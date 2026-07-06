#!/usr/bin/env python3
"""Prueba de conexión al agente LLM (desde el host o desde dentro del contenedor)."""
import json
import os
import sys

# Cargar config para usar la misma URL que el backend (en el contenedor ya viene por env_file)
from dotenv import load_dotenv
_root = os.path.join(os.path.dirname(__file__), "..")
load_dotenv(os.path.join(_root, "config.env"))
url = os.getenv("AGENT_API_URL", "http://localhost:8081/api/chat")

payload = {
    "request_id": "test-conn",
    "session_id": "test",
    "user_id": "unknown",
    "client_id": "default_client",
    "level_id": "default_level",
    "input_text": "hola",
    "modality": "speech",
}

def main():
    try:
        import urllib.request
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read().decode()
            print("OK", r.status)
            print(body[:500])
    except Exception as e:
        print("FAIL", type(e).__name__, e)
        sys.exit(1)

if __name__ == "__main__":
    main()
