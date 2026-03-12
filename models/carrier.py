from models import db
from datetime import datetime


class Carrier(db.Model):
    __tablename__ = 'carriers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    slug = db.Column(db.String(100), nullable=False, unique=True)
    logo_color = db.Column(db.String(7), default='#FF6B6B')
    description = db.Column(db.Text, default='')
    website = db.Column(db.String(200), default='')
    contact_email = db.Column(db.String(200), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sla_documents = db.relationship('SLADocument', backref='carrier', lazy=True, cascade='all, delete-orphan')
    alerts = db.relationship('Alert', backref='carrier', lazy=True, cascade='all, delete-orphan')

    @property
    def active_sla(self):
        from models.sla import SLADocument
        return SLADocument.query.filter_by(carrier_id=self.id, is_active=True).first()

    @property
    def sla_count(self):
        return len(self.sla_documents)

    @property
    def health_score(self):
        """Calculate carrier health score based on active alerts"""
        from models.sla import Alert
        critical = Alert.query.filter_by(carrier_id=self.id, level='CRITICAL', dismissed=False).count()
        warning = Alert.query.filter_by(carrier_id=self.id, level='WARNING', dismissed=False).count()
        if critical > 0:
            return max(0, 40 - (critical * 20))
        if warning > 0:
            return max(40, 70 - (warning * 10))
        return 95

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'logo_color': self.logo_color,
            'description': self.description,
            'sla_count': self.sla_count,
            'health_score': self.health_score,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @staticmethod
    def make_slug(name):
        import re
        slug = name.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_-]+', '-', slug)
        slug = re.sub(r'^-+|-+$', '', slug)
        return slug
