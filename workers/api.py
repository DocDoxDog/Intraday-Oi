from __future__ import annotations

import os

import uvicorn

from src.api import app


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.environ.get("CANONICAL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("CANONICAL_API_PORT", "8000")),
    )
