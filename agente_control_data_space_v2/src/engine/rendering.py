# src/engine/rendering.py
# -*- coding: utf-8 -*-
"""
Render de la respuesta final por MODALIDAD a partir de las salidas FIELES de
los especialistas (no del resumen del Gestor, que colapsa listas).

Garantía: el LLM solo PULE. El suelo es el dato completo de los especialistas.
Si el formateo falla, vuelve vacío, o deja fuera algún valor numérico
(comprobación determinista), servimos las salidas de los especialistas tal
cual. Nunca servimos MENOS dato del que trajeron.

Parte del MOTOR: no conoce el dominio.
"""
from __future__ import annotations

import re
from typing import Any, List

from engine.logging_setup import get_logger
from engine.response_processing import (
    build_response_payload, clean_text_response, clean_speech_response,
)

logger = get_logger("mcp.client")

_NO_SENTENCE_CAP = 100_000  # clean_speech sin recorte: queremos completitud

_TEXT_RULES = (
    "Eres un formateador. Recibes la PREGUNTA del usuario y los DATOS ya "
    "obtenidos por los especialistas. Devuelve la respuesta final en español "
    "con Markdown.\n"
    "REGLAS:\n"
    "- Incluye TODOS los valores e ítems de los DATOS. NUNCA resumas en "
    "rangos, NUNCA omitas un ítem, NUNCA inventes nada que no esté en DATOS.\n"
    "- Pon en **negrita** los valores clave. Si hay varios ítems con varias "
    "propiedades, usa una TABLA Markdown; si es una sola lista, viñetas.\n"
    "- Sin preámbulo, sin frases de cierre, sin preguntas finales.\n"
    "- Si los DATOS dicen que no hay datos, dilo en una frase y nada más.\n"
)

_SPEECH_RULES = (
    "Eres un formateador para voz (lectura por TTS). Recibes la PREGUNTA y los "
    "DATOS obtenidos. Devuelve la respuesta en español HABLADO y natural.\n"
    "REGLAS:\n"
    "- Incluye TODOS los valores e ítems de los DATOS. NUNCA omitas ninguno.\n"
    "- Texto plano: SIN Markdown, sin asteriscos, sin viñetas, sin tablas, sin "
    "símbolos ni emojis. Frases corridas, fáciles de escuchar.\n"
    "- Sin preámbulo ni frases de cierre.\n"
)

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _join_sources(specialist_outputs: List[dict]) -> str:
    parts = [(o.get("output") or "").strip() for o in (specialist_outputs or [])]
    return "\n\n".join(p for p in parts if p)


def _covers_all_numbers(sources: str, rendered: str) -> bool:
    """True si TODO número de `sources` aparece en `rendered` (tolerando . o ,)."""
    rnums = set(_NUM_RE.findall(rendered))
    for n in _NUM_RE.findall(sources):
        if not ({n, n.replace(".", ","), n.replace(",", ".")} & rnums):
            return False
    return True


def _fallback(sources: str, modality: str, base: dict) -> dict:
    base["text"] = clean_text_response(sources)
    base["speech"] = (
        (clean_speech_response(sources, max_sentences=_NO_SENTENCE_CAP) or sources)
        if modality == "speech" else None
    )
    return base


async def render_payload(
    question: str,
    specialist_outputs: List[dict],
    gestor_text: str,
    modality: str,
    llm: Any,
) -> dict:
    """{"text","speech","data"} listo para servir. Sin especialistas → como antes."""
    # base aporta el campo `data` (artefactos) y el comportamiento por defecto.
    base = build_response_payload(gestor_text, modality=modality)

    sources = _join_sources(specialist_outputs)
    if not sources:
        return base  # meta-pregunta / sin delegación

    is_speech = (modality == "speech")
    rules = _SPEECH_RULES if is_speech else _TEXT_RULES
    prompt = f"{rules}\nPREGUNTA:\n{question}\n\nDATOS:\n{sources}\n\nRESPUESTA:"

    try:
        resp = await llm.acomplete(prompt)
        rendered = (getattr(resp, "text", None) or "").strip()
    except Exception as e:
        logger.warning("Render por modalidad falló (%s); sirvo dato completo", e)
        return _fallback(sources, modality, base)

    if not rendered or not _covers_all_numbers(sources, rendered):
        if rendered:
            logger.warning("Render incompleto (faltan valores); sirvo dato completo")
        return _fallback(sources, modality, base)

    base["text"] = clean_text_response(rendered)
    base["speech"] = (
        (clean_speech_response(rendered, max_sentences=_NO_SENTENCE_CAP) or rendered)
        if is_speech else None
    )
    return base


__all__ = ["render_payload"]