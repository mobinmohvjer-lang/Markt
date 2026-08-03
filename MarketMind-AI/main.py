"""
main.py
--------
Entry point of the MarketMind-AI application.

Purpose:
    This file is the single starting point used to launch the trading
    assistant. It is intentionally kept thin: it should only be
    responsible for wiring together configuration and bootstrapping the
    application, not for containing business logic.

Future responsibilities (to be implemented in later versions):
    - Load configuration and environment variables.
    - Initialize logging.
    - Bootstrap core services (data feed, database, strategies, AI models).
    - Start the main application loop (e.g. a scheduler, CLI, or API server).

Usage:
    python main.py
"""

from __future__ import annotations

from config.settings import get_settings


def main() -> None:
    """
    Application bootstrap function.

    This is the single orchestration point that will, in future versions,
    initialize all subsystems (data, analysis, strategies, database,
    services) in the correct order. For now it only proves that the
    configuration layer can be loaded successfully.
    """
    settings = get_settings()

    print(f"Starting {settings.app_name} v{settings.app_version}")
    print(f"Environment: {settings.environment}")
    print("MarketMind-AI skeleton is ready. No trading logic implemented yet.")


if __name__ == "__main__":
    # Guard clause so this module can be imported elsewhere (e.g. tests)
    # without automatically executing the application.
    main()
