from flask import Blueprint, request, jsonify, render_template, current_app
from models.carrier import Carrier
from models.sla import SLADocument
from config import Config
from routes.auth import login_required

chat_bp = Blueprint('chat', __name__)


def _ai_generate(query, context_chunks, carrier_name=None, system_prompt=''):
    """Route to Claude or Gemini based on AI_PROVIDER setting."""
    if Config.AI_PROVIDER == 'claude':
        from services.claude_service import generate_chat_response
    else:
        from services.gemini_service import generate_chat_response
    return generate_chat_response(
        query=query,
        context_chunks=context_chunks,
        carrier_name=carrier_name,
        system_prompt=system_prompt
    )


def _get_sla_context_chunks(carrier_id=None):
    """
    Pull SLA text from the database as context chunks.
    If carrier_id is given, only that carrier's SLAs. Otherwise all.
    Falls back gracefully if no documents are uploaded yet.
    """
    if carrier_id:
        slas = SLADocument.query.filter_by(carrier_id=carrier_id, is_active=True).all()
        if not slas:
            slas = SLADocument.query.filter_by(carrier_id=carrier_id).order_by(
                SLADocument.upload_date.desc()).limit(3).all()
    else:
        slas = SLADocument.query.filter_by(is_active=True).all()
        if not slas:
            slas = SLADocument.query.order_by(SLADocument.upload_date.desc()).limit(5).all()

    chunks = []
    for sla in slas:
        text = sla.extracted_text or ''
        if not text:
            continue
        # Get carrier name for metadata
        carrier = Carrier.query.get(sla.carrier_id)
        carrier_slug = carrier.slug if carrier else 'unknown'

        # Split into chunks of ~1500 chars
        chunk_size = 1500
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i:i + chunk_size]
            if len(chunk_text) > 50:
                chunks.append({
                    'text': chunk_text,
                    'metadata': {
                        'carrier_slug': carrier_slug,
                        'sla_version': sla.version_label,
                        'original_filename': sla.original_filename or ''
                    }
                })
    return chunks


@chat_bp.route('/chat')
@login_required
def chat_page():
    carriers = Carrier.query.all()
    return render_template('chat.html', carriers=carriers)


@chat_bp.route('/chat/ask', methods=['POST'])
def global_chat():
    """Global RAG chat across all carrier documents."""
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    carrier_filter = data.get('carrier_id')

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    if carrier_filter:
        carrier = Carrier.query.get(carrier_filter)
        if not carrier:
            return jsonify({'error': 'Carrier not found'}), 404
        chunks = _get_sla_context_chunks(carrier_id=carrier.id)
        carrier_name = carrier.name
    else:
        chunks = _get_sla_context_chunks()
        carrier_name = None

    if not chunks:
        return jsonify({
            'answer': "I don't have any contract documents loaded yet. Upload an SLA file (PDF or TXT) for a carrier first, then I can answer questions about it!",
            'sources': [],
            'suggestions': ['Go to Carriers page', 'Upload an SLA document'],
            'carrier_name': carrier_name
        })

    response = _ai_generate(
        query=query,
        context_chunks=chunks,
        carrier_name=carrier_name,
        system_prompt=Config.TARA_SYSTEM_PROMPT
    )

    return jsonify({
        'answer': response.get('answer', ''),
        'sources': response.get('sources', []),
        'suggestions': response.get('suggestions', []),
        'carrier_name': carrier_name
    })


@chat_bp.route('/carrier/<int:carrier_id>/chat/ask', methods=['POST'])
def carrier_chat(carrier_id):
    """Carrier-scoped RAG chat — only this carrier's documents."""
    carrier = Carrier.query.get_or_404(carrier_id)
    data = request.get_json() or {}
    query = data.get('query', '').strip()

    if not query:
        return jsonify({'error': 'Query is required'}), 400

    chunks = _get_sla_context_chunks(carrier_id=carrier.id)

    if not chunks:
        return jsonify({
            'answer': f"I haven't read any contracts for {carrier.name} yet. Upload an SLA file (PDF or TXT) and I'll be able to answer detailed questions.",
            'sources': [],
            'suggestions': [f'Upload {carrier.name} SLA', 'View carrier details'],
            'carrier_name': carrier.name
        })

    scoped_prompt = f"""{Config.TARA_SYSTEM_PROMPT}

IMPORTANT: You are ONLY answering questions about {carrier.name}'s contracts.
Do not reference other carriers. Always state: 'Based on {carrier.name}'s SLA' when answering."""

    response = _ai_generate(
        query=query,
        context_chunks=chunks,
        carrier_name=carrier.name,
        system_prompt=scoped_prompt
    )

    return jsonify({
        'answer': response.get('answer', ''),
        'sources': response.get('sources', []),
        'suggestions': response.get('suggestions', []),
        'carrier_name': carrier.name
    })
