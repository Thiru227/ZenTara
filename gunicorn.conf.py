"""
Gunicorn configuration for Render production deployment.
"""
import os
import multiprocessing

# ── Server Socket ───────────────────────────────
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# ── Workers ─────────────────────────────────────
# Render free tier: 512MB RAM → 2 workers max
# Render paid:      use (2 × CPU) + 1
workers = int(os.environ.get('WEB_CONCURRENCY', 2))
worker_class = 'gthread'
threads = 2

# ── Timeouts ────────────────────────────────────
# AI/PDF processing can be slow; allow up to 120s
timeout = 120
graceful_timeout = 30
keepalive = 5

# ── Logging ─────────────────────────────────────
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('LOG_LEVEL', 'info')

# ── Security ────────────────────────────────────
forwarded_allow_ips = '*'  # Trust Render's proxy headers
proxy_protocol = False

# ── Preload ─────────────────────────────────────
preload_app = True

# ── Server Hooks ────────────────────────────────
def on_starting(server):
    print("🧘 ZenTara is starting on Render...")

def when_ready(server):
    print("🧘 ZenTara is ready to serve requests!")
