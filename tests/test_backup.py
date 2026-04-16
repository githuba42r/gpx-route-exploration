import os
import sqlite3
import tarfile
from datetime import date, timedelta

import pytest

from server.backup import create_backup, promote_and_purge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_data_dir(tmp_path):
    data_dir = str(tmp_path / "data")
    os.makedirs(os.path.join(data_dir, "gpx", "testuser", "default"), exist_ok=True)
    db_path = os.path.join(data_dir, "routes.db")
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test (id INTEGER)")
    conn.execute("INSERT INTO test VALUES (1)")
    conn.commit()
    conn.close()
    with open(os.path.join(data_dir, "gpx", "testuser", "default", "test.gpx"), "w") as f:
        f.write("<gpx/>")
    return data_dir


def _make_empty_tarball(path):
    """Create an empty (but valid) .tar.gz at *path*."""
    with tarfile.open(path, "w:gz"):
        pass


def _fill_tier(tier_dir, count, base_date=None):
    """Create *count* empty tarballs in *tier_dir* at consecutive dates."""
    if base_date is None:
        base_date = date.today()
    os.makedirs(tier_dir, exist_ok=True)
    paths = []
    for i in range(count):
        d = base_date - timedelta(days=i)
        path = os.path.join(tier_dir, f"backup-{d.isoformat()}.tar.gz")
        _make_empty_tarball(path)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_daily_backup(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    backup_path = create_backup(data_dir)
    daily_dir = os.path.join(data_dir, "backups", "daily")
    assert os.path.isdir(daily_dir)
    assert os.path.isfile(backup_path)
    assert backup_path.startswith(daily_dir)
    assert backup_path.endswith(".tar.gz")


def test_backup_contains_db_and_gpx(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    backup_path = create_backup(data_dir)

    extract_dir = str(tmp_path / "extracted")
    os.makedirs(extract_dir)
    with tarfile.open(backup_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    assert os.path.isfile(os.path.join(extract_dir, "routes.db"))
    assert os.path.isfile(
        os.path.join(extract_dir, "gpx", "testuser", "default", "test.gpx")
    )


def test_skip_duplicate_daily(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    path1 = create_backup(data_dir)
    path2 = create_backup(data_dir)
    assert path1 == path2
    # Only one file should be present.
    daily_dir = os.path.join(data_dir, "backups", "daily")
    files = [f for f in os.listdir(daily_dir) if f.endswith(".tar.gz")]
    assert len(files) == 1


def test_daily_purge_promotes_to_weekly(tmp_path):
    data_dir = str(tmp_path / "data")
    daily_dir = os.path.join(data_dir, "backups", "daily")
    weekly_dir = os.path.join(data_dir, "backups", "weekly")
    _fill_tier(daily_dir, 8)

    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)

    daily_files = [f for f in os.listdir(daily_dir) if f.endswith(".tar.gz")]
    weekly_files = [f for f in os.listdir(weekly_dir) if f.endswith(".tar.gz")]
    assert len(daily_files) == 7
    assert len(weekly_files) == 1


def test_weekly_purge_promotes_to_monthly(tmp_path):
    data_dir = str(tmp_path / "data")
    weekly_dir = os.path.join(data_dir, "backups", "weekly")
    monthly_dir = os.path.join(data_dir, "backups", "monthly")
    _fill_tier(weekly_dir, 7)

    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)

    weekly_files = [f for f in os.listdir(weekly_dir) if f.endswith(".tar.gz")]
    monthly_files = [f for f in os.listdir(monthly_dir) if f.endswith(".tar.gz")]
    assert len(weekly_files) == 6
    assert len(monthly_files) == 1


def test_monthly_purge_promotes_to_yearly(tmp_path):
    data_dir = str(tmp_path / "data")
    monthly_dir = os.path.join(data_dir, "backups", "monthly")
    yearly_dir = os.path.join(data_dir, "backups", "yearly")
    _fill_tier(monthly_dir, 14)

    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)

    monthly_files = [f for f in os.listdir(monthly_dir) if f.endswith(".tar.gz")]
    yearly_files = [f for f in os.listdir(yearly_dir) if f.endswith(".tar.gz")]
    assert len(monthly_files) == 13
    assert len(yearly_files) == 1


def test_yearly_never_purged(tmp_path):
    data_dir = str(tmp_path / "data")
    yearly_dir = os.path.join(data_dir, "backups", "yearly")
    _fill_tier(yearly_dir, 5)

    promote_and_purge(data_dir, daily_keep=7, weekly_keep=6, monthly_keep=13)

    yearly_files = [f for f in os.listdir(yearly_dir) if f.endswith(".tar.gz")]
    assert len(yearly_files) == 5


def test_backup_db_consistency(tmp_path):
    data_dir = _setup_data_dir(tmp_path)
    backup_path = create_backup(data_dir)

    extract_dir = str(tmp_path / "extracted2")
    os.makedirs(extract_dir)
    with tarfile.open(backup_path, "r:gz") as tar:
        tar.extractall(extract_dir)

    db_path = os.path.join(extract_dir, "routes.db")
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT id FROM test").fetchall()
    conn.close()
    assert rows == [(1,)]
