"""M4 — KM Client (ETSI GS QKD 014 REST client).

Talks to a Key Manager — the :mod:`km_simulator` during development, real QKD
hardware later — over the ETSI 014 REST API. Public class:
:class:`~backend.app.km.client.KMClient`.
"""

from backend.app.km.client import KMClient

__all__ = ["KMClient"]
