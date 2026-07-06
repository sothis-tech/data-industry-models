# src/engine/__init__.py
"""
MOTOR reutilizable del cliente MCP multi-agente.

REGLA DE ORO: este paquete NO importa nada de `project/`. Funciona de forma
básica aunque `project/` esté vacío. Es `project/` quien, al importarse,
REGISTRA sus reglas/prompts/comportamientos en `engine.validators`.
"""
