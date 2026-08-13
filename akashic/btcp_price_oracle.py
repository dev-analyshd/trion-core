"""Compatibility shim — re-exports from anima-service/btcp_price_oracle.py.

The canonical implementation lives at `anima-service/btcp_price_oracle.py`.
`anima-service` cannot be a Python package (the hyphen is illegal in
identifiers), so the `akashic` package re-exports it here for callers
that use `from akashic.btcp_price_oracle import ...`.
"""
import os
import sys

# Add anima-service to sys.path so we can import the canonical module
_ANIMA_SERVICE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "anima-service")
if _ANIMA_SERVICE not in sys.path:
    sys.path.insert(0, _ANIMA_SERVICE)

from btcp_price_oracle import *  # noqa: F401,F403
