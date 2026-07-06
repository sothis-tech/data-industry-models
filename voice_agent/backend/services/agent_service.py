import json
import os
import socket
import logging
import uuid
import aiohttp
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from backend.config import config

log = logging.getLogger("agent-service")

# --- Modelos de Datos (Contrato) ---
# Request: el agente externo (/api/chat).
# Response: el agente debe devolver { request_id, status, response: { speech, text?, data? } }.

class AgentRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    user_id: str
    client_id: str = "default_client"
    level_id: str = "default_level"
    input_text: str
    modality: str = "speech"

class AgentResponsePayload(BaseModel):
    speech: str
    text: Optional[str] = None
    data: Optional[Dict[str, Any]] = {}

class AgentResponse(BaseModel):
    request_id: str
    status: str  # "success" | "error"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    response: Optional[AgentResponsePayload] = None

# --- Servicio ---

class AgentService:
    def __init__(self, api_url: str):
        self.api_url = api_url
        if not self.api_url:
            log.warning("AGENT_API_URL no está configurada. El servicio no funcionará correctamente.")
        else:
            log.info("AgentService inicializado con éxito apuntando a: %s", self.api_url)

    async def process_request(
        self,
        text: str,
        session_id: str,
        user_id: str = "unknown",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Envía una transcripción al Agente de Activos y recibe la respuesta estructurada.
        Retorna un diccionario compatible con lo que espera el frontend: {"speech": "...", "text": "..."}
        """
        
        # 1. Crear Objeto Request (Validado por Pydantic)
        # TODO: Inyectar client_id y level_id reales desde configuración o contexto si existen
        request_model = AgentRequest(
            session_id=session_id,
            user_id=user_id,
            input_text=text,
        )
       
        request_body = request_model.model_dump()
        outbound_headers = {"Content-Type": "application/json"}
        if extra_headers:
            outbound_headers.update({k: v for k, v in extra_headers.items() if v})
        log_headers = {
            k: ("***" if k.lower() == "authorization" else v)
            for k, v in outbound_headers.items()
        }
        log.info(
            "[Agent] Request → %s | headers: %s | body: %s",
            self.api_url,
            json.dumps(log_headers, ensure_ascii=False),
            json.dumps(request_body, ensure_ascii=False),
        )

        try:
            # Connector: forzar IPv4 y sin SSL para evitar fallos de conexión en Docker (host.docker.internal)
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                ssl=False,
            )
            timeout = aiohttp.ClientTimeout(
                total=config.AGENT_TIMEOUT_TOTAL_SEC,
                connect=config.AGENT_TIMEOUT_CONNECT_SEC,
            )
            log.debug(
                "[Agent] Timeouts configurados: total=%ss connect=%ss",
                config.AGENT_TIMEOUT_TOTAL_SEC,
                config.AGENT_TIMEOUT_CONNECT_SEC,
            )
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    self.api_url,
                    json=request_body,
                    headers=outbound_headers,
                    timeout=timeout,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        log.error("[Agent] Error HTTP %s: %s", response.status, error_text)
                        return self._create_error_dict(
                            "Error de comunicación con el Agente de Control de Activos.",
                            code=f"HTTP_{response.status}",
                        )
                    raw_data = await response.json()
                    resp_str = json.dumps(raw_data, ensure_ascii=False)
                    log.info("[Agent] Response ← status=%s | body: %s", response.status, resp_str[:1000] + ("..." if len(resp_str) > 1000 else ""))

                    try:
                        agent_resp = AgentResponse(**raw_data)
                    except Exception as e:
                        log.error("[Agent] Error de validación del contrato de respuesta: %s | Data: %s", e, raw_data)
                        return self._create_error_dict("El agente devolvió una respuesta con formato inválido.", code="INVALID_CONTRACT")

                    if agent_resp.status == "error":
                        log.warning("[Agent] El agente reportó error: %s", agent_resp.error_code)
                        speech = agent_resp.response.speech if agent_resp.response else "Ocurrió un error en el procesamiento."
                        return {
                            "speech": speech,
                            "text": agent_resp.response.text if agent_resp.response and agent_resp.response.text else f"❌ Error: {agent_resp.error_code}",
                            "data": agent_resp.response.data if agent_resp.response else {},
                        }

                    if not agent_resp.response:
                        return self._create_error_dict("Respuesta vacía del agente.", code="EMPTY_RESPONSE")

                    log.info("[Agent] Respuesta recibida correctamente.")
                    return agent_resp.response.model_dump()

        except Exception as e:
            log.error(
                "[Agent] Excepción conectando al agente: url=%s | tipo=%s | error=%s",
                self.api_url,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return self._create_error_dict("No pude conectar con el agente inteligente.", code="CONNECTION_ERROR")

    def _create_error_dict(self, speech_text: str, code: str = "UNKNOWN") -> Dict[str, Any]:
        return {
            "speech": speech_text,
            "text": f"❌ **Error ({code})**\n{speech_text}",
            "data": {},
        }
