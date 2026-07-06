# src/prompts/__init__.py
# -*- coding: utf-8 -*-
"""
Prompts del proyecto, seleccionables por MODO AGÉNTICO.

  - multi.py  → un prompt por rol (Gestor + Orion + QuantumLeap + RAG).
  - single.py → un único prompt que combina orquestación + dominios.

`activate(mode)` registra en el motor (engine.validators) el proveedor de
prompts correcto según el modo configurado en `agent.agent_mode`:
  - "multi"  → prompts.multi.get_system_prompt
  - "single" → prompts.single.get_system_prompt

El cliente llama a activate(mode) al construirse, ANTES de crear los agentes.
Si nadie llama a activate(), el motor usa su prompt genérico (regla de oro).

Aunque los textos son específicos del proyecto NGSI-LD, el MOTOR sigue siendo
agnóstico: solo invoca get_system_prompt(rol) a través del registro.
"""
from __future__ import annotations

from engine.logging_setup import get_logger
from engine.validators import register_prompt_provider

logger = get_logger("mcp.client")

_VALID_MODES = ("multi", "single")


def activate(mode: str = "multi") -> str:
    """
    Registra el proveedor de prompts del modo indicado. Devuelve el modo
    efectivamente activado (cae a 'multi' si el valor no es válido).
    """
    m = (mode or "multi").strip().lower()
    if m not in _VALID_MODES:
        logger.warning("agent_mode '%s' no reconocido; usando 'multi'", mode)
        m = "multi"

    if m == "single":
        from prompts.single import get_system_prompt as _provider
    else:
        from prompts.multi import get_system_prompt as _provider

    register_prompt_provider(_provider)
    logger.info("Prompts activados │ modo=%s", m)
    return m


__all__ = ["activate"]
