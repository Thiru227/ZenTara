from flask import Blueprint, render_template, request, redirect, url_for, jsonify, flash, current_app
from models import db
from models.carrier import Carrier
from models.sla import SLADocument, ExtractedClause, Alert, PerformanceMetric
from routes.auth import login_required

carriers_bp = Blueprint('carriers', __name__)


@carriers_bp.route('/carriers')
@login_required
def carrier_list():
    carriers = Carrier.query.all()
    return render_template('carriers.html', carriers=carriers)


@carriers_bp.route('/carriers/new', methods=['GET', 'POST'])
def new_carrier():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        logo_color = request.form.get('logo_color', '#FF6B6B')
        website = request.form.get('website', '').strip()
        
        if not name:
            flash('Carrier name is required.', 'error')
            return redirect(url_for('carriers.new_carrier'))

        # Check duplicate
        existing = Carrier.query.filter_by(name=name).first()
        if existing:
            flash(f'Carrier "{name}" already exists.', 'error')
            return redirect(url_for('carriers.new_carrier'))

        slug = Carrier.make_slug(name)
        # Ensure unique slug
        base_slug = slug
        counter = 1
        while Carrier.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        carrier = Carrier(
            name=name,
            slug=slug,
            description=description,
            logo_color=logo_color,
            website=website
        )
        db.session.add(carrier)
        db.session.commit()

        flash(f'Carrier "{name}" added successfully!', 'success')
        return redirect(url_for('carriers.carrier_detail', carrier_id=carrier.id))

    return render_template('new_carrier.html')


@carriers_bp.route('/carrier/<int:carrier_id>')
def carrier_detail(carrier_id):
    carrier = Carrier.query.get_or_404(carrier_id)
    sla_docs = SLADocument.query.filter_by(carrier_id=carrier_id).order_by(SLADocument.upload_date.desc()).all()
    active_sla = SLADocument.query.filter_by(carrier_id=carrier_id, is_active=True).first()
    
    # Get clauses for active SLA
    active_clauses = []
    if active_sla:
        active_clauses = ExtractedClause.query.filter_by(sla_document_id=active_sla.id).all()
    
    # Get performance metrics
    metrics = PerformanceMetric.query.filter_by(carrier_id=carrier_id).order_by(
        PerformanceMetric.metric_date.asc()
    ).all()

    # Get open alerts for this carrier
    alerts = Alert.query.filter_by(carrier_id=carrier_id, dismissed=False).order_by(
        Alert.days_remaining.asc()
    ).all()

    return render_template(
        'carrier_detail.html',
        carrier=carrier,
        sla_docs=sla_docs,
        active_sla=active_sla,
        active_clauses=active_clauses,
        metrics=metrics,
        alerts=alerts
    )


@carriers_bp.route('/carrier/<int:carrier_id>/set-active/<int:sla_id>', methods=['POST'])
def set_active_sla(carrier_id, sla_id):
    # Deactivate all SLAs for this carrier
    SLADocument.query.filter_by(carrier_id=carrier_id).update({'is_active': False})
    # Activate selected
    sla = SLADocument.query.get_or_404(sla_id)
    sla.is_active = True
    db.session.commit()
    return jsonify({'success': True, 'message': f'Version {sla.version_label} is now active'})


@carriers_bp.route('/carrier/<int:carrier_id>/metrics', methods=['POST'])
def add_metric(carrier_id):
    carrier = Carrier.query.get_or_404(carrier_id)
    
    metric = PerformanceMetric(
        carrier_id=carrier_id,
        on_time_delivery_pct=float(request.form.get('on_time_delivery_pct', 0)),
        claim_resolution_days=float(request.form.get('claim_resolution_days', 0)),
        dispute_win_rate=float(request.form.get('dispute_win_rate', 0)),
        cost_per_shipment=float(request.form.get('cost_per_shipment', 0)),
        notes=request.form.get('notes', '')
    )
    db.session.add(metric)
    db.session.commit()
    
    flash('Performance metrics added!', 'success')
    return redirect(url_for('carriers.carrier_detail', carrier_id=carrier_id))


@carriers_bp.route('/carrier/<int:carrier_id>/delete', methods=['POST'])
def delete_carrier(carrier_id):
    carrier = Carrier.query.get_or_404(carrier_id)
    name = carrier.name
    db.session.delete(carrier)
    db.session.commit()
    flash(f'Carrier "{name}" deleted.', 'info')
    return redirect(url_for('carriers.carrier_list'))


@carriers_bp.route('/carrier/<int:carrier_id>/sla/<int:sla_id>/view')
def view_sla_document(carrier_id, sla_id):
    """View the full extracted text of an SLA document."""
    carrier = Carrier.query.get_or_404(carrier_id)
    sla = SLADocument.query.get_or_404(sla_id)

    # Get clauses for this SLA
    clauses = ExtractedClause.query.filter_by(sla_document_id=sla.id).all()

    return render_template(
        'sla_viewer.html',
        carrier=carrier,
        sla=sla,
        clauses=clauses
    )


