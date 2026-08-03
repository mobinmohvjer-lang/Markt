"""
config package
---------------
Purpose:
    Groups everything related to application configuration:
    - settings.py: typed, environment-driven application settings.
    - config.py: static/constant configuration values and enums that are
      not expected to change at runtime (paths, default parameters, etc.).

This package is the ONLY place in the project that should read environment
variables directly. Every other module should import configuration objects
from here instead of calling `os.environ` on their own. This keeps
configuration centralized and easy to audit.
"""
