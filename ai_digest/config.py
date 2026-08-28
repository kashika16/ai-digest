from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


@dataclass(frozen=True)
class DigestConfig:
    project_root: Path
    sources_file: Path
    state_file: Path
    last_sent_file: Path
    log_dir: Path
    to_email: Optional[str]
    from_email: Optional[str]
    subject_prefix: str
    hours_back: int
    max_items: int
    timezone_name: str
    smtp_host: Optional[str]
    smtp_port: Optional[int]
    smtp_username: Optional[str]
    smtp_password: Optional[str]
    smtp_use_tls: bool
    smtp_use_ssl: bool


def parse_bool(raw_value: str) -> bool:
    return raw_value.lower() in {"1", "true", "yes", "on"}


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for line in env_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key, value)


def load_config() -> DigestConfig:
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    load_env_file(env_path)

    state_dir = project_root / ".cache"
    log_dir = project_root / "logs"
    state_dir.mkdir(exist_ok=True)
    log_dir.mkdir(exist_ok=True)

    return DigestConfig(
        project_root=project_root,
        sources_file=project_root / "sources.json",
        state_file=state_dir / "seen_links.json",
        last_sent_file=state_dir / "last_sent_date.txt",
        log_dir=log_dir,
        to_email=os.environ.get("DIGEST_TO_EMAIL"),
        from_email=os.environ.get("DIGEST_FROM_EMAIL"),
        subject_prefix=os.environ.get("DIGEST_SUBJECT_PREFIX", "AI Daily Digest"),
        hours_back=int(os.environ.get("DIGEST_HOURS_BACK", "24")),
        max_items=int(os.environ.get("DIGEST_MAX_ITEMS", "20")),
        timezone_name=os.environ.get("DIGEST_TIMEZONE", "Europe/Berlin"),
        smtp_host=os.environ.get("SMTP_HOST"),
        smtp_port=int(os.environ["SMTP_PORT"]) if os.environ.get("SMTP_PORT") else None,
        smtp_username=os.environ.get("SMTP_USERNAME"),
        smtp_password=os.environ.get("SMTP_PASSWORD"),
        smtp_use_tls=parse_bool(os.environ.get("SMTP_USE_TLS", "true")),
        smtp_use_ssl=parse_bool(os.environ.get("SMTP_USE_SSL", "false")),
    )


def require_send_config(config: DigestConfig) -> None:
    missing_fields = []
    if not config.to_email:
        missing_fields.append("DIGEST_TO_EMAIL")
    if not config.from_email:
        missing_fields.append("DIGEST_FROM_EMAIL")
    if not config.smtp_host:
        missing_fields.append("SMTP_HOST")
    if config.smtp_port is None:
        missing_fields.append("SMTP_PORT")
    if not config.smtp_username:
        missing_fields.append("SMTP_USERNAME")
    if not config.smtp_password:
        missing_fields.append("SMTP_PASSWORD")
    if missing_fields:
        raise ValueError(f"Missing required send settings: {', '.join(missing_fields)}")
