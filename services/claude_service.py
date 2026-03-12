"""
Claude (Anthropic) AI Service — ZenTara
Drop-in replacement / parallel service for Gemini.
"""
import logging
import os

logger = logging.getLogger(__name__)

# Lazy-load Anthropic client
_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic
            api_key = os.environ.get('CLAUDE_API_KEY', '')
            if api_key:
                _client = anthropic.Anthropic(api_key=api_key)
            else:
                logger.warning("CLAUDE_API_KEY not set — Claude responses disabled.")
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
    return _client


# ─── Model to use ────────────────────────────────────────────────
CLAUDE_MODEL = "claude-haiku-4-5"   # latest Haiku — fast, cheap; swap for claude-sonnet-4-5 for higher quality


def generate_chat_response(query: str, context_chunks: list, carrier_name: str = None,
                           system_prompt: str = '') -> dict:
    """
    Generate a RAG-powered chat response using Claude.
    Returns dict: {answer, sources, suggestions}
    """
    client = _get_client()

    if not client:
        return _mock_response(query, carrier_name)

    # Build context block from RAG chunks — distribute evenly across carriers
    context_text = ""
    sources = []

    # Group chunks by carrier first
    carrier_chunks = {}
    for chunk in context_chunks:
        meta = chunk.get('metadata', {}) if isinstance(chunk, dict) else {}
        carrier_slug = meta.get('carrier_slug', 'unknown')
        if carrier_slug not in carrier_chunks:
            carrier_chunks[carrier_slug] = []
        carrier_chunks[carrier_slug].append(chunk)

    # Round-robin select up to 12 chunks evenly from each carrier
    max_total = 12
    selected_chunks = []
    if carrier_chunks:
        per_carrier = max(2, max_total // len(carrier_chunks))
        for slug, cchunks in carrier_chunks.items():
            selected_chunks.extend(cchunks[:per_carrier])
    selected_chunks = selected_chunks[:max_total]

    for i, chunk in enumerate(selected_chunks):
        text = chunk.get('text', '') if isinstance(chunk, dict) else str(chunk)
        meta = chunk.get('metadata', {}) if isinstance(chunk, dict) else {}
        carrier = meta.get('carrier_slug', 'unknown')
        version = meta.get('sla_version', '')
        fname = meta.get('original_filename', '')
        context_text += f"\n[Source {i+1} — {carrier} {version} ({fname})]:\n{text[:1000]}\n"
        if carrier not in [s.get('carrier') for s in sources]:
            sources.append({'carrier': carrier, 'version': version, 'chunk': i + 1})

    carrier_scope = f"You are answering about {carrier_name}'s contract specifically." if carrier_name else \
        "You may reference multiple carrier contracts in your knowledge base."

    user_message = f"""Context from carrier SLA documents:
{context_text if context_text else 'No specific contract documents loaded yet.'}

---
{carrier_scope}

User question: {query}

Answer concisely and helpfully. If referencing a specific clause, cite it.
End with exactly 2-3 short, actionable follow-up question suggestions.
Format them exactly like this at the very end:
SUGGESTIONS:
- Short Question 1?
- Short Question 2?
- Short Question 3?"""

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            system=system_prompt or _default_system_prompt(),
            messages=[{"role": "user", "content": user_message}]
        )

        full_text = message.content[0].text if message.content else ""
        # Sanitize for Windows console encoding (strip non-BMP chars if needed)
        full_text = full_text.encode('utf-8', errors='replace').decode('utf-8')

        # Parse suggestions if Claude included them
        suggestions = []
        answer = full_text
        if "SUGGESTIONS:" in full_text:
            parts = full_text.split("SUGGESTIONS:", 1)
            answer = parts[0].strip()
            # Handle potential "|" separated single-line output just in case
            if "|" in parts[1] and "\n" not in parts[1].strip():
                raw_sug = parts[1].strip().split('|')
            else:
                raw_sug = parts[1].strip().split('\n')
            suggestions = [s.strip().lstrip('•-123456789. ') for s in raw_sug if s.strip() and '?' in s][:3]

        return {
            'answer': answer,
            'sources': sources,
            'suggestions': suggestions or [
                "What are the penalty clauses?",
                "When does this SLA expire?",
                "What are my claim deadlines?"
            ]
        }

    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _mock_response(query, carrier_name)


