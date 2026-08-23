"""Load YAML configs and environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return data


@lru_cache(maxsize=1)
def load_env() -> None:
    load_dotenv(ROOT / ".env")


@lru_cache(maxsize=1)
def get_app_config() -> dict[str, Any]:
    load_env()
    return _read_yaml(CONFIG_DIR / "app_config.yaml")


@lru_cache(maxsize=1)
def get_model_config() -> dict[str, Any]:
    load_env()
    return _read_yaml(CONFIG_DIR / "model_config.yaml")


@lru_cache(maxsize=1)
def get_routing_rules() -> dict[str, Any]:
    load_env()
    return _read_yaml(CONFIG_DIR / "routing_rules.yaml")


def get_mongodb_uri() -> str:
    load_env()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set in .env")
    return uri


def get_mongodb_database() -> str:
    load_env()
    return os.getenv("DATABASE", "AI_KB")


def get_mongodb_collection() -> str:
    load_env()
    return os.getenv("COLLECTION", "documents")


def get_deepseek_api_key() -> str:
    load_env()
    key = (os.getenv("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set in .env")
    if key.lower().startswith("your_"):
        raise RuntimeError(
            "DEEPSEEK_API_KEY in .env is still the placeholder from .env.example. "
            "Set a real key from https://platform.deepseek.com/api_keys"
        )
    return key


def project_path(*parts: str) -> Path:
    return ROOT.joinpath(*parts)
