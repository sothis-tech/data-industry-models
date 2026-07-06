import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uuid
import logging

# Configuración básica
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mock-agent")

app = FastAPI()

# Modelos (Copia del contrato)
class AgentRequest(BaseModel):
    request_id: str
    session_id: str
    user_id: str
    client_id: str
    level_id: str
    input_text: str
    modality: str

def _handle_request(req: AgentRequest):
    """Lógica compartida para cualquier ruta."""
    logger.info(f"📥 Recibido: {req.input_text} (Session: {req.session_id})")
    speech_response = f"Hola, he recibido tu mensaje: {req.input_text}. Soy el agente simulado."
    text_display = f"### ✅ Respuesta Simulada\n- **Input**: {req.input_text}\n- **Estado**: OK"
    if "error" in req.input_text.lower():
        return {
            "request_id": req.request_id,
            "status": "error",
            "error_code": "SIMULATED_FAILURE",
            "response": {
                "speech": "He detectado una palabra prohibida.",
                "text": "❌ **Error Simulado**\nSe detectó la palabra clave 'error'.",
                "data": {}
            }
        }
    return {
        "request_id": req.request_id,
        "status": "success",
        "response": {
            "speech": speech_response,
            "text": text_display,
            "data": {"mock_time": "12:00", "source": "mock_server"}
        }
    }

@app.post("/api/chat")
async def api_chat(req: AgentRequest):
    """Misma ruta que el agente real (voice-agent llama aquí)."""
    return _handle_request(req)

@app.post("/api/v1/agent/process")
async def process_request(req: AgentRequest):
    return _handle_request(req)

if __name__ == "__main__":
    print("🚀 Mock Agent corriendo en http://localhost:8081")
    uvicorn.run(app, host="0.0.0.0", port=8081)

