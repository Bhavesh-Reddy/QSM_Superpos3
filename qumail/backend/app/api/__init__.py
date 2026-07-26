"""M2b — HTTP surface (Member C).

Thin FastAPI routers over the M2a services (``backend/app/services/``).
Zero business logic: validate, delegate, serialize. Exception-to-HTTP-status
mapping is registered once in ``backend/main.py``, not per-router.
"""

from backend.app.api import routes_auth, routes_keys, routes_mail

__all__ = ["routes_auth", "routes_keys", "routes_mail"]
