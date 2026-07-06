# src/project/behavior_guards.py
# -*- coding: utf-8 -*-
"""
COMPORTAMIENTO DETERMINISTA DEL PROYECTO
========================================

Dos garantías por código (no por prompt):

1. ANTI-EVASIÓN (is_dodge + DODGE_RETRY_SUFFIX)
   El fallo nº1 del benchmark: el modelo OFRECE o PREGUNTA en vez de ACTUAR
   ("¿quieres que liste…?", "por favor, indícame…") y no llama a ninguna
   herramienta (tools=0). is_dodge() lo detecta; el motor reintenta UNA vez
   añadiendo DODGE_RETRY_SUFFIX, un sufijo imperativo que prohíbe ofrecer y
   obliga a ejecutar.

2. RECONCILIACIÓN DE TOKENS (reconcile_token_metrics)
   El token_tracker directo no ve los sub-agentes (especialistas), así que
   subcontaba (~16 tokens/query irreales). El TokenCountingHandler de
   LlamaIndex sí los ve. Tomamos el MÁXIMO de ambas fuentes por campo.

Ambas se REGISTRAN en el motor al importar `project`. Si `project` no se
importa, el motor funciona sin anti-evasión y con el conteo directo (REGLA
DE ORO: arranca igual).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Set

from engine.validators import (
    register_dodge_detector,
    register_metrics_reconciler,
    register_routing_guard,
    register_schema_observer,
)
from engine.text_normalize import strip_accents


# ════════════════════════════════════════════════════════════════════════
# 1. ANTI-EVASIÓN
# ════════════════════════════════════════════════════════════════════════

# Patrones que delatan una evasión: el modelo se ofrece a hacer algo o pide
# permiso/datos en lugar de ejecutar. Se han elegido para cazar las formas
# reales vistas en el benchmark sin disparar con respuestas legítimas (p.ej.
# devolver un dato y NADA más no matchea).
_DODGE_PATTERNS = [
    re.compile(r"¿\s*quieres\s+que\b", re.IGNORECASE),
    re.compile(r"¿\s*deseas\s+que\b", re.IGNORECASE),
    re.compile(r"¿\s*te\s+gustar[ií]a\b", re.IGNORECASE),
    re.compile(r"¿\s*quieres\s+(que\s+)?(te\s+)?(lo\s+)?(liste|muestre|busque|consulte|indique)\b", re.IGNORECASE),
    re.compile(r"¿\s*necesitas\s+(que|alguna|m[áa]s)\b", re.IGNORECASE),
    re.compile(r"\b(por\s+favor,?\s+)?ind[íi]came\b", re.IGNORECASE),
    re.compile(r"\bdime\s+(cu[áa]l|qu[ée]|el|la|los|las)\b", re.IGNORECASE),
    re.compile(r"\bproporci[óo]name\b", re.IGNORECASE),
    re.compile(r"\bespecif[íi]came\b", re.IGNORECASE),
    re.compile(r"\b(puedo|podr[íi]a)\s+(ayudarte|listar|mostrar|buscar|consultar|proporcionar)\b.*\bsi\b", re.IGNORECASE),
    re.compile(r"\bsi\s+(me\s+)?(lo\s+)?(deseas|quieres|indicas|proporcionas)\b", re.IGNORECASE),
    re.compile(r"\bh[áa]zmelo\s+saber\b", re.IGNORECASE),
    re.compile(r"\bav[íi]same\s+si\b", re.IGNORECASE),
    re.compile(r"\b¿\s*sobre\s+cu[áa]l\b", re.IGNORECASE),
    re.compile(r"\b¿\s*a\s+qu[ée]\b.*\bte\s+refieres\b", re.IGNORECASE),
]


# Negaciones de DISPONIBILIDAD: "no hay datos", "no se dispone", "no está
# disponible"... Son evasión SOLO cuando se emiten con tools=0, es decir, el
# Gestor afirma que no hay datos SIN haber consultado nada. Si hubo consulta
# (tools>0) y el especialista devolvió un negativo legítimo, NO se dispara
# (la condición num_tools==0 de is_dodge ya lo excluye). Este es el fallo más
# caro visto en benchmark: "No hay datos sobre la fuerza de la prensa 001" con
# cero delegaciones, en preguntas que con consulta sí tienen respuesta.
_NEGATION_NO_DATA_PATTERNS = [
    re.compile(r"\bno\s+hay\s+(datos|informaci[óo]n|registros?|lecturas?)\b", re.IGNORECASE),
    re.compile(r"\bno\s+se\s+dispone\b", re.IGNORECASE),
    re.compile(r"\bno\s+(hay|existe[n]?)\s+datos\s+disponibles?\b", re.IGNORECASE),
    re.compile(r"\bno\s+(est[áa]|hay)\s+disponible[s]?\b", re.IGNORECASE),
    re.compile(r"\bno\s+(dispongo|tengo)\s+de\s+(datos|informaci[óo]n)\b", re.IGNORECASE),
    re.compile(r"\bno\s+se\s+(puede|pudo)\s+(determinar|obtener|consultar)\b", re.IGNORECASE),
    re.compile(r"\bsin\s+datos\s+disponibles?\b", re.IGNORECASE),
]

# Salvaguarda anti-falso-positivo: frases que SÍ son respuestas legítimas con
# tools=0 y que jamás deben reintentarse (meta-preguntas, solo-lectura).
_LEGIT_NO_TOOL_PATTERNS = [
    re.compile(r"\bsolo\s+lectura\b", re.IGNORECASE),
    re.compile(r"\bread[- ]?only\b", re.IGNORECASE),
    re.compile(r"\bpuedo\s+(consultar|ayudarte\s+con|darte)\b", re.IGNORECASE),  # descripción de capacidades
]


# Sufijo imperativo que se añade a la pregunta original en el reintento.
# Prohíbe ofrecer/preguntar y obliga a usar las herramientas y dar el dato.
DODGE_RETRY_SUFFIX = (
    "\n\n[INSTRUCCIÓN OBLIGATORIA] No ofrezcas ni preguntes: ACTÚA AHORA. "
    "Delega en el especialista adecuado, llama a las herramientas necesarias "
    "y devuelve el dato concreto. PROHIBIDO responder con '¿quieres que…?', "
    "'indícame…', 'puedo… si deseas…' o cualquier oferta. Si tras usar las "
    "herramientas no hay datos, dilo en una frase ('Sin datos…') y para. "
    "No hagas ninguna pregunta de vuelta al usuario."
)


def is_dodge(text: str, num_tools: int) -> bool:
    """
    True si la respuesta es una EVASIÓN. Dos formas, ambas SOLO con tools=0
    (si se usó alguna herramienta, no es evasión):

      (a) OFERTA/PREGUNTA en vez de actuar ("¿quieres que…?", "indícame…").
      (b) NEGACIÓN-SIN-CONSULTA: afirma "no hay datos / no se dispone / no
          está disponible" SIN haber llamado a ninguna herramienta. Es un
          falso negativo: el Gestor niega sin consultar. Forzamos reintento.

    Salvaguarda: frases legítimas con tools=0 (meta-preguntas de capacidad,
    "solo lectura") nunca se marcan como evasión.
    """
    if num_tools and num_tools > 0:
        return False
    if not text:
        return False

    # Nunca tratar como evasión una respuesta legítima de capacidad/solo-lectura
    if any(p.search(text) for p in _LEGIT_NO_TOOL_PATTERNS):
        return False

    # (a) oferta/pregunta
    if any(p.search(text) for p in _DODGE_PATTERNS):
        return True

    # (b) negación de disponibilidad sin haber consultado nada
    if any(p.search(text) for p in _NEGATION_NO_DATA_PATTERNS):
        return True

    return False


# ════════════════════════════════════════════════════════════════════════
# 2. RECONCILIACIÓN DE TOKENS
# ════════════════════════════════════════════════════════════════════════

def _li_counts(li_token_counter: Any) -> Dict[str, int]:
    """Extrae los conteos del TokenCountingHandler de LlamaIndex (si lo hay)."""
    if li_token_counter is None:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    try:
        prompt     = int(getattr(li_token_counter, "prompt_llm_token_count", 0) or 0)
        completion = int(getattr(li_token_counter, "completion_llm_token_count", 0) or 0)
        total      = int(getattr(li_token_counter, "total_llm_token_count", 0) or 0)
        if total <= 0:
            total = prompt + completion
        return {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": total,
        }
    except Exception:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def reconcile_token_metrics(direct_totals: Dict[str, int], li_token_counter: Any = None) -> Dict[str, int]:
    """
    Reconcilia el conteo de tokens tomando el MÁXIMO por campo entre:
      - el token_tracker directo (intercepta el cliente, pero puede no ver
        a los sub-agentes según el flujo), y
      - el TokenCountingHandler de LlamaIndex (ve también los especialistas).

    Así se evita el subconteo irreal (~16 tokens/query). num_llm_calls se
    conserva del tracker directo (es quien cuenta llamadas).
    """
    direct = direct_totals or {}
    d_prompt     = int(direct.get("prompt_tokens", 0) or 0)
    d_completion = int(direct.get("completion_tokens", 0) or 0)
    d_total      = int(direct.get("total_tokens", 0) or 0)
    d_calls      = int(direct.get("num_llm_calls", 0) or 0)

    li = _li_counts(li_token_counter)

    prompt     = max(d_prompt, li["prompt_tokens"])
    completion = max(d_completion, li["completion_tokens"])
    total      = max(d_total, li["total_tokens"], prompt + completion)

    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "num_llm_calls": d_calls,
    }


# ════════════════════════════════════════════════════════════════════════
# 3. CLASIFICACIÓN DE INTENCIÓN: documental (RAG) vs estructural (Orion/QL)
# ════════════════════════════════════════════════════════════════════════
# Problema observado: el Gestor a veces delega a rag_knowledge preguntas que
# son de datos en vivo ("¿qué operaciones están registradas?", "¿qué máquinas
# hay en la nave X?"). Eso es estructura (Orion), no documentación.
#
# El discriminante NO es la entidad mencionada (un AGV aparece tanto en "batería
# del AGV" como en "manual del AGV"), sino la INTENCIÓN:
#   - documental → manual, procedimiento, norma, especificación, cómo se hace…
#   - estructural → qué hay, cuántos, lista, estado actual, valor…
#
# REGLA DE SEGURIDAD (anti-falsos-positivos): solo marcamos como "mal enrutada
# a RAG" si se cumplen DOS cosas a la vez:
#   (1) la instrucción casa con algún keyword ESTRUCTURAL del data space, Y
#   (2) NO contiene ninguna señal DOCUMENTAL.
# Ante cualquier duda (señal documental presente, o sin keywords claros), NO se
# redirige: es preferible dejar pasar una consulta a RAG que bloquear una
# legítima. Así el guardrail nunca empeora un caso que ya iba bien.

# (2) Señales de intención DOCUMENTAL. Lingüísticas y genéricas (no de dominio):
# si aparece cualquiera, la consulta PUEDE ser legítima de RAG → no redirigir.
_DOC_INTENT = {
    "manual", "manuales", "documento", "documentos", "documentacion",
    "procedimiento", "procedimientos", "instruccion", "instrucciones",
    "especificacion", "especificaciones", "ficha", "datasheet",
    "norma", "normas", "normativa", "reglamento", "protocolo",
    "epi", "epis", "seguridad", "mantenimiento", "preventivo",
    "intervalo", "cada", "recomendado", "recomendada", "recomienda",
    "par", "apriete", "viscosidad", "limite", "limites", "rango",
    "codigo", "codigos", "error", "errores", "alarma", "alarmas",
    "como", "deberia", "hay que", "segun", "dice", "indica",
    "garantia", "calibrar", "calibracion", "lubricacion",
}

# (1) Verbos/sustantivos de intención ESTRUCTURAL (datos en vivo de Orion).
# Genéricos también; el ANCLA de dominio son los keywords del schema (abajo).
_STRUCT_INTENT = {
    "operacion", "operaciones", "registrada", "registradas", "registrado",
    "registrados", "lista", "listar", "listame", "enumera", "cuantos",
    "cuantas", "cuales", "estado", "online", "offline", "activa", "activas",
    "activo", "activos", "valor", "valores", "actual", "actuales",
    "pertenece", "componentes", "relacion", "relaciones",
}

# Keywords estructurales del data space, derivados del schema en runtime
# (ver _schema_observer). Se usan para ENRIQUECER la intención estructural con
# los nombres de los tipos de entidad del data space (p.ej. 'operaciones',
# 'maquinas'), que son señales estructurales legítimas y específicas del
# espacio de datos. Arrancan vacíos para no hardcodear dominio.
_SCHEMA_STRUCT_TERMS: Set[str] = set()


def set_schema_keywords(type_terms) -> None:
    """
    Carga términos estructurales derivados de los NOMBRES DE TIPO del schema
    (no los id-keywords, que son ambiguos). Normaliza minúsculas/sin acentos.
    Lo llama el observador del schema; independiente del data space.
    """
    global _SCHEMA_STRUCT_TERMS
    cleaned = set()
    for kw in (type_terms or []):
        if not kw:
            continue
        tok = strip_accents(str(kw).lower()).strip()
        for part in re.split(r"[\s\-_/.,;:]+", tok):
            if len(part) >= 4:
                cleaned.add(part)
    if cleaned:
        _SCHEMA_STRUCT_TERMS = cleaned


def _tokens(text: str) -> Set[str]:
    base = strip_accents((text or "").lower())
    return {t for t in re.split(r"[\s\-_/.,;:¿?¡!()]+", base) if t}


def is_misrouted_to_docs(instruction: str) -> bool:
    """
    True si una instrucción dirigida a RAG es en realidad ESTRUCTURAL y debería
    ir a Orion/QL. Conservador: exige señal estructural Y ausencia de señal
    documental. Ante la duda, devuelve False (no redirige).

    Disparador = INTENCIÓN estructural explícita ("qué operaciones están
    registradas", "lista", "cuántos", "estado actual"…) o un término de TIPO del
    schema ("operaciones", "máquinas"…). La sola mención de un id-keyword
    ambiguo (p.ej. 'agv') NO basta, porque aparece tanto en consultas de datos
    como documentales ("manual del AGV"); en ese caso dejamos decidir al LLM.
    """
    if not instruction:
        return False
    toks = _tokens(instruction)

    # (2) Si hay CUALQUIER señal documental, es legítima de RAG → no tocar.
    if toks & _DOC_INTENT:
        return False

    # (1) Intención estructural explícita, o término de tipo del schema.
    return bool(toks & _STRUCT_INTENT) or bool(toks & _SCHEMA_STRUCT_TERMS)


# ════════════════════════════════════════════════════════════════════════
# REGISTRO EN EL MOTOR
# ════════════════════════════════════════════════════════════════════════

register_dodge_detector(is_dodge, retry_suffix=DODGE_RETRY_SUFFIX)
register_metrics_reconciler(reconcile_token_metrics)


# Mensaje que se devuelve al Gestor/agente cuando se intercepta una consulta
# estructural mal dirigida a documentación. Le obliga a usar el especialista
# de datos en vivo en lugar de RAG.
_ROUTING_REDIRECT_MSG = (
    "Esta consulta es sobre datos/estructura del data space (entidades, "
    "operaciones, máquinas, estado, valores), NO sobre documentación. "
    "NO uses el especialista de documentación (RAG). Delega en el "
    "especialista de Orion-LD para obtener los datos en vivo del broker."
)


def _routing_guard(target: str, instruction: str) -> bool:
    """
    Solo evalúa destinos de documentación (rag_knowledge). Para cualquier otro
    destino, no interviene. Devuelve True si la instrucción es estructural y
    está mal dirigida a RAG.
    """
    if "rag" not in (target or "").lower():
        return False
    return is_misrouted_to_docs(instruction)


def _schema_observer(tenant: str, schema_text: str) -> None:
    """
    Observador del schema: extrae los NOMBRES DE TIPO del data space y los
    carga como términos estructurales. NO usa los id-keywords (agv, prensa…)
    porque son ambiguos entre datos y documentación. Funciona en cualquier
    data space sin hardcodear dominio.

    De 'TYPE ManufacturingMachineOperation (15 entities)' extrae el nombre y
    sus trozos camelCase ('manufacturing','machine','operation'), que dan
    señales estructurales como 'operation'/'operacion' tras normalizar. Para
    cubrir el español, añadimos también la forma con los chunks sueltos.
    """
    if not schema_text:
        return
    terms: Set[str] = set()
    for line in schema_text.splitlines():
        s = line.strip()
        if s.lower().startswith("type "):
            part = s[5:].split("(")[0].strip()
            terms.add(part)
            for chunk in re.findall(r"[A-Z][a-z]+", part):
                terms.add(chunk)
    set_schema_keywords(terms)


register_routing_guard(_routing_guard, redirect_msg=_ROUTING_REDIRECT_MSG)
register_schema_observer(_schema_observer)