@carriers_bp.route('/carrier/<int:carrier_id>/sla/<int:sla_id>/delete', methods=['POST'])
def delete_sla(carrier_id, sla_id):
    """Delete an SLA document."""
    sla = SLADocument.query.get_or_404(sla_id)
    version = sla.version_label

    # Delete related records
    ExtractedClause.query.filter_by(sla_document_id=sla.id).delete()
    from models.sla import Deadline
    Deadline.query.filter_by(sla_document_id=sla.id).delete()
    Alert.query.filter_by(sla_document_id=sla.id).delete()

    db.session.delete(sla)
    db.session.commit()

    return jsonify({'success': True, 'message': f'SLA {version} deleted'})


@carriers_bp.route('/carrier/<int:carrier_id>/diff/<int:old_id>/<int:new_id>')
def sla_diff(carrier_id, old_id, new_id):
    """Compare two SLA document versions side-by-side."""
    import difflib

    carrier = Carrier.query.get_or_404(carrier_id)
    old_sla = SLADocument.query.get_or_404(old_id)
    new_sla = SLADocument.query.get_or_404(new_id)

    old_text = (old_sla.extracted_text or '').strip()
    new_text = (new_sla.extracted_text or '').strip()

    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    # Generate unified diff
    diff_lines = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{old_sla.version_label} ({old_sla.original_filename})",
        tofile=f"{new_sla.version_label} ({new_sla.original_filename})",
        lineterm=''
    ))

    # Parse diff into structured blocks for rendering
    diff_blocks = []
    current_block = None

    for line in diff_lines:
        if line.startswith('@@'):
            if current_block:
                diff_blocks.append(current_block)
            current_block = {'header': line, 'lines': []}
        elif line.startswith('---') or line.startswith('+++'):
            continue  # Skip file headers
        elif current_block is not None:
            if line.startswith('+'):
                current_block['lines'].append({'type': 'add', 'text': line[1:]})
            elif line.startswith('-'):
                current_block['lines'].append({'type': 'del', 'text': line[1:]})
            else:
                current_block['lines'].append({'type': 'ctx', 'text': line[1:] if line.startswith(' ') else line})

    if current_block:
        diff_blocks.append(current_block)

    # Compute stats
    added = sum(1 for b in diff_blocks for l in b['lines'] if l['type'] == 'add')
    removed = sum(1 for b in diff_blocks for l in b['lines'] if l['type'] == 'del')
    unchanged = sum(1 for b in diff_blocks for l in b['lines'] if l['type'] == 'ctx')

    # Also compare extracted clauses
    old_clauses = ExtractedClause.query.filter_by(sla_document_id=old_id).all()
    new_clauses = ExtractedClause.query.filter_by(sla_document_id=new_id).all()

    old_clause_map = {(c.clause_type, c.clause_number or c.clause_title): c for c in old_clauses}
    new_clause_map = {(c.clause_type, c.clause_number or c.clause_title): c for c in new_clauses}

    clause_changes = []
    all_keys = set(list(old_clause_map.keys()) + list(new_clause_map.keys()))

    for key in sorted(all_keys):
        old_c = old_clause_map.get(key)
        new_c = new_clause_map.get(key)

        if old_c and not new_c:
            clause_changes.append({
                'type': 'removed', 'clause_type': key[0], 'clause_ref': key[1],
                'old_value': old_c.extracted_value or '', 'new_value': '',
                'old_title': old_c.clause_title, 'new_title': ''
            })
        elif new_c and not old_c:
            clause_changes.append({
                'type': 'added', 'clause_type': key[0], 'clause_ref': key[1],
                'old_value': '', 'new_value': new_c.extracted_value or '',
                'old_title': '', 'new_title': new_c.clause_title
            })
        elif old_c and new_c:
            old_val = old_c.extracted_value or ''
            new_val = new_c.extracted_value or ''
            if old_val != new_val or old_c.clause_text != new_c.clause_text:
                clause_changes.append({
                    'type': 'changed', 'clause_type': key[0], 'clause_ref': key[1],
                    'old_value': old_val, 'new_value': new_val,
                    'old_title': old_c.clause_title, 'new_title': new_c.clause_title
                })

    return render_template('sla_diff.html',
        carrier=carrier,
        old_sla=old_sla,
        new_sla=new_sla,
        diff_blocks=diff_blocks,
        added=added,
        removed=removed,
        unchanged=unchanged,
        clause_changes=clause_changes,
        is_identical=(not diff_blocks)
    )


@carriers_bp.route('/api/carriers')
def api_carriers():
    carriers = Carrier.query.all()
    return jsonify([c.to_dict() for c in carriers])


@carriers_bp.route('/carriers/create-quick', methods=['POST'])
def create_quick_carrier():
    """Quick-create a carrier via JSON (used by chat page upload).
    Returns existing carrier if name already exists.
    """
    data = request.get_json() or {}
    name = data.get('name', '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'Carrier name is required'}), 400

    # Check if carrier already exists (case-insensitive)
    existing = Carrier.query.filter(
        db.func.lower(Carrier.name) == name.lower()
    ).first()

    if existing:
        return jsonify({
            'success': True,
            'carrier_id': existing.id,
            'carrier_name': existing.name,
            'created': False
        })

    # Create new carrier
    slug = Carrier.make_slug(name)
    base_slug = slug
    counter = 1
    while Carrier.query.filter_by(slug=slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    carrier = Carrier(name=name, slug=slug)
    db.session.add(carrier)
    db.session.commit()

    return jsonify({
        'success': True,
        'carrier_id': carrier.id,
        'carrier_name': carrier.name,
        'created': True
    })

