from __future__ import annotations

from pathlib import Path

from modules.core.settings import SETTINGS


PROJECT_ROOT = SETTINGS.project_root
DATA_DIR = SETTINGS.data_dir
RAW_DATA_DIR = SETTINGS.raw_data_dir
PROCESSED_DATA_DIR = SETTINGS.processed_data_dir
DB_DIR = SETTINGS.db_dir
CACHE_DIR = SETTINGS.cache_dir
LOGS_DIR = SETTINGS.logs_dir
BACKUPS_DIR = SETTINGS.backups_dir
DOCS_DIR = PROJECT_ROOT / "docs"


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def ensure_raw_data_dir() -> Path:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return RAW_DATA_DIR


def ensure_processed_data_dir() -> Path:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return PROCESSED_DATA_DIR


def ensure_db_dir() -> Path:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    return DB_DIR


def ensure_cache_dir() -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def ensure_logs_dir() -> Path:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR


def ensure_backups_dir() -> Path:
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return BACKUPS_DIR


def data_path(name: str) -> Path:
    ensure_data_dir()
    return DATA_DIR / name


def raw_data_path(name: str) -> Path:
    ensure_raw_data_dir()
    return RAW_DATA_DIR / name


def processed_data_path(name: str) -> Path:
    ensure_processed_data_dir()
    return PROCESSED_DATA_DIR / name


def db_path(name: str) -> Path:
    ensure_db_dir()
    return DB_DIR / name


def cache_path(name: str) -> Path:
    ensure_cache_dir()
    return CACHE_DIR / name


def logs_path(name: str) -> Path:
    ensure_logs_dir()
    return LOGS_DIR / name


def backups_path(name: str) -> Path:
    ensure_backups_dir()
    return BACKUPS_DIR / name
