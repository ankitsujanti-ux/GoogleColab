# main.py
"""
Main entry point for Medication Adherence Dashboard.
Production-ready: startup checks, Data dir creation when running as exe,
port fallback, and clear error messages so it runs on any machine.
"""
import logging
import os
import sys

# Production-ready logging: configurable level via LOG_LEVEL env (default INFO)
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _production_startup():
    """Run on startup: when frozen create Data dir, warn if .env missing, always show where data file is expected."""
    try:
        from runtime_paths import get_app_dir
        app_dir = get_app_dir()
        if getattr(sys, "frozen", False):
            data_dir = app_dir / "Data"
            if not data_dir.exists():
                data_dir.mkdir(parents=True, exist_ok=True)
                logger.info("Created Data folder: %s", data_dir)
            env_file = app_dir / ".env"
            env_cwd = os.path.join(os.getcwd(), ".env")
            env_example = app_dir / ".env.example"
            if env_file.exists():
                logger.info("Loading .env from exe folder: %s", env_file)
            elif os.path.isfile(env_cwd):
                logger.info("Loading .env from current folder: %s", env_cwd)
            if not env_file.exists() and not os.path.isfile(env_cwd):
                if env_example.exists():
                    logger.info(
                        " .env not found. Copy .env.example to .env in this folder if you want to change the port, data file, or enable notifications (Pushover, Twilio, etc.): %s",
                        app_dir,
                    )
                else:
                    logger.info(
                        " .env not found. You can create a .env file to customize PORT, EXCEL_PATH, and optional notification API keys (see README)."
                    )
        try:
            from config import EXCEL_PATH
            excel_exists = os.path.isfile(EXCEL_PATH)
            logger.info("Data file: %s", EXCEL_PATH)
            if not excel_exists:
                logger.warning("File not found - put patients.xlsx in the Data folder or run: python generate_patients_excel.py -n 500")
            else:
                logger.info("Data file found - dashboard will load from this file.")
        except Exception:
            pass
    except Exception as e:
        logger.warning("Startup check: %s", e)

def _find_available_port(start_port: int, max_tries: int = 10) -> int:
    """Try binding to start_port, then start_port+1, ... until one is free."""
    import socket
    for i in range(max_tries):
        port = start_port + i
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("", port))
                return port
        except OSError:
            continue
    return start_port  # fallback to original

if __name__ == "__main__":
    _production_startup()

    try:
        port = int(os.getenv("PORT", "5000"))
    except ValueError:
        port = 5000
        logger.warning("Invalid PORT in env, using 5000")
    if port <= 0 or port > 65535:
        port = 5000
        logger.warning("PORT out of range, using 5000")
    debug = os.getenv("FLASK_DEBUG", "false").strip().lower() in ("1", "true", "yes")
    # Cloud hosts (Render/Railway/etc.) assign PORT — bind exactly to it.
    # Locally, fall back to the next free port if the preferred one is busy.
    on_cloud = any(
        os.getenv(k)
        for k in ("RENDER", "RAILWAY_ENVIRONMENT", "FLY_APP_NAME", "WEBSITE_INSTANCE_ID")
    )
    if not on_cloud:
        port = _find_available_port(port)

    logger.info("Starting Medication Adherence Dashboard...")
    logger.info("Backend API: http://localhost:%s", port)
    if not debug:
        logger.info("Production mode (set FLASK_DEBUG=true for development).")

    try:
        from app_flask import app, socketio
        # allow_unsafe_werkzeug needed so the bundled server can run on cloud free tiers
        socketio.run(
            app,
            debug=debug,
            host="0.0.0.0",
            port=port,
            allow_unsafe_werkzeug=True,
        )
    except OSError as e:
        if "address already in use" in str(e).lower() or "10048" in str(e):
            logger.error("Port %s is in use. Set PORT in .env to another port (e.g. 5001).", port)
        raise
    except Exception as e:
        logger.exception("Failed to start")
        raise
 