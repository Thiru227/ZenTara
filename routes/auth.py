"""
Authentication routes — Login, Signup, Logout, Google OAuth.
"""
import functools
import json
import os
import urllib.parse

import requests
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app, abort)
from models import db
from models.user import User

auth_bp = Blueprint('auth', __name__)


# ── Decorators ──────────────────────────────────────────────────────

def login_required(f):
    """Redirect to login if user is not authenticated."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('auth.login', next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    """Restrict to admin users only."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'error')
            return redirect(url_for('auth.login', next=request.path))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Helper to get the logged-in user object, or None."""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None


# ── Login ───────────────────────────────────────────────────────────

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'error')
            return render_template('auth.html', mode='login')

        user = User.query.filter_by(email=email).first()

        if not user:
            flash('No account found with that email.', 'error')
            return render_template('auth.html', mode='login')

        if user.auth_provider == 'google' and not user.password_hash:
            flash('This account uses Google Sign-In. Please click "Continue with Google".', 'error')
            return render_template('auth.html', mode='login')

        if not user.check_password(password):
            flash('Incorrect password.', 'error')
            return render_template('auth.html', mode='login')

        if not user.is_active:
            flash('Your account has been deactivated. Contact an admin.', 'error')
            return render_template('auth.html', mode='login')

        # Success
        _login_user(user)
        next_url = request.args.get('next') or request.form.get('next') or url_for('dashboard.dashboard')
        return redirect(next_url)

    return render_template('auth.html', mode='login')


# ── Signup ──────────────────────────────────────────────────────────

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('dashboard.dashboard'))

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        errors = []
        if not full_name:
            errors.append('Full name is required.')
        if not email or '@' not in email:
            errors.append('A valid email is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')

        if User.query.filter_by(email=email).first():
            errors.append('An account with this email already exists.')

        if errors:
            for err in errors:
                flash(err, 'error')
            return render_template('auth.html', mode='signup',
                                   form_name=full_name, form_email=email)

        user = User(
            email=email,
            full_name=full_name,
            auth_provider='email',
            role='user',
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        _login_user(user)
        flash(f'Welcome to ZenTara, {user.display_name}! 🧘', 'success')
        return redirect(url_for('dashboard.dashboard'))

    return render_template('auth.html', mode='signup')


# ── Logout ──────────────────────────────────────────────────────────

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ── Google OAuth ────────────────────────────────────────────────────

GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
GOOGLE_USERINFO_URL = 'https://www.googleapis.com/oauth2/v2/userinfo'


@auth_bp.route('/auth/google')
def google_login():
    """Redirect user to Google OAuth consent screen."""
    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    if not client_id:
        flash('Google Sign-In is not configured. Please use email/password.', 'error')
        return redirect(url_for('auth.login'))

    redirect_uri = url_for('auth.google_callback', _external=True)
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'offline',
        'prompt': 'select_account',
    }
    return redirect(f'{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}')


@auth_bp.route('/auth/google/callback')
def google_callback():
    """Handle the Google OAuth callback."""
    error = request.args.get('error')
    if error:
        flash(f'Google login cancelled: {error}', 'error')
        return redirect(url_for('auth.login'))

    code = request.args.get('code')
    if not code:
        flash('Invalid response from Google.', 'error')
        return redirect(url_for('auth.login'))

    client_id = current_app.config.get('GOOGLE_CLIENT_ID')
    client_secret = current_app.config.get('GOOGLE_CLIENT_SECRET')
    redirect_uri = url_for('auth.google_callback', _external=True)

    # Exchange code for token
    try:
        token_resp = requests.post(GOOGLE_TOKEN_URL, data={
            'code': code,
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }, timeout=10)
        token_data = token_resp.json()
    except Exception:
        flash('Failed to connect to Google. Please try again.', 'error')
        return redirect(url_for('auth.login'))

    if 'access_token' not in token_data:
        flash('Google authentication failed.', 'error')
        return redirect(url_for('auth.login'))

    # Get user info
    try:
        userinfo_resp = requests.get(GOOGLE_USERINFO_URL, headers={
            'Authorization': f'Bearer {token_data["access_token"]}'
        }, timeout=10)
        userinfo = userinfo_resp.json()
    except Exception:
        flash('Failed to get user info from Google.', 'error')
        return redirect(url_for('auth.login'))

    google_id = userinfo.get('id')
    email = userinfo.get('email', '').lower()
    name = userinfo.get('name', '')
    avatar = userinfo.get('picture', '')

    if not email:
        flash('Google did not provide an email.', 'error')
        return redirect(url_for('auth.login'))

    # Find or create user
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        user = User.query.filter_by(email=email).first()

    if user:
        # Update existing user with Google info
        if not user.google_id:
            user.google_id = google_id
        if not user.avatar_url:
            user.avatar_url = avatar
        if user.auth_provider == 'email':
            user.auth_provider = 'both'
    else:
        # Create new user
        user = User(
            email=email,
            full_name=name,
            avatar_url=avatar,
            google_id=google_id,
            auth_provider='google',
            role='user',
        )
        db.session.add(user)

    if not user.is_active:
        flash('Your account has been deactivated. Contact an admin.', 'error')
        return redirect(url_for('auth.login'))

    db.session.commit()
    _login_user(user)
    flash(f'Welcome, {user.display_name}! 🧘', 'success')
    return redirect(url_for('dashboard.dashboard'))


# ── Admin Panel ─────────────────────────────────────────────────────

@auth_bp.route('/admin/users')
@admin_required
def admin_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)


@auth_bp.route('/admin/users/<int:user_id>/toggle-active', methods=['POST'])
@admin_required
def toggle_user_active(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash("You can't deactivate your own account.", 'error')
        return redirect(url_for('auth.admin_users'))
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    flash(f'{user.display_name} has been {status}.', 'success')
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@admin_required
def toggle_user_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash("You can't change your own role.", 'error')
        return redirect(url_for('auth.admin_users'))
    user.role = 'user' if user.role == 'admin' else 'admin'
    db.session.commit()
    flash(f'{user.display_name} is now {"an admin" if user.is_admin else "a regular user"}.', 'success')
    return redirect(url_for('auth.admin_users'))


@auth_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == session.get('user_id'):
        flash("You can't delete your own account.", 'error')
        return redirect(url_for('auth.admin_users'))
    name = user.display_name
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{name}" has been deleted.', 'success')
    return redirect(url_for('auth.admin_users'))


# ── Helpers ─────────────────────────────────────────────────────────

def _login_user(user):
    """Set session variables for the user."""
    user.last_login = datetime.utcnow()
    db.session.commit()
    session['user_id'] = user.id
    session['user_email'] = user.email
    session['user_name'] = user.display_name
    session['user_role'] = user.role
    session['user_avatar'] = user.avatar_url or ''
