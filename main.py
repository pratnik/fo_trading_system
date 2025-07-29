"""
Main entry point for the F&O Trading System
-------------------------------------------
Starts:
  • Event-calendar initialisation & auto-refresh
  • Database connectivity check
  • Strategy selector bootstrap
  • Risk monitor
  • Celery worker / beat (optional CLI flags)
  • Streamlit dashboard
Handles graceful shutdown and logs critical failures.

Run:
    python main.py                  # normal mode
    python main.py --headless       # without Streamlit UI
    python main.py --worker         # launch only Celery worker
    python main.py --beat           # launch only Celery beat scheduler
"""

import os
import sys
import logging
import argparse
import signal
import subprocess
from datetime import datetime

# -------------------------------------------------
# Project imports
# -------------------------------------------------
from app.config import settings
from app.db.base import db_manager
from app.utils.event_calendar import event_calendar
from app.risk.risk_monitor import start_risk_monitoring, stop_risk_monitoring
from app.utils.healthcheck import quick_health_check
from app.tasks.celery_config import celery_app  # ensures tasks are registered

logger = logging.getLogger("main")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# -------------------------------------------------
# Helper functions
# -------------------------------------------------
def init_database() -> None:
    """Validate DB connectivity before starting anything else."""
    logger.info("🔗 Checking database connectivity …")
    if not db_manager.check_connection():
        logger.critical("❌ Database connection FAILED – aborting startup")
        sys.exit(1)
    logger.info("✅ Database connection OK")


def init_event_calendar() -> None:
    """Initialise event calendar and refresh if needed."""
    logger.info("📅 Initialising event calendar …")
    event_calendar.auto_refresh_check()
    logger.info("✅ Event calendar ready – last refresh %s",
                event_calendar.last_holiday_refresh.strftime("%d-%m %H:%M"))


def launch_streamlit() -> subprocess.Popen:
    """Start the Streamlit dashboard as a subprocess."""
    dash_cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "app/ui/dashboard.py",
        "--server.port",
        str(os.getenv("PORT", 8501)),
        "--server.address",
        "0.0.0.0",
        "--server.headless",
        "true",
    ]
    logger.info("🌐 Launching Streamlit dashboard …")
    return subprocess.Popen(dash_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def launch_celery_worker() -> subprocess.Popen:
    """Start Celery worker."""
    cmd = ["celery", "-A", "app.tasks.celery_tasks", "worker", "--loglevel=info"]
    logger.info("🚜 Launching Celery worker …")
    return subprocess.Popen(cmd)


def launch_celery_beat() -> subprocess.Popen:
    """Start Celery beat scheduler."""
    cmd = ["celery", "-A", "app.tasks.celery_tasks", "beat", "--loglevel=info"]
    logger.info("⏰ Launching Celery beat …")
    return subprocess.Popen(cmd)


def graceful_shutdown(processes):
    """Terminate spawned subprocesses and stop risk monitor."""
    logger.info("🛑 Initiating graceful shutdown …")
    stop_risk_monitoring()
    for proc in processes:
        if proc and proc.poll() is None:  # still running
            logger.info("Terminating %s …", proc.args[0])
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    logger.info("Shutdown complete – bye 👋")
    sys.exit(0)


def register_signals(processes):
    """Register SIGTERM & SIGINT handlers for graceful shutdown."""

    def _handler(signum, frame):
        logger.warning("Signal %s received", signum)
        graceful_shutdown(processes)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


# -------------------------------------------------
# Main start-up routine
# -------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true",
                        help="Run without Streamlit UI")
    parser.add_argument("--worker", action="store_true",
                        help="Run only Celery worker")
    parser.add_argument("--beat", action="store_true",
                        help="Run only Celery beat scheduler")
    args = parser.parse_args()

    # 1️⃣  Health check
    if not quick_health_check():
        logger.critical("❌ System health FAIL – aborting")
        sys.exit(1)

    # 2️⃣  Database + calendar init
    init_database()
    init_event_calendar()

    # 3️⃣  Start risk monitor (in its own thread)
    start_risk_monitoring()

    # 4️⃣  Spawn requested subprocesses
    spawned = []
    if st.button("SOS emergency Stop",use_container_width=True, type="primary"):
      st.error("ALL TRADING HALTED!")
      #add code to stop strategies here pending
      st.stop()
    if args.worker:
        spawned.append(launch_celery_worker())
    elif args.beat:
        spawned.append(launch_celery_beat())
    else:
        # Default full stack
        spawned.append(launch_celery_worker())
        spawned.append(launch_celery_beat())
        if not args.headless:
            spawned.append(launch_streamlit())

    # 5️⃣  Register signal handlers
    register_signals(spawned)

    # 6️⃣  Wait indefinitely while subprocesses run
    try:
        while True:
            for proc in list(spawned):
                if proc.poll() is not None:  # a child exited
                    logger.error("Subprocess %s exited with code %s",
                                 proc.args[0], proc.returncode)
                    graceful_shutdown(spawned)
            signal.pause()  # wait for signals
    except Exception as exc:
        logger.exception("Unexpected error in main loop: %s", exc)
        graceful_shutdown(spawned)


if __name__ == "__main__":
    main()
