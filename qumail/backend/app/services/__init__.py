"""M2a — orchestration services (Member B).

Pipelines that wire the modules together behind ``core/interfaces.py``:

* :class:`~backend.app.services.send_service.SendService`
  — key -> encrypt -> send
* :class:`~backend.app.services.receive_service.ReceiveService`
  — fetch -> key -> decrypt

Hard rule: this package imports ONLY ``core`` contracts (interfaces, models,
exceptions). No FastAPI imports — HTTP concerns live in ``backend/app/api/``
(M2b).
"""

from backend.app.services.receive_service import ReceiveService
from backend.app.services.send_service import SendService

__all__ = ["ReceiveService", "SendService"]
