from flask import Blueprint, render_template, request, jsonify
import os
import requests as http_requests
from models.carrier import Carrier
from models.sla import Alert, SLADocument
from services.deadline_service import get_active_alerts, get_dashboard_tara_state, get_system_health_score
from routes.auth import login_required

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def landing():
    return render_template('landing.html')

@dashboard_bp.route('/privacy')
def privacy_policy():
    return render_template('privacy_policy.html')

@dashboard_bp.route('/terms')
def terms_of_service():
    return render_template('terms_of_service.html')


@dashboard_bp.route('/integrations')
@login_required
def integrations():
    return render_template('integrations.html')


@dashboard_bp.route('/admin/send-notification', methods=['POST'])
@login_required
def admin_send_notification():
    """Send a push notification to all users via OneSignal REST API."""
    data = request.get_json() or {}
    title = data.get('title', '⚠️ Tara Alert')
    message = data.get('message', 'Check your ZenTara dashboard for important updates.')

    onesignal_app_id = os.environ.get('ONESIGNAL_APP_ID', '75c70233-bd82-4d22-8490-dd752a36f79b')
    onesignal_api_key = os.environ.get('ONESIGNAL_API_KEY', '')

    if not onesignal_api_key:
        # If no API key, still return success for demo purposes
        return jsonify({'success': True, 'message': 'Demo mode — notification simulated (no OneSignal API key set).'})

    headers = {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': f'Basic {onesignal_api_key}'
    }
    payload = {
        'app_id': onesignal_app_id,
        'included_segments': ['Subscribed Users'],
        'headings': {'en': title},
        'contents': {'en': message},
        'chrome_web_icon': '/static/icon-192x192.png',
        'url': '/dashboard'
    }

    try:
        resp = http_requests.post('https://onesignal.com/api/v1/notifications', json=payload, headers=headers)
        return jsonify({'success': True, 'response': resp.json()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@dashboard_bp.route('/dashboard')
@login_required
def dashboard():
    carriers = Carrier.query.all()
    active_alerts = get_active_alerts(dismissed=False)
    tara_state = get_dashboard_tara_state(active_alerts)
    health_score = get_system_health_score(active_alerts)

    # Stats
    total_carriers = len(carriers)
    active_slas = SLADocument.query.filter_by(is_active=True).count()
    critical_count = sum(1 for a in active_alerts if a.level == 'CRITICAL')
    warning_count = sum(1 for a in active_alerts if a.level == 'WARNING')
    info_count = sum(1 for a in active_alerts if a.level == 'INFO')

    # Deadlines this week
    from datetime import datetime, timedelta
    week_from_now = datetime.utcnow() + timedelta(days=7)

    # Build carrier cards with their health data
    carrier_cards = []
    for carrier in carriers:
        active_sla = SLADocument.query.filter_by(carrier_id=carrier.id, is_active=True).first()
        carrier_alerts = [a for a in active_alerts if a.carrier_id == carrier.id]
        carrier_health = carrier.health_score
        
        status = 'critical' if any(a.level == 'CRITICAL' for a in carrier_alerts) else \
                 'warning' if any(a.level == 'WARNING' for a in carrier_alerts) else 'healthy'

        carrier_cards.append({
            'carrier': carrier,
            'active_sla': active_sla,
            'alerts': carrier_alerts[:3],
            'health_score': carrier_health,
            'status': status,
            'sla_count': carrier.sla_count
        })

    now = datetime.utcnow()
    # Windows-safe date formatting (%-d not supported on Windows)
    now_str = now.strftime('%A, %B %d, %Y').replace(' 0', ' ')  # strip leading zero portably

    return render_template(
        'dashboard.html',
        tara_state=tara_state,
        health_score=health_score,
        alerts=active_alerts[:20],
        carrier_cards=carrier_cards,
        total_carriers=total_carriers,
        active_slas=active_slas,
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        now=now,
        now_str=now_str
    )
