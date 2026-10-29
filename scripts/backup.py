import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from config import settings, DEFAULT_REPO_DIR


def run_daily_backup(
    db_path: Path = settings.VAULT_DATA_DIR / "db" / "vault.sqlite",
    backup_root: Path = settings.VAULT_DATA_DIR / "backups",
    env_path: Path = DEFAULT_REPO_DIR / ".env",
    retention_days: int = settings.BACKUP_RETENTION_DAYS
) -> Dict[str, Any]:
    """
    Phase 7.2: Automatic Database & Configuration Backups.
    Uses SQLite's online backup API (`sqlite3.Connection.backup`) so `vault.sqlite`
    is safely backed up even while active transactions are occurring, copies `.env`,
    and prunes backups older than `retention_days`.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest_dir = backup_root / f"backup_{timestamp}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    backed_up_files: List[str] = []

    # 1. Online hot-backup of vault.sqlite
    if db_path.exists():
        dest_db = dest_dir / "vault.sqlite"
        src_conn = sqlite3.connect(str(db_path))
        dst_conn = sqlite3.connect(str(dest_db))
        try:
            with dst_conn:
                src_conn.backup(dst_conn)
            backed_up_files.append(str(dest_db))
        finally:
            dst_conn.close()
            src_conn.close()

    # 2. Copy .env if present
    if env_path.exists():
        dest_env = dest_dir / ".env.backup"
        shutil.copy2(env_path, dest_env)
        backed_up_files.append(str(dest_env))

    # 3. Prune expired backup folders
    pruned_dirs: List[str] = []
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    if backup_root.exists():
        for item in backup_root.iterdir():
            if item.is_dir() and item.name.startswith("backup_"):
                mtime = datetime.utcfromtimestamp(item.stat().st_mtime)
                if mtime < cutoff:
                    shutil.rmtree(item, ignore_errors=True)
                    pruned_dirs.append(item.name)

    return {
        "status": "success",
        "backup_dir": str(dest_dir),
        "files": backed_up_files,
        "pruned_old_backups": pruned_dirs,
        "timestamp": timestamp
    }


if __name__ == "__main__":
    result = run_daily_backup()
    print(f"✅ Backup completed: {result['backup_dir']} ({len(result['files'])} files)")
