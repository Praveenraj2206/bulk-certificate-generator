"""Application settings.

Values come from environment variables (optionally loaded from a `.env` file in
the project root) and fall back to defaults, so the app runs with zero setup.
"""

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Tiny .env reader (KEY=VALUE lines) so we don't need an extra dependency.

    Real environment variables always win over values in the file.
    """
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str
    generated_files_dir: Path


def load_settings() -> Settings:
    _load_dotenv(BASE_DIR / ".env")
    return Settings(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./certificates.db"),
        generated_files_dir=Path(
            os.getenv("GENERATED_FILES_DIR", "./generated")
        )
        .expanduser()
        .resolve(),
    )


settings = load_settings()


def get_generated_dir() -> Path:
    """FastAPI dependency returning the folder where PDFs are stored.

    It is a dependency (instead of a global) so tests can point it at a
    temporary directory without touching the real `generated/` folder.
    """
    return settings.generated_files_dir