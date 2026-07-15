"""既存のAPIキーを保持したまま院内運用設定を整える。"""

from pathlib import Path
import secrets


ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
LOCAL_SECRET = "django-insecure-local-development-only"


def parse_key(line: str) -> str | None:
    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
        return None

    if "=" not in stripped:
        return None

    return stripped.split("=", 1)[0].strip()


def secret_needs_replacement(value: str) -> bool:
    normalized = value.strip()

    return (
        len(normalized) < 40
        or normalized == LOCAL_SECRET
        or normalized.startswith("replace-")
    )


def configure_environment() -> None:
    lines = (
        ENV_PATH.read_text(encoding="utf-8").splitlines()
        if ENV_PATH.exists()
        else []
    )
    existing = {}

    for line in lines:
        key = parse_key(line)

        if key:
            existing[key] = line.split("=", 1)[1].strip()

    current_secret = existing.get("DJANGO_SECRET_KEY", "")

    if secret_needs_replacement(current_secret):
        current_secret = secrets.token_urlsafe(64)

    required = {
        "DJANGO_SECRET_KEY": current_secret,
        "DJANGO_DEBUG": "false",
        "DJANGO_PRODUCTION": "true",
        "DJANGO_ALLOWED_HOSTS": "127.0.0.1,localhost",
        "DJANGO_HTTPS": "false",
    }

    updated = []
    written = set()

    for line in lines:
        key = parse_key(line)

        if key in required:
            updated.append(f"{key}={required[key]}")
            written.add(key)
        else:
            updated.append(line)

    if updated and updated[-1].strip():
        updated.append("")

    for key, value in required.items():
        if key not in written:
            updated.append(f"{key}={value}")

    temporary_path = ENV_PATH.with_name(".env.tmp")
    temporary_path.write_text(
        "\n".join(updated).rstrip() + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(ENV_PATH)

    print(
        "院内運用設定を更新しました。"
        "秘密鍵やAPIキーの値は表示していません。"
    )


if __name__ == "__main__":
    configure_environment()
