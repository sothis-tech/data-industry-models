# src/project/guardrails.py
# -*- coding: utf-8 -*-
"""
GUARDARRAÍLES DETERMINISTAS DEL PROYECTO  (NGSI-LD: Orion-LD + QuantumLeap)
==========================================================================

TODAS las reglas del proyecto viven AQUÍ, en UN solo fichero, como funciones
registradas con @register_validator y separadas por comentarios. Nada de un
fichero por regla.

Cada validador tiene la firma:

    validator(server: str, tool: str, kwargs: dict) -> str | None

Devuelve None si la llamada es válida; si no, un string con el motivo del
rechazo. El motor (engine/mcp_client.py, vía run_validators) entrega ese
motivo al LLM como tool-error para que CORRIJA el flujo (típicamente pasando
primero por Orion para resolver el URN canónico).

Estas reglas son guardarraíles por CÓDIGO: el prompt sube la probabilidad de
comportamiento correcto, pero el código lo GARANTIZA. Son estándar NGSI-LD
(no dependen del dominio del tenant), por lo que sirven para ibermot, metapan
o cualquier tenant futuro.

Los nombres de tools usados aquí coinciden EXACTAMENTE con los expuestos por
los servidores MCP (servers/orion_server.py, servers/quantumleap_server.py).
"""
from __future__ import annotations

import re

from engine.validators import register_validator, register_arg_normalizer
from engine.text_normalize import strip_accents, normalize_fragment


# ────────────────────────────────────────────────────────────────────────
# Patrones y catálogos de tools (estándar NGSI-LD)
# ────────────────────────────────────────────────────────────────────────

# URN NGSI-LD canónica: urn:ngsi-ld:<Type>:<resto>
_URN_NGSI_LD_PATTERN = re.compile(r"^urn:ngsi-ld:[A-Za-z][A-Za-z0-9_]*:.+$")

# Operadores válidos del parámetro `q` de NGSI-LD. Si `q` no contiene NINGUNO,
# no es un filtro: es un fragmento de id mal colocado (devuelve [] siempre).
_NGSILD_Q_OPERATOR = re.compile(r"==|!=|>=|<=|>|<|~=")

# Tools de QuantumLeap que reciben un entity_id (o entity_ids) que DEBE ser
# una URN canónica resuelta previamente por Orion.
_QL_ENTITY_TOOLS = {
    "ql_get_last_value",
    "ql_get_entity_history",
    "ql_get_attribute_history",
    "ql_get_multiple_entities_last_value",
}

# Tools de bajo nivel de QL que devuelven SERIE CRUDA. Sin last_n ni
# aggr_method derrochan tokens trayéndolo todo: se empujan al agregado.
_QL_RAW_SERIES_TOOLS = {
    "ql_get_entity_history",
    "ql_get_attribute_history",
    "ql_get_type_history",
}

# Tools de Orion de listado/conteo donde el `q` mal usado es el fallo típico.
_ORION_LIST_TOOLS = {"list_entities", "count_entities"}


def _is_canonical_urn(s) -> bool:
    return isinstance(s, str) and bool(_URN_NGSI_LD_PATTERN.match(s))


# ════════════════════════════════════════════════════════════════════════
# REGLA 1 — QL: entity_id / entity_ids deben ser URN NGSI-LD canónicas
# ────────────────────────────────────────────────────────────────────────
# El LLM tiende a saltarse Orion y a inventar URNs (urn:ngsi-ld:AGV:002,
# 'prensa-001', …) al llamar a QuantumLeap. Si no es una URN canónica, se
# rechaza y se le manda a resolverla con Orion (resolve_entity_ids).
# ════════════════════════════════════════════════════════════════════════

@register_validator
def ql_entity_id_must_be_canonical_urn(server: str, tool: str, kwargs: dict):
    if server != "quantumleap" or tool not in _QL_ENTITY_TOOLS:
        return None
    if tool == "get_historical_aggregate":
        return None  # tool de alto nivel: resuelve el URN internamente

    # ql_get_multiple_entities_last_value usa 'entity_ids' (lista);
    # el resto usa 'entity_id'.
    eids = kwargs.get("entity_ids")
    if isinstance(eids, list):
        bad = [x for x in eids if not _is_canonical_urn(x)]
        if bad:
            return (
                f"entity_ids contiene URNs no canónicas: {bad[:3]}. "
                f"Cada entity_id debe empezar por 'urn:ngsi-ld:<Type>:'. "
                f"Pide a Agente_orion_ld que resuelva los URN con "
                f"resolve_entity_ids antes de llamar a {tool}."
            )

    eid = kwargs.get("entity_id")
    if isinstance(eid, list):
        bad = [x for x in eid if not _is_canonical_urn(x)]
        if bad:
            return (
                f"entity_id contiene URNs no canónicas: {bad[:3]}. "
                f"Cada entity_id debe empezar por 'urn:ngsi-ld:<Type>:'. "
                f"Pide a Agente_orion_ld que resuelva los URN con "
                f"resolve_entity_ids antes de llamar a {tool}."
            )
    elif eid is not None and not _is_canonical_urn(eid):
        return (
            f"entity_id='{eid}' no es una URN NGSI-LD canónica. "
            f"Debe empezar por 'urn:ngsi-ld:<Type>:'. Pide a "
            f"Agente_orion_ld que resuelva el URN exacto con "
            f"resolve_entity_ids y úsalo aquí sin modificar."
        )
    return None


