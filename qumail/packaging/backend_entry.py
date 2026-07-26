"""Frozen entrypoint for the QuMail backend (PyInstaller target).

Runs the FastAPI app under uvicorn *without* the dev reloader — reload and
import-string based reloading do not work inside a PyInstaller bundle. Config
is read from a ``.env`` file in the working directory (see ``.env.example``);
``KEYSTORE_MASTER_PASSWORD`` is required.
"""

from __future__ import annotations

import uvicorn

from backend.app.config import get_settings
from backend.main import app


def main() -> None:
    """Serve the backend on the configured host/port."""
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
