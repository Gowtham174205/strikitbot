"""
Gunicorn Configuration — STRIKIT Bot (Production)

Usage:
    gunicorn app.main:app -c gunicorn.conf.py

Environment overrides:
    WEB_CONCURRENCY  — Number of worker processes (default: 4)
"""

import multiprocessing
import os
from pathlib import Path

# ── Server Socket ───────────────────────────────────────────────────────────
bind = "0.0.0.0:5000"
backlog = 2048

# ── Worker Processes ────────────────────────────────────────────────────────
workers = int(os.environ.get("WEB_CONCURRENCY", 4))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000
threads = 1  # not used with async workers, but set for safety

# ── Worker Lifecycle ────────────────────────────────────────────────────────
# Recycle workers after N requests to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# ── Timeouts ────────────────────────────────────────────────────────────────
timeout = 120            # Kill worker if it doesn't respond within 120s
keepalive = 5            # Keep-alive connections wait 5s for next request
graceful_timeout = 30    # Time to finish serving requests after SIGTERM

# ── Application Loading ────────────────────────────────────────────────────
preload_app = True       # Load app before forking workers (saves memory via COW)

# ── Logging ─────────────────────────────────────────────────────────────────
_logs_dir = Path(__file__).resolve().parent / "logs"
_logs_dir.mkdir(exist_ok=True)

accesslog = str(_logs_dir / "access.log")
errorlog = str(_logs_dir / "error.log")
loglevel = os.environ.get("LOG_LEVEL", "info")
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sμs'

# ── Process Naming ──────────────────────────────────────────────────────────
proc_name = "strikit-bot"

# ── Server Mechanics ────────────────────────────────────────────────────────
# Restart workers if the app code changes (disable in production if desired)
reload = False

# Forward proxy headers (X-Forwarded-For, etc.)
forwarded_allow_ips = "*"
proxy_protocol = False
proxy_allow_from = "*"

# ── Security ────────────────────────────────────────────────────────────────
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# ── Hooks ───────────────────────────────────────────────────────────────────
def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("STRIKIT Bot — Starting Gunicorn master process")
    server.log.info(f"Workers: {workers} | Bind: {bind} | Worker class: {worker_class}")


def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info(f"Worker spawned (pid: {worker.pid})")


def pre_exec(server):
    """Called just before a new master process is forked (on SIGHUP)."""
    server.log.info("Forking new master process")


def worker_exit(server, worker):
    """Called when a worker exits."""
    server.log.info(f"Worker exited (pid: {worker.pid})")


def on_exit(server):
    """Called just before exiting Gunicorn."""
    server.log.info("STRIKIT Bot — Gunicorn master shutting down")
