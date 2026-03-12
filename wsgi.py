"""
WSGI entry point for Render / Gunicorn.
Usage: gunicorn wsgi:app -c gunicorn.conf.py
"""
import os
from app import create_app

config_name = os.environ.get('FLASK_CONFIG', 'production')
app = create_app(config_name)
