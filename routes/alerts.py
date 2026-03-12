from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from models import db
from models.sla import Alert
from models.carrier import Carrier
from services.deadline_service import get_active_alerts
from routes.auth import login_required

alerts_bp = Blueprint('alerts', __name__)


@alerts_bp.route('/alerts')
@login_required
def all_alerts():
    active_alerts = get_active_alerts(dismissed=False)
    dismissed_alerts = get_active_alerts(dismissed=True)
    carriers = Carrier.query.all()
    return render_template(
        'alerts.html',
        active_alerts=active_alerts,
        dismissed_alerts=dismissed_alerts,
        carriers=carriers
    )


@alerts_bp.route('/alerts/dismiss/<int:alert_id>', methods=['POST'])
def dismiss_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.dismissed = True
    db.session.commit()
    return jsonify({'success': True, 'message': 'Alert dismissed'})


@alerts_bp.route('/alerts/dismiss-all', methods=['POST'])
def dismiss_all():
    level = request.json.get('level') if request.json else None
    query = Alert.query.filter_by(dismissed=False)
    if level:
        query = query.filter_by(level=level)
    query.update({'dismissed': True})
    db.session.commit()
    return jsonify({'success': True})


@alerts_bp.route('/alerts/create', methods=['POST'])
def create_alert():
    """Manually create a test alert."""
    data = request.get_json() or {}
    
    alert = Alert(
        carrier_id=data.get('carrier_id'),
        title=data.get('title', 'Test Alert'),
        message=data.get('message', 'Test message'),
        level=data.get('level', 'INFO'),
        clause_reference=data.get('clause_reference', ''),
        days_remaining=data.get('days_remaining')
    )
    db.session.add(alert)
    db.session.commit()
    return jsonify({'success': True, 'alert_id': alert.id})


@alerts_bp.route('/api/alerts')
def api_alerts():
    alerts = get_active_alerts(dismissed=False)
    return jsonify([a.to_dict() for a in alerts])
