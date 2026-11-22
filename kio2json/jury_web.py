"""Serve the jury upload page and extraction API together on localhost."""

from pathlib import Path

from fastapi.staticfiles import StaticFiles

from .web_api import app

app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend/public", html=True))
