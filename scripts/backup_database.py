"""Djangoデータベースをローカルに世代保存する。"""

from datetime import datetime
from pathlib import Path
import shutil


ROOT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = ROOT_DIR / "db.sqlite3"
BACKUP_DIR = ROOT_DIR / "backups" / "database"
KEEP_BACKUPS = 14


def backup_database() -> Path:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "db.sqlite3がありません。先に初回設定を実行してください。"
        )

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / f"db_{timestamp}.sqlite3"
    shutil.copy2(DATABASE_PATH, destination)

    backups = sorted(
        BACKUP_DIR.glob("db_*.sqlite3"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    for old_backup in backups[KEEP_BACKUPS:]:
        old_backup.unlink()

    return destination


if __name__ == "__main__":
    saved_path = backup_database()
    print(f"バックアップ完了: {saved_path}")
