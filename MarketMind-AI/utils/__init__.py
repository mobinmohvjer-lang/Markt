"""
utils package
---------------
Purpose:
    Small, generic, reusable helper functions that don't belong to any
    specific layer (e.g. date/time helpers, logging setup, decorators,
    validation helpers).

    Rule of thumb: if a helper function is used by 2+ unrelated packages
    and has no business meaning of its own, it belongs here.

Planned contents (future versions):
    - logger.py: centralized logging configuration used across the app.
    - datetime_utils.py: timeframe/timestamp conversions.
    - validators.py: generic input validation helpers.

Currently empty: no trading logic implemented yet.
"""
