from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

ALERT_CONFIG = {
    "CRITICAL": {"max_days": 2,  "color": "#FF3B30", "tara_state": "stressed"},
    "WARNING":  {"max_days": 7,  "color": "#FFB347", "tara_state": "standing"},
    "INFO":     {"max_days": 30, "color": "#4ECDC4", "tara_state": "standing"},
}


def get_dashboard_tara_state(alerts):
    """Determine Tara's state based on current alerts."""
    if not alerts:
        return {
            'state': 'calm',
            'image': 'tara_meditation.png',
            'pose_style': '',
            'message': "Everything's under control. Breathe 🌿",
            'bg_mood': 'calm',
            'health_score': 98
        }
    
    has_critical = any(a.level == 'CRITICAL' for a in alerts)
    has_warning = any(a.level == 'WARNING' for a in alerts)
    
    if has_critical:
        return {
            'state': 'stressed',
            'image': 'tara_stressed.png',
            'pose_style': '',
            'message': "⚠️ I'm stressed! Critical deadlines need your attention right now.",
            'bg_mood': 'critical',
            'health_score': max(20, 60 - len([a for a in alerts if a.level == 'CRITICAL']) * 15)
        }
    elif has_warning:
        return {
            'state': 'standing',
            'image': 'tara_standing.png',
            'pose_style': '',
            'message': "A few things need your attention. Let's work through it together.",
            'bg_mood': 'warning',
            'health_score': max(55, 85 - len([a for a in alerts if a.level == 'WARNING']) * 8)
        }
    else:
        return {
            'state': 'victory',
            'image': 'tara_victory.png',
            'pose_style': '',
            'message': "You're on top of everything! Tara is celebrating 🎉",
            'bg_mood': 'calm',
            'health_score': 95
        }


def refresh_alerts(app):
    """Refresh all alerts based on current deadlines and SLA status."""
    from models.sla import Deadline, Alert, SLADocument
    from models.carrier import Carrier
    from models import db
    
    with app.app_context():
        try:
            # Clear non-dismissed alerts older than 1 hour (they'll be regenerated)
            # Keep dismissed ones
            now = datetime.utcnow()
            
            # Check deadline-based alerts for active SLA documents
            active_slas = SLADocument.query.filter_by(is_active=True).all()
            
            for sla in active_slas:
                deadlines = Deadline.query.filter_by(sla_document_id=sla.id).all()
                for deadline in deadlines:
                    if not deadline.deadline_date:
                        continue
                    
                    days_left = (deadline.deadline_date - now).days
                    
                    if days_left <= 30:
                        level = 'CRITICAL' if days_left <= 2 else ('WARNING' if days_left <= 7 else 'INFO')
                        
                        # Check if alert already exists
                        existing = Alert.query.filter_by(
                            carrier_id=deadline.carrier_id,
                            sla_document_id=sla.id,
                            title=f"Deadline: {deadline.title}",
                            dismissed=False
                        ).first()
                        
                        if not existing:
                            alert = Alert(
                                carrier_id=deadline.carrier_id,
                                sla_document_id=sla.id,
                                title=f"Deadline: {deadline.title}",
                                message=deadline.description or f"{deadline.title} deadline approaching",
                                level=level,
                                clause_reference=deadline.clause_reference,
                                days_remaining=days_left
                            )
                            db.session.add(alert)
            
            db.session.commit()
        except Exception as e:
            logger.error(f"Alert refresh error: {e}")
            db.session.rollback()


def get_active_alerts(dismissed=False):
    """Get all active (non-dismissed by default) alerts."""
    from models.sla import Alert
    from models.carrier import Carrier
    
    query = Alert.query.filter_by(dismissed=dismissed)
    alerts = query.order_by(
        Alert.level.desc(),  # CRITICAL first (alphabetically W > I > C, but we handle display)
        Alert.days_remaining.asc(),
        Alert.created_at.desc()
    ).all()
    
    # Sort properly: CRITICAL > WARNING > INFO
    level_order = {'CRITICAL': 0, 'WARNING': 1, 'INFO': 2}
    alerts.sort(key=lambda a: (level_order.get(a.level, 3), a.days_remaining or 999))
    
    return alerts


def get_system_health_score(alerts):
    """Calculate overall system health score 0-100."""
    if not alerts:
        return 98
    
    critical_count = sum(1 for a in alerts if a.level == 'CRITICAL')
    warning_count = sum(1 for a in alerts if a.level == 'WARNING')
    info_count = sum(1 for a in alerts if a.level == 'INFO')
    
    score = 100
    score -= critical_count * 25
    score -= warning_count * 10
    score -= info_count * 2
    
    return max(0, min(100, score))


def create_sample_alert(carrier, sla_doc, days_remaining, level='INFO'):
    """Helper to create a demo alert for a carrier."""
    from models.sla import Alert
    from models import db
    
    messages = {
        'CRITICAL': f"Urgent: Claim deadline expires in {days_remaining} day(s). File immediately.",
        'WARNING': f"Claim window closes in {days_remaining} days. Review and prepare documentation.",
        'INFO': f"Upcoming deadline in {days_remaining} days. No immediate action required."
    }
    
    alert = Alert(
        carrier_id=carrier.id,
        sla_document_id=sla_doc.id if sla_doc else None,
        title=f"{carrier.name} Claim Window Closing",
        message=messages.get(level, messages['INFO']),
        level=level,
        clause_reference="4.2",
        days_remaining=days_remaining
    )
    db.session.add(alert)
    db.session.commit()
    return alert