# ════════════════════════════════════════════════════════════════════════
# REGLA 2 — QL: attr_name con guion es un fragmento de id mal puesto
# ────────────────────────────────────────────────────────────────────────
# En SmartDataModels el campo numérico se llama 'numValue'. Un attr_name
# tipo 'fuerza-meas' es un trozo de id, no un atributo.
# ════════════════════════════════════════════════════════════════════════

@register_validator
def ql_attr_name_hyphen_is_id_fragment(server: str, tool: str, kwargs: dict):
    if server != "quantumleap" or tool not in _QL_ENTITY_TOOLS:
        return None
    attr = kwargs.get("attr_name")
    if isinstance(attr, str) and "-" in attr:
        return (
            f"attr_name='{attr}' parece un fragmento de id, no un "
            f"nombre de atributo. En SmartDataModels el campo numérico se "
            f"llama 'numValue'. Pregunta a Agente_orion_ld el attr_name "
            f"correcto antes de llamar a {tool}."
        )
    return None


# ════════════════════════════════════════════════════════════════════════
# REGLA 3 — QL: no traer serie CRUDA para un agregado
# ────────────────────────────────────────────────────────────────────────
# Si una tool de bajo nivel que devuelve serie cruda se llama SIN last_n ni
# aggr_method, está a punto de traerse toda la serie (derroche de tokens).
# Se empuja a get_historical_aggregate, que agrega en el servidor.
# ════════════════════════════════════════════════════════════════════════

@register_validator
def ql_no_raw_series_for_aggregate(server: str, tool: str, kwargs: dict):
    if server != "quantumleap" or tool not in _QL_RAW_SERIES_TOOLS:
        return None
    has_last_n = kwargs.get("last_n") not in (None, 0, "")
    has_aggr   = bool(kwargs.get("aggr_method"))
    if not has_last_n and not has_aggr:
        return (
            f"{tool} traería la serie temporal CRUDA completa (derroche de "
            f"tokens). Para medias/máximos/mínimos/sumas/conteos o tendencias "
            f"usa get_historical_aggregate(asset_fragment=..., "
            f"aggr_method='avg'|'max'|'min'|'sum'|'count', from_date=..., "
            f"aggr_period=...). Si de verdad necesitas puntos crudos, indica "
            f"last_n=<N> para limitar cuántos."
        )
    return None


# ════════════════════════════════════════════════════════════════════════
# REGLA 4 — Orion list/count: `q` sin operador NGSI-LD es un id mal puesto
# ────────────────────────────────────────────────────────────────────────
# `q` filtra por VALORES DE ATRIBUTOS (attr==valor, attr>30). Un `q` con un
# keyword suelto ('AGV', 'prensa-001') devuelve [] siempre. Para buscar por
# id se usa resolve_entity_ids.
# ════════════════════════════════════════════════════════════════════════

@register_validator
def orion_q_needs_operator(server: str, tool: str, kwargs: dict):
    if server != "orion_ld" or tool not in _ORION_LIST_TOOLS:
        return None
    q = kwargs.get("q")
    if isinstance(q, str) and q.strip() and not _NGSILD_Q_OPERATOR.search(q):
        etype = kwargs.get("entity_type") or "<Type>"
        return (
            f"q='{q}' no es un filtro NGSI-LD válido: no contiene ningún "
            f"operador (==, !=, >, <, >=, <=, ~=). El parámetro `q` filtra "
            f"por VALORES DE ATRIBUTOS, no por fragmento de id — devuelve [] "
            f"siempre que se usa así. Para buscar entidades por keyword de id "
            f"usa: resolve_entity_ids(name_fragment='{q.lower()}', "
            f"entity_type='{etype}'). El schema pre-cargado lista los id "
            f"keywords disponibles por tipo."
        )
    return None


# ════════════════════════════════════════════════════════════════════════
# REGLA 5 — Orion: get_entity_attributes da 404 en este broker → get_entity
# ────────────────────────────────────────────────────────────────────────

