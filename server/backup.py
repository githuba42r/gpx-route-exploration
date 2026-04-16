import logging
import os
import shutil
import sqlite3
import tarfile
import tempfile
import threading
from datetime import date

logger = logging.getLogger(__name__)


def create_backup(data_dir, today=None):
    """Create a daily backup tarball containing routes.db and gpx/ tree.

    Uses the sqlite3 backup API for a consistent DB snapshot. If today's
    backup already exists, returns the existing path without overwriting.

    Returns the path to the backup tarball.
    """
    if today is None:
        today = date.today()

    daily_dir = os.path.join(data_dir, "backups", "daily")
    os.makedirs(daily_dir, exist_ok=True)

    backup_name = f"backup-{today.isoformat()}.tar.gz"
    backup_path = os.path.join(daily_dir, backup_name)

    if os.path.exists(backup_path):
        logger.info("Today's backup already exists: %s", backup_path)
        return backup_path

    db_path = os.path.join(data_dir, "routes.db")
    gpx_dir = os.path.join(data_dir, "gpx")

    # Use a temp file within data_dir to avoid cross-device issues.
    tmp_fd, tmp_db_path = tempfile.mkstemp(dir=data_dir, suffix=".db")
    os.close(tmp_fd)

    try:
        # Consistent DB copy via sqlite3 backup API.
        src_conn = sqlite3.connect(db_path)
        dst_conn = sqlite3.connect(tmp_db_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
            src_conn.close()

        # Build the tarball.
        with tarfile.open(backup_path, "w:gz") as tar:
            tar.add(tmp_db_path, arcname="routes.db")
            if os.path.isdir(gpx_dir):
                tar.add(gpx_dir, arcname="gpx")
    finally:
        if os.path.exists(tmp_db_path):
            os.unlink(tmp_db_path)

    logger.info("Created backup: %s", backup_path)
    return backup_path


def promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13):
    """Promote oldest files from each tier when count exceeds the keep threshold.

    Tier chain: daily -> weekly -> monthly -> yearly.
    Yearly backups are never purged.
    """
    tiers = [
        ("daily", daily_keep, "weekly"),
        ("weekly", weekly_keep, "monthly"),
        ("monthly", monthly_keep, "yearly"),
    ]

    for tier_name, keep, next_tier_name in tiers:
        tier_dir = os.path.join(data_dir, "backups", tier_name)
        if not os.path.isdir(tier_dir):
            continue

        files = sorted(
            f for f in os.listdir(tier_dir) if f.endswith(".tar.gz")
        )
        overflow_count = len(files) - keep
        if overflow_count <= 0:
            continue

        next_tier_dir = os.path.join(data_dir, "backups", next_tier_name)
        os.makedirs(next_tier_dir, exist_ok=True)

        # Oldest files are at the start of the sorted list.
        for fname in files[:overflow_count]:
            src = os.path.join(tier_dir, fname)
            dst = os.path.join(next_tier_dir, fname)
            shutil.move(src, dst)
            logger.info("Promoted %s -> %s", src, dst)


def start_backup_scheduler(app):
    """Start a daemon timer that runs backups at the configured interval."""
    if not app.config.get("BACKUP_ENABLED", True):
        logger.info("Backup system disabled (BACKUP_ENABLED=False)")
        return

    data_dir = app.config["DATA_DIR"]
    interval_seconds = app.config.get("BACKUP_INTERVAL_HOURS", 1) * 3600
    daily_keep = app.config.get("BACKUP_DAILY_KEEP", 7)
    weekly_keep = app.config.get("BACKUP_WEEKLY_KEEP", 6)
    monthly_keep = app.config.get("BACKUP_MONTHLY_KEEP", 13)

    def run_backup():
        try:
            create_backup(data_dir)
            promote_and_purge(
                data_dir,
                daily_keep=daily_keep,
                weekly_keep=weekly_keep,
                monthly_keep=monthly_keep,
            )
        except Exception:
            logger.exception("Backup run failed")
        finally:
            # Reschedule after every run regardless of success/failure.
            _schedule(interval_seconds, run_backup)

    _schedule(interval_seconds, run_backup)
    logger.info(
        "Backup scheduler started (interval=%dh)", app.config.get("BACKUP_INTERVAL_HOURS", 1)
    )


def _schedule(interval_seconds, fn):
    timer = threading.Timer(interval_seconds, fn)
    timer.daemon = True
    timer.start()
    return timer
