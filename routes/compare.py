from flask import Blueprint, render_template, request, jsonify
from models.carrier import Carrier
from models.sla import SLADocument
from services.compare_service import compare_two_carriers, compare_two_versions
from routes.auth import login_required

compare_bp = Blueprint('compare', __name__)


@compare_bp.route('/compare')
@login_required
def compare_page():
    carriers = Carrier.query.all()
    carrier1_id = request.args.get('carrier1', type=int)
    carrier2_id = request.args.get('carrier2', type=int)
    
    carrier1 = Carrier.query.get(carrier1_id) if carrier1_id else None
    carrier2 = Carrier.query.get(carrier2_id) if carrier2_id else None
    
    return render_template(
        'compare.html',
        carriers=carriers,
        carrier1=carrier1,
        carrier2=carrier2
    )


@compare_bp.route('/compare/carriers', methods=['POST'])
def compare_carriers_api():
    data = request.get_json() or {}
    carrier1_id = data.get('carrier1_id')
    carrier2_id = data.get('carrier2_id')

    if not carrier1_id or not carrier2_id:
        return jsonify({'error': 'Two carrier IDs required'}), 400
    
    if carrier1_id == carrier2_id:
        return jsonify({'error': 'Select two different carriers'}), 400

    carrier1 = Carrier.query.get_or_404(carrier1_id)
    carrier2 = Carrier.query.get_or_404(carrier2_id)

    result = compare_two_carriers(carrier1, carrier2)
    return jsonify(result)


@compare_bp.route('/compare/versions', methods=['POST'])
def compare_versions_api():
    data = request.get_json() or {}
    sla_v1_id = data.get('sla_v1_id')
    sla_v2_id = data.get('sla_v2_id')

    if not sla_v1_id or not sla_v2_id:
        return jsonify({'error': 'Two SLA version IDs required'}), 400

    sla_v1 = SLADocument.query.get_or_404(sla_v1_id)
    sla_v2 = SLADocument.query.get_or_404(sla_v2_id)

    if sla_v1.carrier_id != sla_v2.carrier_id:
        return jsonify({'error': 'Versions must belong to the same carrier'}), 400

    carrier = Carrier.query.get(sla_v1.carrier_id)
    result = compare_two_versions(sla_v1, sla_v2, carrier.name if carrier else 'Unknown')
    return jsonify(result)


@compare_bp.route('/api/carrier/<int:carrier_id>/versions')
def carrier_versions(carrier_id):
    versions = SLADocument.query.filter_by(carrier_id=carrier_id).order_by(
        SLADocument.upload_date.desc()
    ).all()
    return jsonify([v.to_dict() for v in versions])
