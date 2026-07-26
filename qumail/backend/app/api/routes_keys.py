"""M2b — key manager status route.

Proxies the ETSI 014 ``status`` document. Contains no key bytes; safe to
return to the client as-is.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.interfaces import IKMClient
from core.models import ETSIStatus

from backend.app.api.deps import get_km_client

router = APIRouter(prefix="/keys", tags=["keys"])


@router.get("/status", response_model=ETSIStatus)
def keys_status(km: IKMClient = Depends(get_km_client)) -> ETSIStatus:
    """Return the connected KM's key-availability status.

    Raises:
        ConfigError: If ``POST /auth/km`` has not been called yet.
        KMConnectionError: If the KM is unreachable.
        KMResponseError: If the KM's response is malformed.
    """
    return km.get_status()
