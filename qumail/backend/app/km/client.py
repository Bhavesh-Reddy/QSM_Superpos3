"""ETSI GS QKD 014 REST client (M4).

Implements :class:`core.interfaces.IKMClient` over HTTP using ``httpx``. The
client is bound to a single SAE ID at construction; it requests encryption
keys (``enc_keys``) toward a peer and redeems key IDs (``dec_keys``) received
from a peer. Base64 ``key`` values from the wire are decoded into raw bytes
and wrapped in :class:`core.models.QKDKey`.

Logging never includes key material — only ``key_ID``s, counts, and sizes.
"""

from __future__ import annotations

import base64
import logging

import httpx

from core.exceptions import KeyExhaustedError, KeyNotFoundError, KMConnectionError, KMResponseError
from core.interfaces import IKMClient
from core.models import ETSIStatus, QKDKey

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class KMClient(IKMClient):
    """ETSI 014 REST client bound to one SAE ID."""

    def __init__(
        self,
        base_url: str,
        sae_id: str,
        verify_tls: bool = True,
        timeout: httpx.Timeout | float = _DEFAULT_TIMEOUT,
    ) -> None:
        """Configure the client.

        Args:
            base_url: KM root URL, e.g. ``http://127.0.0.1:8100``.
            sae_id: This client's SAE ID (used in the ``status`` path).
            verify_tls: Verify server TLS certificates (disable only for a
                local dev simulator over plain HTTP).
            timeout: Per-request timeout (httpx ``Timeout`` or seconds).
        """
        self._base_url = base_url.rstrip("/")
        self._sae_id = sae_id
        self._verify_tls = verify_tls
        self._timeout = timeout

    @property
    def sae_id(self) -> str:
        """The SAE ID this client is bound to."""
        return self._sae_id

    def _post(self, path: str, payload: dict) -> dict:
        """POST JSON to the KM and return the decoded JSON body.

        Args:
            path: Request path beginning with ``/``.
            payload: JSON request body.

        Returns:
            The parsed JSON response object.

        Raises:
            KMConnectionError: On transport or HTTP-status errors.
            KMResponseError: If the body is not valid JSON.
        """
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(verify=self._verify_tls, timeout=self._timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            raise self._map_status_error(exc) from exc
        except httpx.HTTPError as exc:
            raise KMConnectionError(f"KM request to {path} failed: {exc}") from exc
        except ValueError as exc:  # json decode
            raise KMResponseError(f"KM returned non-JSON body from {path}") from exc

    @staticmethod
    def _map_status_error(exc: httpx.HTTPStatusError) -> Exception:
        """Map an HTTP error status onto a typed QuMail exception.

        Args:
            exc: The raised httpx status error.

        Returns:
            The typed exception to raise (404 -> KeyNotFoundError,
            otherwise KMConnectionError).
        """
        status = exc.response.status_code
        if status == 404:
            return KeyNotFoundError("KM reports one or more key_IDs unknown")
        return KMConnectionError(f"KM returned HTTP {status}")

    @staticmethod
    def _decode_keys(container: dict) -> list[QKDKey]:
        """Convert an ETSI key container into :class:`QKDKey` objects.

        Args:
            container: Parsed ``{"keys": [{"key_ID", "key"}]}`` response.

        Returns:
            Keys with base64 ``key`` decoded to raw bytes.

        Raises:
            KMResponseError: If the container shape is invalid or base64 is bad.
        """
        try:
            entries = container["keys"]
            keys: list[QKDKey] = []
            for entry in entries:
                raw = base64.b64decode(entry["key"], validate=True)
                keys.append(
                    QKDKey(key_id=entry["key_ID"], key=raw, size_bits=len(raw) * 8)
                )
            return keys
        except (KeyError, TypeError, ValueError, base64.binascii.Error) as exc:
            raise KMResponseError(f"malformed ETSI key container: {exc}") from exc

    def get_status(self) -> ETSIStatus:
        """Query key availability for this client's SAE (ETSI 014 ``status``).

        Returns:
            The KM status document.

        Raises:
            KMConnectionError: If the KM is unreachable or returns an HTTP error.
            KMResponseError: If the response is not a valid status document.
        """
        url = f"{self._base_url}/api/v1/keys/{self._sae_id}/status"
        try:
            with httpx.Client(verify=self._verify_tls, timeout=self._timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPStatusError as exc:
            raise KMConnectionError(f"KM returned HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise KMConnectionError(f"KM status request failed: {exc}") from exc
        except ValueError as exc:
            raise KMResponseError("KM returned non-JSON status body") from exc
        try:
            status = ETSIStatus.model_validate(body)
        except Exception as exc:  # noqa: BLE001 - normalize pydantic errors
            raise KMResponseError(f"invalid ETSI status document: {exc}") from exc
        logger.info(
            "KM status for %s: %d key(s) available", self._sae_id, status.stored_key_count
        )
        return status

    def get_key(
        self, target_sae_id: str, number: int = 1, size: int = 256
    ) -> list[QKDKey]:
        """Request fresh encryption keys toward a peer (ETSI 014 ``enc_keys``).

        Args:
            target_sae_id: SAE ID of the recipient.
            number: How many keys to request.
            size: Key size in bits.

        Returns:
            The generated keys (base64 decoded to bytes).

        Raises:
            KMConnectionError: If the KM is unreachable or returns an HTTP error.
            KeyExhaustedError: If the KM cannot supply the requested keys.
        """
        path = f"/api/v1/keys/{target_sae_id}/enc_keys"
        body = self._post(path, {"number": number, "size": size})
        keys = self._decode_keys(body)
        if not keys:
            raise KeyExhaustedError(
                f"KM returned no keys for {target_sae_id} (requested {number})"
            )
        logger.info(
            "enc_keys: got %d key(s) of %d bits toward %s [%s]",
            len(keys),
            size,
            target_sae_id,
            ", ".join(k.key_id for k in keys),
        )
        return keys

    def get_key_with_ids(
        self, source_sae_id: str, key_ids: list[str]
    ) -> list[QKDKey]:
        """Redeem key IDs received from a peer (ETSI 014 ``dec_keys``).

        Args:
            source_sae_id: SAE ID of the sender who requested the keys.
            key_ids: ``key_ID`` values from the message metadata.

        Returns:
            The matching keys (base64 decoded to bytes).

        Raises:
            KMConnectionError: If the KM is unreachable or returns an HTTP error.
            KeyNotFoundError: If any requested ``key_ID`` is unknown to the KM.
        """
        path = f"/api/v1/keys/{source_sae_id}/dec_keys"
        payload = {"key_IDs": [{"key_ID": kid} for kid in key_ids]}
        body = self._post(path, payload)
        keys = self._decode_keys(body)
        returned = {k.key_id for k in keys}
        missing = [kid for kid in key_ids if kid not in returned]
        if missing:
            raise KeyNotFoundError(f"KM did not return key_ID(s): {', '.join(missing)}")
        logger.info(
            "dec_keys: resolved %d key(s) from %s [%s]",
            len(keys),
            source_sae_id,
            ", ".join(k.key_id for k in keys),
        )
        return keys
