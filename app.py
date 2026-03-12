import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify
from config import config
from models import db


def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # ── Reverse Proxy Support (Render / HTTPS) ──────────────────
    # Render terminates SSL at the load balancer and forwards X-Forwarded-*
    # headers. This tells Flask to trust those headers so url_for(_external=True)
    # generates https:// URLs instead of http://.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Ensure upload and RAG directories exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['RAG_COLLECTIONS_PATH'], exist_ok=True)

    # Initialize extensions
    db.init_app(app)

    # Register blueprints
    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.carriers import carriers_bp
    from routes.upload import upload_bp
    from routes.chat import chat_bp
    from routes.alerts import alerts_bp
    from routes.compare import compare_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(carriers_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(compare_bp)

    # Inject current_user into all templates
    @app.context_processor
    def inject_user():
        from routes.auth import get_current_user
        return dict(current_user=get_current_user())

    # ── Health Check (Render uses this to verify the service is up) ──
    @app.route('/health')
    def health_check():
        return jsonify({'status': 'healthy', 'service': 'zentara'}), 200

    # ── PWA Support (Service Worker & Manifest) ──────────────────────
    @app.route('/sw.js')
    def service_worker():
        return app.send_static_file('sw.js')

    @app.route('/OneSignalSDKWorker.js')
    def onesignal_worker():
        return app.send_static_file('sw.js')

    @app.route('/manifest.json')
    def manifest():
        return app.send_static_file('manifest.json')

    @app.route('/.well-known/assetlinks.json')
    def assetlinks():
        return app.send_static_file('assetlinks.json')

    # Create all tables on first run
    with app.app_context():
        # Import all models so SQLAlchemy knows about them
        from models.carrier import Carrier
        from models.sla import SLADocument, ExtractedClause, Deadline, Alert, PerformanceMetric
        from models.user import User
        db.create_all()
        _seed_demo_data(app)
        _seed_admin_user(app)

    return app


def _seed_demo_data(app):
    """Seed some demo carriers and alerts if database is empty."""
    from models.carrier import Carrier
    from models.sla import Alert
    from models import db

    if Carrier.query.count() > 0:
        return  # Already seeded

    # Create demo carriers
    carriers_data = [
        {'name': 'FedEx', 'slug': 'fedex', 'logo_color': '#4D148C', 'description': 'Global express delivery services'},
        {'name': 'DHL', 'slug': 'dhl', 'logo_color': '#FFCC00', 'description': 'International logistics and courier'},
        {'name': 'UPS', 'slug': 'ups', 'logo_color': '#351C15', 'description': 'United Parcel Service logistics'},
    ]

    for cd in carriers_data:
        carrier = Carrier(**cd)
        db.session.add(carrier)

    db.session.flush()  # Get IDs

    # Create demo alerts
    fedex = Carrier.query.filter_by(slug='fedex').first()
    dhl = Carrier.query.filter_by(slug='dhl').first()
    ups = Carrier.query.filter_by(slug='ups').first()

    demo_alerts = [
        Alert(carrier_id=fedex.id, title="FedEx Claim Window Closing Soon",
              message="FedEx SLA Clause 4.2 — Claim window closes in 5 days. Review shipment #FX-8832 immediately.",
              level='WARNING', clause_reference='4.2', days_remaining=5),
        Alert(carrier_id=ups.id, title="UPS Damage Claim CRITICAL",
              message="UPS SLA Clause 6.1 — Damage claim deadline is TOMORROW. File claim for shipment #UP-2291 now.",
              level='CRITICAL', clause_reference='6.1', days_remaining=1),
        Alert(carrier_id=dhl.id, title="DHL SLA Renewal Approaching",
              message="DHL contract expires in 28 days. Review terms and initiate renewal process.",
              level='INFO', clause_reference='12.1', days_remaining=28),
        Alert(carrier_id=fedex.id, title="FedEx SLA v2.1 Uploaded",
              message="FedEx SLA version 2.1 has been uploaded and processed successfully. 4 key clauses extracted.",
              level='INFO', clause_reference=None, days_remaining=None),
    ]

    for alert in demo_alerts:
        db.session.add(alert)

    db.session.commit()
    app.logger.info("Demo data seeded successfully.")


def _seed_admin_user(app):
    """Seed a default admin user if none exists."""
    from models.user import User
    from models import db

    if User.query.filter_by(role='admin').count() > 0:
        return  # Already has an admin

    admin = User(
        email='admin@zentara.com',
        full_name='ZenTara Admin',
        role='admin',
        auth_provider='email',
    )
    admin.set_password('admin123')
    db.session.add(admin)
    db.session.commit()
    app.logger.info("Default admin user created: admin@zentara.com / admin123")


if __name__ == '__main__':
    app = create_app('development')
    app.run(debug=True, host='0.0.0.0', port=5000)
