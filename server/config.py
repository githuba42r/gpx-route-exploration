import os


class Config:
    VALHALLA_URL = os.environ.get("VALHALLA_URL", "http://10.0.1.25:8002")
    NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "http://10.0.1.25:8001")
    DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")
    AUTH_USER_HEADER = os.environ.get("AUTH_USER_HEADER", "Remote-User")
    BACKUP_ENABLED = os.environ.get("BACKUP_ENABLED", "true").lower() == "true"
    BACKUP_INTERVAL_HOURS = int(os.environ.get("BACKUP_INTERVAL_HOURS", "1"))
    BACKUP_DAILY_KEEP = int(os.environ.get("BACKUP_DAILY_KEEP", "7"))
    BACKUP_WEEKLY_KEEP = int(os.environ.get("BACKUP_WEEKLY_KEEP", "6"))
    BACKUP_MONTHLY_KEEP = int(os.environ.get("BACKUP_MONTHLY_KEEP", "13"))
    NOMINATIM_RATE_LIMIT_MS = int(os.environ.get("NOMINATIM_RATE_LIMIT_MS", "1000"))
    CSV_MAX_BYTES = int(os.environ.get("CSV_MAX_BYTES", str(1024 * 1024)))
    CSV_MAX_ROWS = int(os.environ.get("CSV_MAX_ROWS", "200"))
