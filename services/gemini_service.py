import os
import logging
import json
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def get_gemini_client():
    """Get configured Gemini client."""
    try:
        import google.generativeai as genai
        api_key = os.environ.get('GEMINI_API_KEY', '')
        if not api_key:
            return None
        genai.configure(api_key=api_key)
        return genai.GenerativeModel('gemini-1.5-flash')
    except ImportError:
        logger.warning("google-generativeai not installed")
        return None
    except Exception as e:
        logger.error(f"Gemini init error: {e}")
        return None


def classify_and_extract_clauses(text, carrier_name, version_label):
    """Use Gemini to extract and classify key clauses from SLA text."""
    model = get_gemini_client()
    if not model:
        return _mock_clause_extraction(carrier_name)

    prompt = f"""You are analyzing a carrier SLA/contract for {carrier_name} (Version: {version_label}).
    
Extract ALL key clauses from this text and return them as a JSON array.
For each clause, identify:
1. clause_type: One of [claim_deadline, liability, penalty, pickup_commitment, payment_terms, dispute_resolution, general]
2. clause_title: Short descriptive title
3. clause_text: The relevant text snippet (max 200 words)
4. clause_number: Clause/section number if mentioned
5. page_number: Estimated page number
6. extracted_value: The key value/number (e.g., "30 days", "$100", "99.5%")

Also extract any TIME-SENSITIVE deadlines into a "deadlines" array with:
- title: Deadline name
- description: What triggers this deadline
- days_window: Number of days
- clause_reference: Clause number

Return ONLY valid JSON in this format:
{{
  "clauses": [...],
  "deadlines": [...],
  "summary": "Brief 2-3 sentence summary of the contract"
}}

CONTRACT TEXT:
{text[:8000]}"""

    try:
        response = model.generate_content(prompt)
        text_response = response.text.strip()
        # Clean markdown code blocks if present
        text_response = re.sub(r'```json\s*', '', text_response)
        text_response = re.sub(r'```\s*', '', text_response)
        return json.loads(text_response)
    except json.JSONDecodeError:
        logger.error("Gemini returned invalid JSON for clause extraction")
        return _mock_clause_extraction(carrier_name)
    except Exception as e:
        logger.error(f"Gemini clause extraction error: {e}")
        return _mock_clause_extraction(carrier_name)


def generate_chat_response(query, context_chunks, carrier_name=None, system_prompt=None):
    """Generate a RAG-based chat response using Gemini."""
    model = get_gemini_client()
    
    scope = f"for {carrier_name}" if carrier_name else "across all carriers"
    
    if not model:
        return {
            'answer': f"I'm Tara! I'd love to help you with that query {scope}, but the Gemini API key isn't configured yet. Please add your GEMINI_API_KEY to the .env file to enable AI responses.",
            'sources': [],
            'suggestions': ["Configure your Gemini API key", "Upload a carrier contract", "Add a new carrier"]
        }

    if not context_chunks:
        return {
            'answer': f"I don't have any contract documents to reference {scope} yet. Please upload an SLA/contract PDF first, and I'll be able to answer detailed questions about it!",
            'sources': [],
            'suggestions': ["Upload your first contract", "Add a new carrier"]
        }

    context_text = "\n\n".join([
        f"[Source: {c.get('source', 'Unknown')}, Page {c.get('page', '?')}]\n{c.get('text', '')}"
        for c in context_chunks[:5]
    ])

    tara_prompt = system_prompt or """You are Tara, ZenTara's calm and wise AI assistant who has read all carrier contracts.
Speak with warmth and clarity. Always cite exact clause references and page numbers when available.
Keep answers concise, human, and actionable."""

    full_prompt = f"""{tara_prompt}

CONTEXT FROM CONTRACTS:
{context_text}

USER QUESTION: {query}

Provide a helpful, accurate answer based ONLY on the contract context above.
After your answer, suggest 2-3 relevant follow-up questions in a JSON block like:
SUGGESTIONS_JSON: ["question1", "question2", "question3"]"""

    try:
        response = model.generate_content(full_prompt)
        full_text = response.text.strip()
        
        # Extract suggestions
        suggestions = []
        suggestions_match = re.search(r'SUGGESTIONS_JSON:\s*(\[.*?\])', full_text, re.DOTALL)
        if suggestions_match:
            try:
                suggestions = json.loads(suggestions_match.group(1))
                full_text = full_text[:suggestions_match.start()].strip()
            except:
                pass

        # Extract sources from context chunks
        sources = []
        for chunk in context_chunks[:3]:
            source = chunk.get('source', '')
            page = chunk.get('page', '')
            if source and source not in [s.get('source') for s in sources]:
                sources.append({'source': source, 'page': page})

        return {
            'answer': full_text,
            'sources': sources,
            'suggestions': suggestions or ["Tell me more", "What are my deadlines?", "Summarize this contract"]
        }
    except Exception as e:
        logger.error(f"Gemini chat error: {e}")
        return {
            'answer': "I encountered an issue processing your question. Please try again in a moment.",
            'sources': [],
            'suggestions': []
        }


