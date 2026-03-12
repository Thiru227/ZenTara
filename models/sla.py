from models import db
from datetime import datetime


class SLADocument(db.Model):
    __tablename__ = 'sla_documents'

    id = db.Column(db.Integer, primary_key=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    version_label = db.Column(db.String(50), nullable=False, default='v1.0')
    file_path = db.Column(db.String(500), nullable=False)
    page_count = db.Column(db.Integer, default=0)
    file_size = db.Column(db.Integer, default=0)
    branch_name = db.Column(db.String(100), nullable=True, default='main')
    is_active = db.Column(db.Boolean, default=True)
    processing_status = db.Column(db.String(50), default='pending')  # pending, processing, done, error
    extracted_text = db.Column(db.Text, default='')
    clause_summary = db.Column(db.Text, default='')
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    clauses = db.relationship('ExtractedClause', backref='sla_document', lazy=True, cascade='all, delete-orphan')
    deadlines = db.relationship('Deadline', backref='sla_document', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'carrier_id': self.carrier_id,
            'filename': self.filename,
            'original_filename': self.original_filename,
            'version_label': self.version_label,
            'page_count': self.page_count,
            'file_size': self.file_size,
            'tags': self.tags.split(',') if self.tags else [],
            'is_active': self.is_active,
            'processing_status': self.processing_status,
            'upload_date': self.upload_date.isoformat() if self.upload_date else None
        }


class ExtractedClause(db.Model):
    __tablename__ = 'extracted_clauses'

    id = db.Column(db.Integer, primary_key=True)
    sla_document_id = db.Column(db.Integer, db.ForeignKey('sla_documents.id'), nullable=False)
    clause_type = db.Column(db.String(100), nullable=False)  # claim_deadline, liability, penalty, etc.
    clause_title = db.Column(db.String(200), nullable=False)
    clause_text = db.Column(db.Text, nullable=False)
    clause_number = db.Column(db.String(20), default='')
    page_number = db.Column(db.Integer, default=0)
    extracted_value = db.Column(db.String(500), default='')  # e.g. "30 days", "$100 per shipment"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    CLAUSE_ICONS = {
        'claim_deadline': '📋',
        'liability': '💰',
        'penalty': '⚠️',
        'pickup_commitment': '⏰',
        'payment_terms': '💳',
        'dispute_resolution': '⚖️',
        'general': '📄'
    }

    @property
    def icon(self):
        return self.CLAUSE_ICONS.get(self.clause_type, '📄')

    def to_dict(self):
        return {
            'id': self.id,
            'clause_type': self.clause_type,
            'clause_title': self.clause_title,
            'clause_text': self.clause_text,
            'clause_number': self.clause_number,
            'page_number': self.page_number,
            'extracted_value': self.extracted_value,
            'icon': self.icon
        }


class Deadline(db.Model):
    __tablename__ = 'deadlines'

    id = db.Column(db.Integer, primary_key=True)
    sla_document_id = db.Column(db.Integer, db.ForeignKey('sla_documents.id'), nullable=False)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default='')
    clause_reference = db.Column(db.String(50), default='')
    deadline_date = db.Column(db.DateTime, nullable=True)
    days_window = db.Column(db.Integer, default=0)  # e.g. "30 days from delivery"
    deadline_type = db.Column(db.String(50), default='recurring')  # fixed, recurring
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def days_until(self):
        if self.deadline_date:
            delta = self.deadline_date - datetime.utcnow()
            return delta.days
        return None

    @property
    def alert_level(self):
        days = self.days_until
        if days is None:
            return 'INFO'
        if days <= 2:
            return 'CRITICAL'
        elif days <= 7:
            return 'WARNING'
        elif days <= 30:
            return 'INFO'
        return None


class Alert(db.Model):
    __tablename__ = 'alerts'

    id = db.Column(db.Integer, primary_key=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'), nullable=False)
    sla_document_id = db.Column(db.Integer, db.ForeignKey('sla_documents.id'), nullable=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    level = db.Column(db.String(20), default='INFO')  # INFO, WARNING, CRITICAL
    clause_reference = db.Column(db.String(50), default='')
    days_remaining = db.Column(db.Integer, nullable=True)
    dismissed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def level_color(self):
        colors = {'INFO': '#4ECDC4', 'WARNING': '#FFB347', 'CRITICAL': '#FF3B30'}
        return colors.get(self.level, '#4ECDC4')

    @property
    def level_emoji(self):
        emojis = {'INFO': '🟢', 'WARNING': '🟡', 'CRITICAL': '🔴'}
        return emojis.get(self.level, '🟢')

    def to_dict(self):
        return {
            'id': self.id,
            'carrier_id': self.carrier_id,
            'title': self.title,
            'message': self.message,
            'level': self.level,
            'level_color': self.level_color,
            'level_emoji': self.level_emoji,
            'clause_reference': self.clause_reference,
            'days_remaining': self.days_remaining,
            'dismissed': self.dismissed,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class PerformanceMetric(db.Model):
    __tablename__ = 'performance_metrics'

    id = db.Column(db.Integer, primary_key=True)
    carrier_id = db.Column(db.Integer, db.ForeignKey('carriers.id'), nullable=False)
    metric_date = db.Column(db.DateTime, default=datetime.utcnow)
    on_time_delivery_pct = db.Column(db.Float, default=0.0)
    claim_resolution_days = db.Column(db.Float, default=0.0)
    dispute_win_rate = db.Column(db.Float, default=0.0)
    cost_per_shipment = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, default='')

    def to_dict(self):
        return {
            'id': self.id,
            'carrier_id': self.carrier_id,
            'metric_date': self.metric_date.isoformat() if self.metric_date else None,
            'on_time_delivery_pct': self.on_time_delivery_pct,
            'claim_resolution_days': self.claim_resolution_days,
            'dispute_win_rate': self.dispute_win_rate,
            'cost_per_shipment': self.cost_per_shipment
        }
