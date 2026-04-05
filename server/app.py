"""
server/app.py - Entry point for multi-mode deployment.
This module re-exports the FastAPI app from the root app.py
and provides a main() function for the [project.scripts] entry point.
"""
import sys
import os

# Add parent directory to path so we can import from root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: F401


def main():
    """Entry point for 'serve' script defined in pyproject.toml."""
    import uvicorn
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )


if __name__ == "__main__":
    main()
