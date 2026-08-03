"""
tests package
--------------
Purpose:
    Contains all automated tests for the project, mirroring the main
    package structure (e.g. `tests/analysis/`, `tests/strategies/`) so
    that each module's tests are easy to locate.

    Testing framework: pytest (free, industry standard).

Planned contents (future versions):
    - unit/: fast, isolated tests for individual functions/classes.
    - integration/: tests that exercise multiple layers together
      (e.g. data -> analysis -> strategies), using mocked external APIs
      to keep everything free and offline-friendly.
    - conftest.py: shared pytest fixtures.

Currently empty: no trading logic implemented yet, so no tests yet
beyond verifying the project skeleton imports correctly.
"""
