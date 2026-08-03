"""
test_settings.py
------------------
Purpose:
    Smoke test for the configuration layer. Since no trading logic
    exists yet in this first version, this test simply verifies that
    the project skeleton is wired correctly: settings can be loaded
    and expose the expected default values.

Run with:
    pytest
"""

from __future__ import annotations

from config.settings import get_settings


def test_settings_load_successfully() -> None:
    """The settings object should load without raising and expose the app name."""
    settings = get_settings()
    assert settings.app_name == "MarketMind-AI"


def test_settings_default_database_is_sqlite() -> None:
    """By default, persistence should use a free, local SQLite database."""
    settings = get_settings()
    assert settings.database_url.startswith("sqlite:///")
