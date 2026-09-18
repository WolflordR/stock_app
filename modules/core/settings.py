from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    project_root: Path
    data_dir: Path
    raw_data_dir: Path
    processed_data_dir: Path
    db_dir: Path
    cache_dir: Path
    logs_dir: Path
    backups_dir: Path
    api_cors_origins: tuple[str, ...]


def _resolve_path(value: str | None, fallback: Path) -> Path:
    if not value:
        return fallback
    return Path(value).expanduser().resolve()


def load_settings() -> AppSettings:
    project_root = Path(__file__).resolve().parents[2]
    default_data_dir = project_root / "data"
    data_dir = _resolve_path(os.getenv("TRADE_DATA_DIR"), default_data_dir)

    cors_origins = tuple(
        origin.strip()
        for origin in os.getenv("TRADE_API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
        if origin.strip()
    )

    return AppSettings(
        project_root=project_root,
        data_dir=data_dir,
        raw_data_dir=_resolve_path(os.getenv("TRADE_RAW_DATA_DIR"), data_dir / "raw"),
        processed_data_dir=_resolve_path(os.getenv("TRADE_PROCESSED_DATA_DIR"), data_dir / "processed"),
        db_dir=_resolve_path(os.getenv("TRADE_DB_DIR"), data_dir),
        cache_dir=_resolve_path(os.getenv("TRADE_CACHE_DIR"), data_dir / "cache"),
        logs_dir=_resolve_path(os.getenv("TRADE_LOGS_DIR"), project_root / "logs"),
        backups_dir=_resolve_path(os.getenv("TRADE_BACKUPS_DIR"), project_root / "backups"),
        api_cors_origins=cors_origins,
    )


SETTINGS = load_settings()