@register_validator
def orion_get_entity_attributes_is_404(server: str, tool: str, kwargs: dict):
    if server != "orion_ld" or tool != "get_entity_attributes":
        return None
    eid = kwargs.get("entity_id", "<URN>")
    return (
        f"get_entity_attributes no está disponible en este Context Broker "
        f"(devuelve 404). Para obtener los atributos/propiedades de una "
        f"entidad usa get_entity(entity_id='{eid}'): devuelve la entidad "
        f"COMPLETA con todos sus atributos en una sola llamada."
    )

# ════════════════════════════════════════════════════════════════════════
# NORMALIZADOR DE FRAGMENTOS DE BÚSQUEDA  (determinista, antes de resolver)
# ════════════════════════════════════════════════════════════════════════
# El LLM construye fragmentos como 'prensa 002 presión hid', 'agv carroceria 2
# nivel bateria' o 'presion planta'. La resolución por id (resolve_entity_ids /
# get_historical_aggregate) exige que TODAS las palabras aparezcan en el id, y
# los ids NGSI-LD de este data space:
#   - no llevan acentos      (presion, bateria)  → quitamos tildes
#   - usan ciertas palabras como ruido           → quitamos stopwords de relleno
#   - abrevian algunos términos                  → aplicamos sinónimos
#   - usan numeración con padding (001, 002…)    → reescribimos '2' → '002'
# Todo esto es estándar de cómo hablan los usuarios vs cómo son los ids; va por
# CÓDIGO para no depender del prompt.

# Palabras de relleno que el usuario dice pero NUNCA están en un id.
_FRAGMENT_STOPWORDS = {
    # genéricas de "lectura/valor"
    "nivel", "valor", "valores", "actual", "actuales", "ahora", "mismo",
    "dato", "datos", "medida", "medidas", "medicion", "mediciones", "lectura",
    "lecturas", "monitorizada", "monitorizado", "monitorizadas", "monitorizados",
    "registrado", "registrada", "registro", "estado",
    # ubicación/genéricas que no son keyword de id
    "planta", "sistema", "fabrica", "nave", "zona", "area", "areas",
    # conectores
    "de", "del", "la", "el", "los", "las", "un", "una", "en", "y", "o",
    "que", "se", "su", "sus", "con", "para", "por", "esta", "este",
}

# Sinónimos: término del usuario → token tal cual aparece en los ids.
_FRAGMENT_SYNONYMS = {
    "presion": "presion",      # ya sin acento; aquí dejaríamos abreviaturas reales
    "hidraulica": "hid",
    "temperatura": "temp",
    "velocidad": "velocidad",  # se conserva (los ids usan 'velocidad' completa)
    "bateria": "bateria",
}

# Tools (server, tool, parámetro) cuyo fragmento de búsqueda normalizamos.
_FRAGMENT_TARGETS = {
    ("orion_ld",    "resolve_entity_ids"):       "name_fragment",
    ("quantumleap", "get_historical_aggregate"): "asset_fragment",
}

# Detecta un número "suelto" de 1-2 dígitos para reescribirlo con padding a 3.
_BARE_NUM_RE = re.compile(r"^\d{1,2}$")


def _pad_numbers(fragment: str) -> str:
    """
    Reescribe números sueltos de 1-2 dígitos a 3 cifras con ceros a la
    izquierda ('2' → '002'), porque los ids del data space usan ese padding
    (prensa-002, agv-carroceria-002...). Números ya de 3+ cifras o pegados a
    texto no se tocan.
    """
    out = []
    for tok in fragment.split(" "):
        if _BARE_NUM_RE.match(tok):
            out.append(tok.zfill(3))
        else:
            out.append(tok)
    return " ".join(out)


@register_arg_normalizer
def normalize_search_fragment(server: str, tool: str, kwargs: dict) -> dict:
    """
    Limpia el fragmento de búsqueda de las tools de resolución por id:
    quita acentos, stopwords de relleno, aplica sinónimos y padding numérico.
    No toca nada si la tool no está en _FRAGMENT_TARGETS o no hay fragmento.
    """
    param = _FRAGMENT_TARGETS.get((server, tool))
    if not param:
        return kwargs
    raw = kwargs.get(param)
    if not isinstance(raw, str) or not raw.strip():
        return kwargs

    cleaned = normalize_fragment(
        raw, stopwords=_FRAGMENT_STOPWORDS, synonyms=_FRAGMENT_SYNONYMS
    )
    cleaned = _pad_numbers(cleaned)

    if cleaned and cleaned != raw:
        kwargs[param] = cleaned
    return kwargs