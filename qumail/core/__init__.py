"""QuMail shared contracts: models, interfaces, and exceptions.

Every other package (backend, km_simulator, tests) imports its cross-module
types from here. Keep this package dependency-free except for pydantic.
"""

from core.exceptions import QuMailError
from core.models import (
    EmailAttachment,
    EmailMessage,
    EncryptedMessage,
    QKDKey,
    SecurityLevel,
)

__all__ = [
    "EmailAttachment",
    "EmailMessage",
    "EncryptedMessage",
    "QKDKey",
    "QuMailError",
    "SecurityLevel",
]