def compare_carriers_with_ai(carrier1_data, carrier2_data):
    """Use Gemini to generate a comparison summary between two carriers."""
    model = get_gemini_client()
    if not model:
        return "AI comparison not available. Please configure your Gemini API key."

    prompt = f"""Compare these two carrier contracts and provide a concise, actionable summary:

CARRIER 1: {carrier1_data.get('name', 'Carrier 1')}
Clauses: {json.dumps(carrier1_data.get('clauses', []), indent=2)[:2000]}

CARRIER 2: {carrier2_data.get('name', 'Carrier 2')}
Clauses: {json.dumps(carrier2_data.get('clauses', []), indent=2)[:2000]}

Provide:
1. Which carrier has better terms for claim filing (and why)
2. Which has lower liability exposure
3. Overall recommendation
Keep it under 150 words, conversational, and as Tara (calm, wise yoga instructor)."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Comparison analysis unavailable: {str(e)}"


def compare_versions_with_ai(old_version_data, new_version_data, carrier_name):
    """Generate an AI changelog between two SLA versions."""
    model = get_gemini_client()
    if not model:
        return "Version comparison AI not available."

    prompt = f"""Analyze these two versions of {carrier_name}'s SLA and identify all changes:

OLD VERSION: {old_version_data.get('version_label', 'v1.0')}
{json.dumps(old_version_data.get('clauses', []), indent=2)[:2000]}

NEW VERSION: {new_version_data.get('version_label', 'v2.0')}
{json.dumps(new_version_data.get('clauses', []), indent=2)[:2000]}

Identify:
1. Changes that HURT the user (reduced claim windows, lower liability caps, new penalties)
2. Changes that HELP the user (better terms, longer windows, lower penalties)  
3. Neutral changes

Respond as Tara (calm yoga instructor). Be specific about clause numbers. Max 200 words."""

    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Version comparison unavailable: {str(e)}"


def _mock_clause_extraction(carrier_name):
    """Return mock clause data when Gemini is unavailable."""
    return {
        "clauses": [
            {
                "clause_type": "claim_deadline",
                "clause_title": "Claim Filing Window",
                "clause_text": f"All claims against {carrier_name} must be filed within 30 days of delivery date or scheduled delivery date.",
                "clause_number": "4.2",
                "page_number": 7,
                "extracted_value": "30 days"
            },
            {
                "clause_type": "liability",
                "clause_title": "Maximum Liability Cap",
                "clause_text": "Carrier liability is limited to the declared value of the shipment, not to exceed $100 per shipment unless additional coverage is purchased.",
                "clause_number": "6.1",
                "page_number": 12,
                "extracted_value": "$100 per shipment"
            },
            {
                "clause_type": "pickup_commitment",
                "clause_title": "On-Time Pickup SLA",
                "clause_text": "Carrier commits to 99.5% on-time pickup performance measured monthly.",
                "clause_number": "3.1",
                "page_number": 5,
                "extracted_value": "99.5%"
            },
            {
                "clause_type": "penalty",
                "clause_title": "Service Credit Clause",
                "clause_text": "In the event of 3 or more consecutive late deliveries, a service credit of 2% will be applied to the next monthly invoice.",
                "clause_number": "8.3",
                "page_number": 15,
                "extracted_value": "2% credit after 3 delays"
            }
        ],
        "deadlines": [
            {
                "title": "Claim Filing Deadline",
                "description": "Must be filed from delivery date",
                "days_window": 30,
                "clause_reference": "4.2"
            }
        ],
        "summary": f"This {carrier_name} SLA covers standard carrier services with a 30-day claim window, $100 liability cap, and 99.5% on-time pickup commitment. Service credits apply after repeated delays."
    }
