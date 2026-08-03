<!--
logs/README.md
---------------
Purpose: Explains what this folder is for, since it is a runtime output
directory rather than a Python package (it intentionally has no
__init__.py).
-->

# logs/

This folder is where the application will write its runtime log files
once logging is implemented (see the planned `utils/logger.py`).

- Log files themselves (e.g. `*.log`) are **not** committed to version
  control -- see the root `.gitignore`.
- This `README.md` (and the accompanying `.gitkeep`) exist only so the
  otherwise-empty folder is preserved in the Git repository.

No trading logic or logging logic is implemented yet in this version.
