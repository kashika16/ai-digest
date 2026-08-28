from pathlib import Path
from plistlib import dump

from ai_digest.config import DigestConfig


DEFAULT_LABEL = "ai-digest"


def launch_agent_destination(label: str = DEFAULT_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def launch_agent_dict(config: DigestConfig, hour: int, minute: int, label: str = DEFAULT_LABEL) -> dict:
    return {
        "Label": label,
        "ProgramArguments": [
            "/usr/bin/python3",
            str(config.project_root / "run_digest.py"),
        ],
        "WorkingDirectory": str(config.project_root),
        "RunAtLoad": True,
        "StartCalendarInterval": {
            "Hour": hour,
            "Minute": minute,
        },
        "StandardOutPath": str(config.log_dir / "ai-digest.log"),
        "StandardErrorPath": str(config.log_dir / "ai-digest.error.log"),
    }


def write_launch_agent(config: DigestConfig, destination: Path, hour: int, minute: int) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        dump(launch_agent_dict(config, hour, minute), handle)
    return destination
