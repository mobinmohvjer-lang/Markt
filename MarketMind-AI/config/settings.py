"""
settings.py
------------
Purpose:
    Defines the typed `Settings` object used throughout the application.

    This module centralizes all environment-dependent configuration
    (API keys, environment name, debug flags, etc.) using a single typed
    class. It is the recommended pattern for "12-factor app" style
    configuration: values come from environment variables (or a `.env`
    file for local development), never hardcoded in business logic.

Design notes:
    - Uses `dataclasses` (standard library, free, no extra dependency)
      for a lightweight typed settings object. Once the project grows,
      this can be swapped for `pydantic-settings` without changing the
      rest of the codebase, since consumers only depend on `get_settings()`.
    - `get_settings()` is cached with `functools.lru_cache` so the
      environment is only parsed once per process.
    - No trading logic lives here. Only configuration values.

Usage:
    from config.settings import get_settings
    settings = get_settings()
    print(settings.app_name)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    """
    Immutable container for all application-wide settings.

    Attributes:
        app_name: Human-readable name of the application.
        app_version: Current version of the application.
        environment: Deployment environment identifier
            (e.g. "development", "production", "testing").
        debug: Whether the application should run in verbose/debug mode.

        binance_api_key: Placeholder for the Binance API key (free tier).
        binance_api_secret: Placeholder for the Binance API secret.
        binance_testnet: Whether to use Binance's free testnet endpoints
            instead of live trading endpoints (recommended for personal,
            free, risk-free experimentation).

        news_api_key: Placeholder for a free-tier news data provider key,
            to be used later by the news analysis module.

        database_url: Connection string for the local database
            (defaults to a local SQLite file, which is free and
            requires no external server).

        log_level: Default logging verbosity for the whole application.
    """

    app_name: str = "MarketMind-AI"
    app_version: str = "0.1.0"
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    debug: bool = field(default_factory=lambda: os.getenv("APP_DEBUG", "true").lower() == "true")

    binance_api_key: str = field(default_factory=lambda: os.getenv("BINANCE_API_KEY", ""))
    binance_api_secret: str = field(default_factory=lambda: os.getenv("BINANCE_API_SECRET", ""))
    binance_testnet: bool = field(
        default_factory=lambda: os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    )

    news_api_key: str = field(default_factory=lambda: os.getenv("NEWS_API_KEY", ""))

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///./marketmind.db")
    )

    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached, singleton-like `Settings` instance.

    Using `lru_cache` ensures environment variables are read only once,
    which avoids inconsistent behavior if environment variables were to
    change during the process lifetime, and avoids repeated parsing cost.

    Returns:
        Settings: the fully populated settings object.
    """
    return Settings()
