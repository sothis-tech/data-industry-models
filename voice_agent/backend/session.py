"""Estado de sesión WebSocket y máquina de estados del agente de voz."""
import time
import logging
from enum import Enum
from typing import Mapping


class AgentState(Enum):
    WAITING_WAKEWORD = "waiting_wakeword"
    ACTIVE = "active"
    PROCESSING = "processing"


class SessionContext:
    """Contexto de una sesión WebSocket: estado actual y timeout de inactividad."""

    def __init__(
        self,
        session_id: str,
        active_timeout_sec: float,
        log: logging.Logger,
        service_headers: Mapping[str, str] | None = None,
    ):
        self.session_id = session_id
        self.state = AgentState.WAITING_WAKEWORD
        self.last_interaction = time.time()
        self._active_timeout_sec = active_timeout_sec
        self._log = log
        self.service_headers = dict(service_headers or {})

    def transition_to(self, new_state: AgentState) -> None:
        self._log.info(
            "[WS %s] State transition: %s -> %s",
            self.session_id,
            self.state.name,
            new_state.name,
        )
        self.state = new_state
        if new_state == AgentState.ACTIVE:
            self.last_interaction = time.time()

    def check_timeout(self) -> bool:
        """Comprueba si la sesión activa ha superado el tiempo sin interacción. Devuelve True si ha expirado."""
        if self.state == AgentState.ACTIVE:
            if (time.time() - self.last_interaction) > self._active_timeout_sec:
                self._log.info(
                    "[WS %s] Timeout (%.1fs). Resetting to Waiting Wake Word.",
                    self.session_id,
                    self._active_timeout_sec,
                )
                self.transition_to(AgentState.WAITING_WAKEWORD)
                return True
        return False
