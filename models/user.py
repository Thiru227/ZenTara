"""
User model for ZenTara authentication.
Supports email/password and Google OAuth.
"""
from datetime import datetime
from models import db
from werkzeug.security import generate_password_hash, check_password_hash


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=True)   # Null for OAuth-only users
    full_name = db.Column(db.String(120), nullable=False, default='')
    avatar_url = db.Column(db.String(500), nullable=True)      # Google profile picture
    role = db.Column(db.String(20), nullable=False, default='user')  # 'user' or 'admin'
    auth_provider = db.Column(db.String(20), nullable=False, default='email')  # 'email' or 'google'
    google_id = db.Column(db.String(200), nullable=True, unique=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def display_name(self):
        return self.full_name or self.email.split('@')[0]

    @property
    def initials(self):
        parts = self.display_name.strip().split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.display_name[:2].upper()

    def __repr__(self):
        return f'<User {self.email} ({self.role})>'
