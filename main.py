"""
ProfFeb - Root ASGI Application Entrypoint
Provides entrypoint for Vercel, uvicorn, and container deployments.
"""
import sys
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_BACKEND = _ROOT / "backend"

for p in [str(_ROOT), str(_BACKEND)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from backend.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
