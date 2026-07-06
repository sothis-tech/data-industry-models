#!/usr/bin/env python3
# src/interfaces/cli.py
"""
Terminal REPL para el sistema MCP multi-agente.

Separa la interfaz de terminal del MOTOR (engine/client.py: MCPChatClient).
El motor es EL MISMO que usa la API: este REPL solo lo conduce a través de
`procesar_peticion_api`, exactamente igual que hace interfaces/api.py en
/api/chat. Así no se duplica lógica, no se toca el motor para hacer pruebas por
consola, y la trazabilidad (logs, métricas, conversaciones) es idéntica.

IMPORTANTE: arranca SIEMPRE desde la raíz del proyecto
(agente_control_data_space/), porque los servidores MCP se lanzan con rutas
relativas tipo 'src/servers/orion_server.py'.

Uso (desde la raíz del proyecto):
  python -m src.interfaces.cli                              # config/config.local.yaml (host)
  python -m src.interfaces.cli --config config/config.yaml  # config de Docker
  python -m src.interfaces.cli --tenant metapan             # fuerza otro tenant
  python -m src.interfaces.cli --session mi_sesion          # nombre de sesión

  (o, con src/ en el PYTHONPATH: python -m interfaces.cli)

Dentro del chat:
  salir / exit / quit / Ctrl+C   → cerrar
"""

import os
import sys
import argparse
import asyncio
import time
from pathlib import Path

# src/interfaces/cli.py → metemos src/ en sys.path para los imports 'engine.*',
# 'project.*' aunque se ejecute como 'python src/interfaces/cli.py'.
_SRC_DIR = Path(__file__).resolve().parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Importar el motor arranca el logging: engine/client.py ejecuta
# setup_logging() a nivel de módulo.
from engine.client import MCPChatClient
from engine.logging_setup import log_startup_banner, log_shutdown_banner

# Importar `project` REGISTRA en el motor los guardrails, prompts y
# comportamientos del proyecto. Sin esta línea el motor arrancaría en modo
# básico (sin reglas NGSI-LD ni anti-evasión).
import project  # noqa: F401


async def repl(config_path: str, tenant: str | None, session_id: str) -> None:
    log_startup_banner("Cliente MCP", mode="Terminal", extra={"config": config_path})
    print("🚀 Iniciando Cliente MCP...")

    client = MCPChatClient(config_path=config_path)

    # Tenant efectivo: --tenant tiene prioridad sobre el default_tenant del config.
    if tenant:
        client.default_tenant = tenant
    tenant_efectivo = client.default_tenant or "(sin tenant)"

    try:
        if not await client.conectar():
            print(
                "❌ Fallo al conectar a los servidores MCP.\n"
                f"   Revisa el fichero de config ({config_path}) y que el Docker "
                "(Orion / QuantumLeap / ChromaDB) esté levantado en los puertos esperados."
            )
            return

        await client.inicializar_agente()

        print(
            f"\n💬 Chat activo │ sesión: {session_id} │ tenant: {tenant_efectivo} │ "
            f"config: {config_path}"
        )
        print("   Escribe 'salir' o Ctrl+C para terminar.\n")

        # _context explícito con el tenant, igual que la API lo recibe vía header
        # NGSILD-Tenant. Si no hay tenant, procesar_peticion_api inyecta el default.
        ctx = {"ngsild_tenant": client.default_tenant} if client.default_tenant else {}

        while True:
            try:
                msg = input("👤 Tú: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if msg.lower() in ("salir", "exit", "quit"):
                break
            if not msg:
                continue

            resp = await client.procesar_peticion_api({
                "request_id": f"cli_{int(time.time() * 1000)}",
                "session_id": session_id,
                "input_text": msg,
                "modality":   "text",
                "_context":   ctx,
            })

            if resp.get("status") == "success":
                print(f"\n🤖 Asistente: {resp['response']['text']}\n")
            else:
                code = resp.get("error_code", "ERROR")
                print(f"\n⚠️  [{code}] {resp.get('error_message', 'Error desconocido')}\n")

    finally:
        log_shutdown_banner("Cliente MCP", reason="terminal cerrada")
        await client.cerrar()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Terminal REPL del sistema MCP multi-agente"
    )
    parser.add_argument(
        "--config", default="config/config.local.yaml",
        help="Ruta al fichero de configuración (default: config/config.local.yaml).",
    )
    parser.add_argument(
        "--tenant", default=None,
        help="Fuerza un tenant concreto (ej: ibermot, metapan). "
             "Si se omite, usa el default_tenant del config.",
    )
    parser.add_argument(
        "--session", default="terminal_user",
        help="Identificador de sesión (default: terminal_user).",
    )
    args = parser.parse_args()

    try:
        asyncio.run(repl(args.config, args.tenant, args.session))
    except KeyboardInterrupt:
        print("\n👋 Hasta luego")


if __name__ == "__main__":
    main()
