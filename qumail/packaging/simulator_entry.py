"""Frozen entrypoint for the KM simulator (PyInstaller target).

Serves the ETSI 014 simulator under uvicorn on its default port (8100). Kept
separate from ``km_simulator/main.py`` so packaging never depends on that
module's ``__main__`` block.
"""

from __future__ import annotations

import uvicorn

from km_simulator.main import PORT, app


def main() -> None:
    """Serve the KM simulator on 127.0.0.1:PORT."""
    uvicorn.run(app, host="127.0.0.1", port=PORT)


if __name__ == "__main__":
    main()