def classify_and_extract_clauses(pdf_text: str, carrier_name: str, version: str) -> dict:
    """
    Use Claude to classify and extract SLA clauses from raw PDF text.
    Returns dict: {clauses: [...], deadlines: [...], summary: str}
    """
    client = _get_client()

    if not client:
        return _mock_extraction(carrier_name)

    prompt = f"""You are an expert at analyzing carrier SLA contracts.
Analyze this contract for {carrier_name} (version: {version}).

CONTRACT TEXT (first 8000 chars):
{pdf_text[:8000]}

Extract and return a JSON object with this exact structure:
{{
  "summary": "2-3 sentence plain English summary of this SLA",
  "clauses": [
    {{
      "clause_type": "one of: claim_deadline, liability, penalty, pickup_commitment, payment_terms, dispute_resolution, general",
      "clause_title": "short title",
      "clause_text": "exact text or paraphrase from contract",
      "clause_number": "section number if visible, else empty string",
      "page_number": 1,
      "extracted_value": "key value e.g. '30 days', '$100/shipment', or empty string"
    }}
  ],
  "deadlines": [
    {{
      "title": "deadline name",
      "description": "what happens at this deadline",
      "clause_reference": "section number",
      "days_window": 30
    }}
  ]
}}

Return ONLY valid JSON, no markdown fences."""

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}]
        )

        import json
        import re
        raw = message.content[0].text.strip()

        # Strip markdown code fences robustly
        # Match ```json ... ``` or ``` ... ```
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', raw, re.DOTALL)
        if fence_match:
            text = fence_match.group(1).strip()
        else:
            text = raw

        # Find the JSON object boundaries
        start = text.find('{')
        end = text.rfind('}')
        if start >= 0 and end > start:
            text = text[start:end + 1]

        result = json.loads(text)
        logger.info(f"Claude extracted {len(result.get('clauses', []))} clauses for {carrier_name}")
        return result

    except json.JSONDecodeError as je:
        logger.error(f"Claude JSON parse error for {carrier_name}: {je}")
        logger.error(f"Raw response (first 500 chars): {raw[:500] if 'raw' in dir() else 'N/A'}")
        return _mock_extraction(carrier_name)
    except Exception as e:
        logger.error(f"Claude extraction error: {e}")
        return _mock_extraction(carrier_name)


def compare_two_carriers_ai(carrier1_data: dict, carrier2_data: dict) -> dict:
    """Use Claude to generate a carrier comparison summary."""
    client = _get_client()
    if not client:
        return {'summary': 'Comparison unavailable — Claude not configured.', 'recommendation': ''}

    prompt = f"""Compare these two carrier SLA contracts and provide a concise analysis.

Carrier 1: {carrier1_data.get('name')}
- Health Score: {carrier1_data.get('health_score')}
- Active SLA: {carrier1_data.get('active_sla_version', 'None')}
- Clauses: {carrier1_data.get('clause_summary', 'Not extracted')}

Carrier 2: {carrier2_data.get('name')}
- Health Score: {carrier2_data.get('health_score')}
- Active SLA: {carrier2_data.get('active_sla_version', 'None')}
- Clauses: {carrier2_data.get('clause_summary', 'Not extracted')}

Provide:
1. A 2-sentence executive summary
2. Which carrier you recommend and why (1 sentence)

Format: JSON with keys "summary" and "recommendation"."""

    try:
        import json
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = message.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        logger.error(f"Claude compare error: {e}")
        return {'summary': 'Unable to generate comparison.', 'recommendation': ''}


def _default_system_prompt():
    return """You are Tara, ZenTara's AI assistant — a calm, knowledgeable, and friendly expert 
in carrier SLA contracts. You help operations teams understand their carrier contracts, 
track deadlines, and make informed decisions. You speak in a warm, professional tone.
You always cite specific clauses when referencing contract terms. 
If you don't know something, say so honestly rather than guessing."""


def _mock_response(query: str, carrier_name: str = None) -> dict:
    scope = f" about {carrier_name}'s contract" if carrier_name else ""
    return {
        'answer': f"I'm in demo mode{scope}. Configure your CLAUDE_API_KEY in the .env file to get real AI-powered answers about your carrier contracts.",
        'sources': [],
        'suggestions': [
            "What are my claim deadlines?",
            "Show me the penalty clauses",
            "Which carrier has the best terms?"
        ]
    }


def _mock_extraction(carrier_name: str) -> dict:
    return {
        'summary': f'Demo mode: {carrier_name} SLA uploaded. Configure CLAUDE_API_KEY for real clause extraction.',
        'clauses': [
            {
                'clause_type': 'claim_deadline',
                'clause_title': 'Claim Filing Window',
                'clause_text': 'Claims must be filed within 30 days of delivery.',
                'clause_number': '4.2',
                'page_number': 1,
                'extracted_value': '30 days'
            }
        ],
        'deadlines': [
            {
                'title': 'Claim Filing Deadline',
                'description': 'File all carrier claims within 30 days',
                'clause_reference': '4.2',
                'days_window': 30
            }
        ]
    }
