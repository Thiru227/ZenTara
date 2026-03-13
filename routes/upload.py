import os
import uuid
from datetime import datetime, timedelta
from flask import Blueprint, request, redirect, url_for, jsonify, flash, current_app
from werkzeug.utils import secure_filename
from models import db
from models.carrier import Carrier
from models.sla import SLADocument, ExtractedClause, Deadline, Alert
from services.rag_service import ingest_document
from config import Config


def _ai_classify(text, carrier_name, version):
    """Route to Claude or Gemini for clause extraction."""
    if Config.AI_PROVIDER == 'claude':
        from services.claude_service import classify_and_extract_clauses
    else:
        from services.gemini_service import classify_and_extract_clauses
    return classify_and_extract_clauses(text, carrier_name, version)


upload_bp = Blueprint('upload', __name__)

ALLOWED_EXTENSIONS = {'pdf', 'txt', 'docx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_file_extension(filename):
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


@upload_bp.route('/carrier/<int:carrier_id>/upload', methods=['POST'])
@login_required
def upload_sla(carrier_id):
    carrier = Carrier.query.get_or_404(carrier_id)

    if 'sla_file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['sla_file']
    branch_name = request.form.get('branch_name', 'main').strip() or 'main'
    version_label = request.form.get('version_label', '').strip()
    tags = request.form.get('tags', '').strip()

    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Only PDF, TXT, and DOCX files are allowed'}), 400

    original_filename = secure_filename(file.filename)
    file_ext = _get_file_extension(file.filename)

    # Auto-generate version label if not provided
    if not version_label:
        existing_count = SLADocument.query.filter_by(carrier_id=carrier_id).count()
        version_label = f"v{existing_count + 1}.0"

    # Create carrier upload directory
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], f"carrier_{carrier.slug}")
    os.makedirs(upload_dir, exist_ok=True)

    # Save file with unique name
    unique_name = f"{carrier.slug}_{version_label.replace('.', '_')}_{uuid.uuid4().hex[:8]}.{file_ext}"
    file_path = os.path.join(upload_dir, unique_name)
    file.save(file_path)

    # Deactivate other versions if this is the first or user wants it active
    set_active = request.form.get('set_active', 'true').lower() == 'true'

    # Track previous active version in THIS branch for diff
    previous_active = None
    if set_active:
        previous_active = SLADocument.query.filter_by(
            carrier_id=carrier_id, branch_name=branch_name, is_active=True
        ).first()
        # Only deactivate others in the SAME branch
        SLADocument.query.filter_by(carrier_id=carrier_id, branch_name=branch_name).update({'is_active': False})

    # ── Handle based on file type ────────────────────────────────
    if file_ext == 'txt':
        # Read text directly
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            full_text = f.read()
        page_count = 1
        file_size = os.path.getsize(file_path)
    elif file_ext == 'docx':
        # Extract ALL text from DOCX — paragraphs AND tables in document order
        from docx import Document as DocxDocument
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph as DocxParagraph
        doc = DocxDocument(file_path)

        parts = []
        for element in doc.element.body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag
            if tag == 'p':
                para = DocxParagraph(element, doc)
                if para.text.strip():
                    parts.append(para.text.strip())
            elif tag == 'tbl':
                table = DocxTable(element, doc)
                for row in table.rows:
                    cells = [cell.text.strip().replace('\n', ' ') for cell in row.cells]
                    # Deduplicate merged cells
                    unique = []
                    prev = None
                    for c in cells:
                        if c != prev:
                            unique.append(c)
                        prev = c
                    parts.append(' | '.join(unique))
                parts.append('')  # Blank line after table

        full_text = '\n'.join(parts)
        page_count = max(1, len(full_text) // 3000)  # Estimate ~3000 chars per page
        file_size = os.path.getsize(file_path)
    else:
        # PDF: extract text
        from services.pdf_service import extract_text_from_pdf, get_pdf_info
        pdf_info = get_pdf_info(file_path)
        page_count = pdf_info.get('page_count', 0)
        file_size = pdf_info.get('file_size', 0)
        full_text = None  # Will be extracted in _process_sla_document

    # Create SLA document record
    sla_doc = SLADocument(
        carrier_id=carrier_id,
        filename=unique_name,
        original_filename=original_filename,
        version_label=version_label,
        file_path=file_path,
        page_count=page_count,
        file_size=file_size,
        branch_name=branch_name,
        is_active=set_active,
        processing_status='processing'
    )

    # For TXT and DOCX files, store text immediately
    if file_ext in ('txt', 'docx') and full_text:
        sla_doc.extracted_text = full_text[:50000]  # Store up to 50k chars

    db.session.add(sla_doc)
    db.session.commit()

    # Process the document (extract clauses, ingest into RAG)
    try:
        if file_ext in ('txt', 'docx'):
            _process_txt_document(sla_doc, carrier, full_text, current_app._get_current_object())
        else:
            _process_pdf_document(sla_doc, carrier, current_app._get_current_object())
        status_msg = 'processed'
    except Exception as e:
        current_app.logger.error(f"SLA processing error: {e}")
        sla_doc.processing_status = 'error'
        db.session.commit()
        status_msg = 'uploaded_with_errors'

    # Create upload success alert
    alert = Alert(
        carrier_id=carrier_id,
        sla_document_id=sla_doc.id,
        title=f"{carrier.name} SLA {version_label} uploaded",
        message=f"'{original_filename}' has been uploaded and processed successfully.",
        level='INFO',
        days_remaining=None
    )
    db.session.add(alert)
    db.session.commit()

    # Build diff URL if previous version exists
    diff_url = None
    if previous_active and previous_active.id != sla_doc.id:
        diff_url = url_for('carriers.sla_diff',
            carrier_id=carrier_id,
            old_id=previous_active.id,
            new_id=sla_doc.id
        )

    return jsonify({
        'success': True,
        'message': f'SLA {version_label} uploaded and {status_msg}!',
        'sla_id': sla_doc.id,
        'version_label': version_label,
        'page_count': sla_doc.page_count,
        'redirect': url_for('carriers.carrier_detail', carrier_id=carrier_id),
        'diff_url': diff_url,
        'previous_version': previous_active.version_label if previous_active else None
    })


def _process_txt_document(sla_doc, carrier, full_text, app):
    """Process a .txt SLA document — classify clauses and store."""
    # 1. AI clause extraction
    extraction_result = _ai_classify(full_text, carrier.name, sla_doc.version_label)

    # 2. Save extracted clauses
    for clause_data in extraction_result.get('clauses', []):
        clause = ExtractedClause(
            sla_document_id=sla_doc.id,
            clause_type=clause_data.get('clause_type', 'general'),
            clause_title=clause_data.get('clause_title', 'Unknown Clause'),
            clause_text=clause_data.get('clause_text', ''),
            clause_number=clause_data.get('clause_number', ''),
            page_number=clause_data.get('page_number', 1),
            extracted_value=clause_data.get('extracted_value', '')
        )
        db.session.add(clause)

    # 3. Save extracted deadlines
    for deadline_data in extraction_result.get('deadlines', []):
        days = deadline_data.get('days_window', 30)
        future_date = datetime.utcnow() + timedelta(days=days)
        deadline = Deadline(
            sla_document_id=sla_doc.id,
            carrier_id=carrier.id,
            title=deadline_data.get('title', 'Deadline'),
            description=deadline_data.get('description', ''),
            clause_reference=deadline_data.get('clause_reference', ''),
            deadline_date=future_date,
            days_window=days
        )
        db.session.add(deadline)

    # 4. Save summary
    sla_doc.clause_summary = extraction_result.get('summary', '')
    sla_doc.processing_status = 'done'
    sla_doc.processed_at = datetime.utcnow()
    db.session.commit()

    # 5. Ingest into RAG (simulate pages from text chunks)
    chunk_size = 2000
    pages = []
    for i in range(0, len(full_text), chunk_size):
        pages.append({
            'text': full_text[i:i + chunk_size],
            'page_number': (i // chunk_size) + 1
        })

    metadata = {
        'carrier_id': str(carrier.id),
        'carrier_slug': carrier.slug,
        'sla_document_id': str(sla_doc.id),
        'sla_version': sla_doc.version_label,
        'upload_date': sla_doc.upload_date.isoformat() if sla_doc.upload_date else '',
        'original_filename': sla_doc.original_filename,
        'is_active_version': sla_doc.is_active
    }
    collections_path = app.config['RAG_COLLECTIONS_PATH']
    ingest_document(carrier.slug, sla_doc.id, pages, metadata, collections_path)


def _process_pdf_document(sla_doc, carrier, app):
    """Process a .pdf SLA document — extract text, classify, ingest."""
    from services.pdf_service import extract_text_from_pdf

    result = extract_text_from_pdf(sla_doc.file_path)
    if not result.get('success'):
        sla_doc.processing_status = 'error'
        db.session.commit()
        return

    full_text = result.get('full_text', '')
    pages = result.get('pages', [])

    sla_doc.extracted_text = full_text[:50000]
    sla_doc.page_count = result.get('page_count', 0)

    # Classify clauses with AI
    extraction_result = _ai_classify(full_text, carrier.name, sla_doc.version_label)

    for clause_data in extraction_result.get('clauses', []):
        clause = ExtractedClause(
            sla_document_id=sla_doc.id,
            clause_type=clause_data.get('clause_type', 'general'),
            clause_title=clause_data.get('clause_title', 'Unknown Clause'),
            clause_text=clause_data.get('clause_text', ''),
            clause_number=clause_data.get('clause_number', ''),
            page_number=clause_data.get('page_number', 1),
            extracted_value=clause_data.get('extracted_value', '')
        )
        db.session.add(clause)

    for deadline_data in extraction_result.get('deadlines', []):
        days = deadline_data.get('days_window', 30)
        future_date = datetime.utcnow() + timedelta(days=days)
        deadline = Deadline(
            sla_document_id=sla_doc.id,
            carrier_id=carrier.id,
            title=deadline_data.get('title', 'Deadline'),
            description=deadline_data.get('description', ''),
            clause_reference=deadline_data.get('clause_reference', ''),
            deadline_date=future_date,
            days_window=days
        )
        db.session.add(deadline)

    sla_doc.clause_summary = extraction_result.get('summary', '')
    sla_doc.processing_status = 'done'
    sla_doc.processed_at = datetime.utcnow()
    db.session.commit()

    metadata = {
        'carrier_id': str(carrier.id),
        'carrier_slug': carrier.slug,
        'sla_document_id': str(sla_doc.id),
        'sla_version': sla_doc.version_label,
        'upload_date': sla_doc.upload_date.isoformat() if sla_doc.upload_date else '',
        'original_filename': sla_doc.original_filename,
        'is_active_version': sla_doc.is_active
    }
    collections_path = app.config['RAG_COLLECTIONS_PATH']
    ingest_document(carrier.slug, sla_doc.id, pages, metadata, collections_path)
