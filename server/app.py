"""
server/app.py — Multi-mode deployment entry point.
Required by the OpenEnv validator for multi-mode deployment checks.
Delegates to the root app.py FastAPI application.
"""
import sys
import os

# Ensure root is on path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: F401 — re-exported for server entry point


def main():
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
