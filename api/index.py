"""
ProfFeb - Vercel Serverless Function Entrypoint
Routes requests to the FastAPI application instance.
"""
import sys
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"

for p in [str(_ROOT), str(_BACKEND)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.main import app
