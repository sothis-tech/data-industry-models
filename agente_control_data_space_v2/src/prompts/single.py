# src/prompts/single.py
# -*- coding: utf-8 -*-
"""
System Prompt — MODO AGENTE ÚNICO (single).

Un solo FunctionAgent recibe TODAS las tools de todos los MCP activos
(Orion-LD, QuantumLeap, RAG) y decide por sí mismo qué herramienta usar. No
hay delegación ni Gestor. Este prompt fusiona, en uno, el rol de orquestador
y el conocimiento operativo de cada dominio.

Mantiene las MISMAS invariantes que el modo multi (domain-agnostic,
discovery-first, anti-loop, anti-hallucination) y los MISMOS guardrails
deterministas del cliente siguen aplicando igual (envuelven las tools, no
dependen del número de agentes).

Reutiliza BASE_SYSTEM_PROMPT y los sub-prompts de dominio definidos en
prompts.multi para no duplicar texto: el prompt single es la concatenación
del rol único + las guías de Orion, QuantumLeap y RAG.
"""
from __future__ import annotations

from prompts.multi import (
    BASE_SYSTEM_PROMPT,
    ORION_LD_SYSTEM_PROMPT,
    QUANTUMLEAP_SYSTEM_PROMPT,
    RAG_SYSTEM_PROMPT,
)


# El rol único: mismas reglas de no-alucinación y anti-loop que el Gestor,
# pero ejecutando directamente en vez de delegar.
SINGLE_ROLE = """
## YOUR ROLE: SINGLE DATA SPACE AGENT (you hold ALL tools)

You have DIRECT access to every tool of every active store. There is no
delegation: you classify the question and CALL the right tool yourself.

═══════════════════════════════════════════════════════════════════════
## ⛔ RULE ZERO — DISCOVERY FIRST, NEVER FABRICATE IDENTIFIERS
═══════════════════════════════════════════════════════════════════════
You do NOT know this tenant's entity types, id format or URNs from training.
The injected schema is the ONLY source of truth.
  - NEVER write a URN from memory. Resolve it with resolve_entity_ids first.
  - To find entities by id keyword use resolve_entity_ids(name_fragment=...,
    entity_type='<Type>'), NEVER list_entities(q='<keyword>') — `q` filters
    attribute VALUES, not ids, and returns [] when misused.

═══════════════════════════════════════════════════════════════════════
## TEMPORAL CLASSIFICATION → WHICH TOOLSET
═══════════════════════════════════════════════════════════════════════
  CURRENT value / structure / counts / relationships / "what info has X"
        → Orion-LD tools (get_entity, resolve_entity_ids, list_entities,
          count_entities, get_schema_summary...).
  HISTORICAL / trend / aggregate (media, máximo, mínimo, suma, conteo,
        evolución, ayer, última semana, entre fechas)
        → QuantumLeap tool get_historical_aggregate (resolves the URN
          internally from a fragment; one shot).
  DOCUMENTATION (procedimiento, especificación, norma, límite, intervalo,
        "qué dice el manual")
        → RAG tools (búsqueda en documentación indexada).

═══════════════════════════════════════════════════════════════════════
## ANTI-LOOP
═══════════════════════════════════════════════════════════════════════
1. For a CURRENT value: resolve once → get_entity once → answer. Do NOT dump
   dozens of entities to find one.
2. "sin datos", "found=false", "ambiguous=true", "0 documentos" → FINAL
   answer in one sentence. STOP. Never retry the same call.
3. Never repeat an identical tool call.
"""


# Las guías de dominio: reutilizamos las secciones operativas de cada
# especialista (decision trees, few-shots, formato de salida) tal cual, ya
# que en single el mismo agente necesita ESE conocimiento para usar bien las
# tools. Quitamos el BASE_SYSTEM_PROMPT repetido de cada uno (ya está arriba).
def _strip_base(prompt: str) -> str:
    """Quita el BASE_SYSTEM_PROMPT inicial de un sub-prompt de dominio."""
    if prompt.startswith(BASE_SYSTEM_PROMPT):
        return prompt[len(BASE_SYSTEM_PROMPT):]
    return prompt


_ORION_GUIDE = "\n\n## ── ORION-LD TOOLSET ──" + _strip_base(ORION_LD_SYSTEM_PROMPT)
_QL_GUIDE    = "\n\n## ── QUANTUMLEAP TOOLSET ──" + _strip_base(QUANTUMLEAP_SYSTEM_PROMPT)
_RAG_GUIDE   = "\n\n## ── RAG / DOCUMENTATION TOOLSET ──" + _strip_base(RAG_SYSTEM_PROMPT)


SINGLE_SYSTEM_PROMPT = (
    BASE_SYSTEM_PROMPT
    + SINGLE_ROLE
    + _ORION_GUIDE
    + _QL_GUIDE
    + _RAG_GUIDE
    + """

## OUTPUT
Spanish. Max 3 sentences. Key value/list first. No closing phrases, no
follow-up questions. A truthful "no encontrado / sin datos" IS complete.
"""
)


def get_system_prompt(server_type: str, modality: str = "text") -> str:
    """
    En modo single SIEMPRE devolvemos el mismo prompt unificado, sea cual sea
    el `server_type` que pida el motor (no hay roles separados). Mantener la
    firma idéntica a la del modo multi permite que el registro del motor sea
    intercambiable según el modo.
    """
    return SINGLE_SYSTEM_PROMPT


__all__ = ["SINGLE_SYSTEM_PROMPT", "get_system_prompt"]
