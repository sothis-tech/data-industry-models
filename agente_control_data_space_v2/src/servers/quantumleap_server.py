# servers/quantumleap_server.py
# -*- coding: utf-8 -*-
"""
Servidor MCP para Quantum Leap (STH-Comet compatible).

v2.1 — Tool de alto nivel `get_historical_aggregate`
====================================================
Añade una tool de alto nivel que esconde la cadena Orion → QL dentro de
una sola llamada:

  1) Resuelve la URN del DeviceMeasurement vía Orion-LD (HTTP).
  2) Lee la unidad y la propiedad controlada de Orion (best-effort).
  3) Consulta QuantumLeap con la URN canónica y attr_name='numValue'.

El orquestador ya no necesita encadenar dos especialistas para preguntas
de histórico/agregación: una sola tool entrega resultado, metadata y
resumen humano listo para retransmitir.

Las tools low-level (`ql_get_attribute_history`, `ql_get_last_value`,
`ql_list_*`, etc.) se mantienen tal cual como escape hatch para casos
donde el orquestador ya tiene la URN exacta o quiere explorar QL.

Soporte multi-tenant
--------------------
Cada tool acepta `fiware_service: str | None = None`. mcp_client lo
inyecta automáticamente con el tenant activo. Para las llamadas internas
a Orion se traduce a la cabecera `NGSILD-Tenant` (mismo valor de tenant).

Configuración (env vars desde config.yaml):
  QL_HOST              — host de Quantum Leap        (default: localhost)
  QL_PORT              — puerto HTTP                 (default: 8669)
  QL_FIWARE_SERVICE    — tenant por defecto          (default: "")
  QL_FIWARE_SERVICEPATH — Fiware-ServicePath         (default: "/")
  QL_TIMEOUT           — timeout HTTP en segundos    (default: 30)
  ORION_URL            — base URL de Orion-LD        (default: http://orion-ld:1026)
  ORION_TIMEOUT        — timeout HTTP en segundos    (default: 15)
  SDM_VALUE_TYPE_URI   — URI completa del VALUE TYPE (default: SDM DeviceMeasurement)
  SDM_VALUE_TYPE_SHORT — nombre corto del VALUE TYPE (default: DeviceMeasurement)
  SDM_VALUE_ATTR       — nombre del atributo numérico (default: numValue)
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import unicodedata as _unicodedata

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("quantumleap-server")

# ─── Configuración QL ─────────────────────────────────────────────────────────

QL_HOST              = os.getenv("QL_HOST",                "localhost")
QL_PORT              = int(os.getenv("QL_PORT",            "8669"))
QL_FIWARE_SERVICE    = os.getenv("QL_FIWARE_SERVICE",      "")
QL_FIWARE_SERVICEPATH = os.getenv("QL_FIWARE_SERVICEPATH", "/")
QL_TIMEOUT           = int(os.getenv("QL_TIMEOUT",         "30"))

_QL_BASE = f"http://{QL_HOST}:{QL_PORT}"

# ─── Configuración Orion (para resolución interna) ────────────────────────────

ORION_URL          = os.getenv("ORION_URL", "http://orion-ld:1026")
ORION_API_BASE     = f"{ORION_URL}/ngsi-ld/v1"
ORION_TIMEOUT      = int(os.getenv("ORION_TIMEOUT", "15"))

# Convención SmartDataModels — si el tenant usa otro VALUE TYPE, override por env.
SDM_VALUE_TYPE_URI   = os.getenv(
    "SDM_VALUE_TYPE_URI",
    "https://smartdatamodels.org/dataModel.Device/DeviceMeasurement",
)
SDM_VALUE_TYPE_SHORT = os.getenv("SDM_VALUE_TYPE_SHORT", "DeviceMeasurement")
SDM_VALUE_ATTR       = os.getenv("SDM_VALUE_ATTR",       "numValue")

# ─── Constantes ───────────────────────────────────────────────────────────────

_VALID_AGGR_METHODS = {"count", "sum", "avg", "min", "max"}
_VALID_AGGR_PERIODS = {"year", "month", "day", "hour", "minute", "second"}

_TENANT_PARAM_DOC = (
    "\n- fiware_service: (opcional) tenant. Si se omite usa el configurado por "
    "defecto. mcp_client lo inyecta automáticamente con el tenant activo."
)


# ─── Helpers internos QL ──────────────────────────────────────────────────────

def _log(msg: str):
    print(f"[QuantumLeap] {msg}", file=sys.stderr)


def _effective_service(override: str | None = None) -> str:
    """Prioridad: override > QL_FIWARE_SERVICE. '' = sin tenant explícito."""
    if override is not None:
        return override
    return QL_FIWARE_SERVICE


def _headers(fiware_service: str | None = None) -> dict:
    h = {"Accept": "application/json", "Content-Type": "application/json"}
    service = _effective_service(fiware_service)
    if service:
        h["Fiware-Service"] = service
    if QL_FIWARE_SERVICEPATH:
        h["Fiware-ServicePath"] = QL_FIWARE_SERVICEPATH
    return h


def _get(
    path: str,
    params: Optional[dict] = None,
    fiware_service: str | None = None,
) -> dict:
    """GET contra QL. Devuelve JSON o lanza RuntimeError con detalle."""
    if not REQUESTS_AVAILABLE:
        raise RuntimeError("'requests' no instalado. Ejecuta: pip install requests")

    url = f"{_QL_BASE}{path}"
    clean_params = {k: v for k, v in (params or {}).items() if v is not None}

    try:
        resp = requests.get(
            url,
            params=clean_params,
            headers=_headers(fiware_service),
            timeout=QL_TIMEOUT,
        )
    except requests.ConnectionError as exc:
        raise ConnectionError(f"No se puede conectar a Quantum Leap en {_QL_BASE}: {exc}")
    except requests.Timeout:
        raise TimeoutError(f"Timeout ({QL_TIMEOUT}s) esperando respuesta de Quantum Leap.")

    if resp.status_code == 404:
        return {"_ql_not_found": True, "status_code": 404, "url": url}

    if resp.status_code == 204:
        return {"_ql_no_content": True, "status_code": 204}

    if not resp.ok:
        detail = ""
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:300]
        raise RuntimeError(
            f"Quantum Leap HTTP {resp.status_code} en {path}: {detail}"
        )

    try:
        return resp.json()
    except ValueError:
        raise RuntimeError(f"Quantum Leap devolvió respuesta no-JSON: {resp.text[:300]}")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_offset(days: int = 0, hours: int = 0) -> str:
    delta = timedelta(days=days, hours=hours)
    dt = datetime.now(timezone.utc) - delta
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_relative_date(date_str: Optional[str]) -> Optional[str]:
    if not date_str:
        return None
    mapping = {
        "last_hour":   _iso_offset(hours=1),
        "last_day":    _iso_offset(days=1),
        "last_24h":    _iso_offset(hours=24),
        "last_week":   _iso_offset(days=7),
        "last_month":  _iso_offset(days=30),
        "last_3days":  _iso_offset(days=3),
        "last_year":   _iso_offset(days=365),
    }
    return mapping.get(date_str.lower(), date_str)


def _zip_index_values(index: list, values: list) -> list:
    return [
        {"timestamp": ts, "value": v}
        for ts, v in zip(index, values)
    ]


def _format_entity_response(data: dict, from_date: Optional[str] = None) -> dict:
    if "_ql_not_found" in data:
        msg = "Entidad o atributo no encontrado en Quantum Leap"
        if from_date:
            msg = (
                f"No hay datos en el rango solicitado (desde {from_date}). "
                f"Prueba con un rango más amplio (last_week / last_month) "
                f"o usa last_n=1 para ver el último valor registrado."
            )
        return {"found": False, "detail": msg}

    if "attrName" in data and "values" in data:
        index  = data.get("index", [])
        values = data.get("values", [])
        return {
            "entity_id":   data.get("entityId"),
            "entity_type": data.get("entityType"),
            "attr_name":   data["attrName"],
            "data_points": len(values),
            "series":      _zip_index_values(index, values),
        }

    if "attributes" in data:
        attrs_out = {}
        index = data.get("index", [])
        for attr in data.get("attributes", []):
            name   = attr.get("attrName", "unknown")
            values = attr.get("values", [])
            attrs_out[name] = _zip_index_values(index, values)
        return {
            "entity_id":   data.get("entityId"),
            "entity_type": data.get("entityType"),
            "data_points": len(index),
            "attributes":  attrs_out,
        }

    return data


def _format_type_response(data: dict) -> dict:
    if "_ql_not_found" in data:
        return {"found": False, "detail": "Tipo no encontrado en Quantum Leap"}

    if "entities" in data:
        entities_out = []
        for ent in data.get("entities", []):
            index = ent.get("index", [])
            attrs_out = {}
            for attr in ent.get("attributes", []):
                name   = attr.get("attrName", "unknown")
                values = attr.get("values", [])
                attrs_out[name] = _zip_index_values(index, values)
            entities_out.append({
                "entity_id":   ent.get("entityId"),
                "data_points": len(index),
                "attributes":  attrs_out,
            })
        return {
            "entity_type":     data.get("entityType"),
            "entities_count": len(entities_out),
            "entities":        entities_out,
        }

    if "attrName" in data:
        index  = data.get("index", [])
        values = data.get("values", [])
        return {
            "entity_type": data.get("entityType"),
            "attr_name":   data["attrName"],
            "data_points": len(values),
            "series":      _zip_index_values(index, values),
        }

    return data


# ─── Helpers Orion (resolución interna desde fragmento natural) ──────────────

def _orion_headers(fiware_service: str | None = None) -> dict:
    """
    Cabeceras NGSI-LD para llamar a Orion. El tenant es el mismo valor que
    para QL (multi-tenant unificado), pero la cabecera se llama distinto.
    """
    h = {
        "Accept": "application/ld+json",
        "Link": (
            '<https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld>; '
            'rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'
        ),
    }
    tenant = _effective_service(fiware_service)
    if tenant:
        h["NGSILD-Tenant"] = tenant
    return h


def _strip_accents(s: str) -> str:
    """Elimina tildes/diacríticos: 'carrocería' → 'carroceria'."""
    return "".join(
        c for c in _unicodedata.normalize("NFKD", s)
        if not _unicodedata.combining(c)
    )

def _tokenize_fragment(fragment: str) -> list:
    """
    Normaliza un fragmento en tokens para matching contra ids.
    Lowercase, separa por espacios/guiones/underscores, elimina vacíos.
    """
    if not fragment:
        return []
    normalized = _strip_accents(fragment.lower()).replace("-", " ").replace("_", " ")
    return [t for t in normalized.split() if t]


def _orion_resolve_measurement_urns(
    asset_fragment: str,
    fiware_service: str | None,
) -> list:
    """
    Devuelve la lista de URNs (del VALUE TYPE configurado) cuyo id contiene
    TODOS los tokens del fragmento. 0 = sin match, 1 = preciso, >1 = ambiguo.
    """
    tokens = _tokenize_fragment(asset_fragment)
    if not tokens:
        return []
    try:
        resp = requests.get(
            f"{ORION_API_BASE}/entities",
            params={"type": SDM_VALUE_TYPE_URI, "limit": 1000},
            headers=_orion_headers(fiware_service),
            timeout=ORION_TIMEOUT,
        )
        if not resp.ok:
            _log(
                f"⚠️  Orion HTTP {resp.status_code} resolviendo URNs "
                f"(tenant={_effective_service(fiware_service) or '(sin tenant)'})"
            )
            return []
        entities = resp.json() if resp.text else []
    except Exception as exc:
        _log(f"⚠️  Error consultando Orion para resolución: {exc}")
        return []

    matches = []
    for e in entities:
        eid = e.get("id", "")
        eid_norm = _strip_accents((
            eid.lower()
               .replace("-", " ")
               .replace("_", " ")
               .replace(":", " ")
        ))
        if all(tok in eid_norm for tok in tokens):
            matches.append(eid)
    return matches


def _orion_get_measurement_meta(
    entity_id: str,
    fiware_service: str | None,
) -> dict:
    """
    Best-effort lookup de tipo corto, unidad y propiedad controlada
    de una entidad de medida en Orion.
    """
    try:
        resp = requests.get(
            f"{ORION_API_BASE}/entities/{entity_id}",
            params={"options": "keyValues"},
            headers=_orion_headers(fiware_service),
            timeout=ORION_TIMEOUT,
        )
        if not resp.ok:
            return {"entity_type": SDM_VALUE_TYPE_SHORT, "unit": None, "property": None}
        e = resp.json()

        # Tipo corto (Orion puede devolver la URI completa)
        etype = e.get("type", SDM_VALUE_TYPE_SHORT)
        if isinstance(etype, str) and "/" in etype:
            etype = etype.rsplit("/", 1)[-1]

        unit = e.get("unitText") or e.get("unitCode")

        # controlledProperty puede venir como short o como URI completa
        prop = e.get("controlledProperty")
        if prop is None:
            for k, v in e.items():
                if isinstance(k, str) and k.endswith("controlledProperty"):
                    prop = v
                    break

        return {"entity_type": etype, "unit": unit, "property": prop}
    except Exception:
        return {"entity_type": SDM_VALUE_TYPE_SHORT, "unit": None, "property": None}


def _build_summary(
    property_: Optional[str],
    unit: Optional[str],
    aggr_method: Optional[str],
    aggr_period: Optional[str],
    from_date: Optional[str],
    last_n: Optional[int],
    series: list,
) -> str:
    """Resumen humano de una sola línea, listo para retransmitir."""
    if not series:
        return "Sin datos."

    prop_str = (property_ or "valor").replace("_", " ")
    unit_str = f" {unit}" if unit else ""

    # Valores agregados → recalculamos el agregado global por seguridad
    if aggr_method:
        try:
            values = [
                float(p["value"]) for p in series
                if p.get("value") is not None
            ]
            if not values:
                return "Sin datos numéricos en la ventana."

            method_map = {
                "avg":   ("media",   sum(values) / len(values)),
                "max":   ("máximo",  max(values)),
                "min":   ("mínimo",  min(values)),
                "sum":   ("suma",    sum(values)),
                "count": ("conteo",  float(len(values))),
            }
            label, agg = method_map.get(aggr_method, (aggr_method, values[-1]))
            window = from_date or (f"últimos {last_n} puntos" if last_n else "ventana")
            return (
                f"{prop_str.capitalize()} — {label} ({window}): "
                f"{round(agg, 2)}{unit_str} ({len(values)} puntos)."
            )
        except Exception:
            pass

    # Serie cruda
    try:
        last       = series[-1]
        last_value = last.get("value")
        last_ts    = last.get("timestamp")
        return (
            f"{prop_str.capitalize()}: {len(series)} muestras. "
            f"Última: {last_value}{unit_str} ({last_ts})."
        )
    except Exception:
        return f"{len(series)} muestras devueltas."


# ═══════════════════════════════════════════════════════════════════════
# TOOLS MCP
# ═══════════════════════════════════════════════════════════════════════

@mcp.tool(
    name="get_historical_aggregate",
    description=(
        "TOOL PRINCIPAL para histórico, agregaciones y tendencias industriales. "
        "Dos modos de uso:\n\n"
        "MODO A — URN YA CONOCIDA (preferido, 100%% determinista):\n"
        "  Proporciona `entity_id` con la URN canónica exacta del DeviceMeasurement "
        "(ej: 'urn:ngsi-ld:DeviceMeasurement:agv-carroceria-001-bateria-meas'). "
        "Salta la resolución interna y va directo a QuantumLeap.\n\n"
        "MODO B — RESOLUCIÓN INTERNA POR FRAGMENTO:\n"
        "  Proporciona `asset_fragment` con palabras clave del activo + propiedad. "
        "El sistema resolverá la URN consultando Orion-LD internamente.\n\n"
        "Parámetros:\n"
        "- entity_id (str, opcional): URN canónica exacta del DeviceMeasurement. "
        "  Si se proporciona, `asset_fragment` se ignora.\n"
        "- asset_fragment (str): palabras clave cuando no se tiene la URN.\n"
        "- aggr_method: 'avg' (default), 'max', 'min', 'sum', 'count', o None.\n"
        "- from_date: 'last_hour' (default), 'last_day', 'last_24h', 'last_3days', "
        "  'last_week', 'last_month', 'last_year', o ISO8601.\n"
        "- aggr_period: 'minute', 'hour' (default), 'day', 'month', 'year'.\n"
        "- last_n: últimos N puntos crudos (excluye from_date+aggr_method)."
        + _TENANT_PARAM_DOC
    ),
)
def get_historical_aggregate(
    asset_fragment: str = "",
    entity_id: Optional[str] = None,       # ← NUEVO
    aggr_method: Optional[str] = "avg",
    from_date: Optional[str] = "last_hour",
    aggr_period: Optional[str] = "hour",
    last_n: Optional[int] = None,
    fiware_service: str | None = None,
) -> str:
    # Validación
    if not asset_fragment and not entity_id:
        return json.dumps({
            "found": False,
            "detail": "Proporciona entity_id (URN exacta) o asset_fragment (palabras clave).",
        }, ensure_ascii=False)

    if aggr_method is not None and aggr_method not in _VALID_AGGR_METHODS:
        return json.dumps({"found": False,
            "detail": f"aggr_method '{aggr_method}' no válido. Usa: {sorted(_VALID_AGGR_METHODS)}"
        }, ensure_ascii=False)

    if aggr_period is not None and aggr_period not in _VALID_AGGR_PERIODS:
        return json.dumps({"found": False,
            "detail": f"aggr_period '{aggr_period}' no válido. Usa: {sorted(_VALID_AGGR_PERIODS)}"
        }, ensure_ascii=False)

# ── Paso 1: resolver o usar URN directa ──────────────────────────────────
    if entity_id and entity_id.startswith("urn:ngsi-ld:"):
        parts = entity_id.split(":")
        entity_type_in_urn = parts[2] if len(parts) >= 4 else ""
        id_segment = parts[3] if len(parts) >= 4 else ""

        if entity_type_in_urn == SDM_VALUE_TYPE_SHORT:
            # Correcto: URN del VALUE TYPE, usarla directamente
            _log(f"entity_id directo (VALUE TYPE correcto): {entity_id}")
        else:
            # URN de otro tipo (activo físico, etc.) — resolver automáticamente
            _log(
                f"entity_id '{entity_id}' no es {SDM_VALUE_TYPE_SHORT} "
                f"(es {entity_type_in_urn}). Resolviendo automáticamente..."
            )
            # Combinar el segmento de id del activo con el asset_fragment
            # para afinar la resolución (ej: "agv carroceria 002" + "bateria")
            base_fragment = id_segment.replace("-", " ").replace("_", " ")
            combined = f"{base_fragment} {asset_fragment}".strip() if asset_fragment else base_fragment

            auto_matches = _orion_resolve_measurement_urns(combined, fiware_service)

            if not auto_matches and asset_fragment:
                # Segundo intento solo con el id del activo (sin la propiedad)
                auto_matches = _orion_resolve_measurement_urns(base_fragment, fiware_service)

            if not auto_matches:
                return json.dumps({
                    "found": False, "stage": "resolve",
                    "detail": (
                        f"Se recibió una URN de tipo '{entity_type_in_urn}' "
                        f"(se esperaba '{SDM_VALUE_TYPE_SHORT}'). "
                        f"Resolución automática con fragmento '{combined}' sin resultados. "
                        f"Proporciona la URN exacta del {SDM_VALUE_TYPE_SHORT} "
                        f"o un asset_fragment más preciso."
                    ),
                }, ensure_ascii=False)

            if len(auto_matches) > 1:
                # (auto-resolución y MODO B)
                match_labels = [m.split(":")[-1].replace("-meas", "") for m in auto_matches[:10]]

                return json.dumps({
                    "found": False, "stage": "resolve", "ambiguous": True,
                    "matches": auto_matches[:10],
                    "match_labels": match_labels,
                    "total_matches": len(auto_matches),
                    "detail": (
                        f"Se recibió una URN de tipo '{entity_type_in_urn}'. "
                        f"Resolución automática encontró {len(auto_matches)} medidas. "
                        f"Añade más keywords al asset_fragment para acotar a una sola."
                    ),
                }, ensure_ascii=False)

            entity_id = auto_matches[0]
            _log(f"Auto-resolución exitosa: {entity_id}")
    else:
        # MODO B: resolución por fragmento de texto
        if not asset_fragment:
            return json.dumps({
                "found": False,
                "detail": "Proporciona entity_id (URN del VALUE TYPE) o asset_fragment.",
            }, ensure_ascii=False)

        matches = _orion_resolve_measurement_urns(asset_fragment, fiware_service)
        if not matches:
            return json.dumps({
                "found": False, "stage": "resolve",
                "detail": (
                    f"No encontré ningún {SDM_VALUE_TYPE_SHORT} cuyo id contenga "
                    f"todas las palabras de '{asset_fragment}'."
                ),
            }, ensure_ascii=False)
        if len(matches) > 1:
            return json.dumps({
                "found": False, "stage": "resolve", "ambiguous": True,
                "matches": matches[:10], "total_matches": len(matches),
                "detail": f"Ambiguo: '{asset_fragment}' coincide con {len(matches)} medidas.",
            }, ensure_ascii=False)
        entity_id = matches[0]

    # Paso 2 — metadata (best-effort)
    meta = _orion_get_measurement_meta(entity_id, fiware_service)

    # Paso 3 — consulta a QL
    path = f"/v2/entities/{entity_id}/attrs/{SDM_VALUE_ATTR}"
    params = {
        "type":       meta.get("entity_type"),
        "fromDate":   _parse_relative_date(from_date) if (from_date and not last_n) else None,
        "lastN":      last_n,
        "aggrMethod": aggr_method,
        "aggrPeriod": aggr_period if aggr_method else None,
    }
    try:
        data = _get(path, params=params, fiware_service=fiware_service)
    except Exception as exc:
        return json.dumps({
            "found":     False,
            "stage":     "query",
            "entity_id": entity_id,
            "detail":    f"Error consultando QuantumLeap: {exc}",
        }, ensure_ascii=False)

    formatted = _format_entity_response(data, from_date=from_date)
    series    = formatted.get("series", [])

    if not series:
        return json.dumps({
            "found":     False,
            "stage":     "query",
            "entity_id": entity_id,
            "property":  meta.get("property"),
            "unit":      meta.get("unit"),
            "detail":    formatted.get("detail", "Sin datos en la ventana solicitada."),
        }, ensure_ascii=False)

    summary = _build_summary(
        property_=meta.get("property"),
        unit=meta.get("unit"),
        aggr_method=aggr_method,
        aggr_period=aggr_period,
        from_date=from_date,
        last_n=last_n,
        series=series,
    )

    return json.dumps({
        "found":       True,
        "entity_id":   entity_id,
        "entity_type": meta.get("entity_type"),
        "property":    meta.get("property"),
        "unit":        meta.get("unit"),
        "aggr_method": aggr_method,
        "aggr_period": aggr_period if aggr_method else None,
        "from_date":   from_date,
        "last_n":      last_n,
        "data_points": len(series),
        "series":      series,
        "summary":     summary,
        "tenant":      _effective_service(fiware_service) or "(sin tenant)",
    }, ensure_ascii=False, default=str)


# ─── TOOLS LOW-LEVEL (escape hatch) ──────────────────────────────────────────

@mcp.tool(
    name="ql_health",
    description="Verifica que Quantum Leap está operativo." + _TENANT_PARAM_DOC,
)
def ql_health(fiware_service: str | None = None) -> str:
    try:
        data = _get("/v2/entities", params={"limit": 1}, fiware_service=fiware_service)
        ok = "_ql_not_found" not in data
        return json.dumps({
            "status":   "ok" if ok else "degraded",
            "base_url": _QL_BASE,
            "tenant":   _effective_service(fiware_service) or "(sin tenant)",
            "note":     "Conectividad verificada vía /v2/entities",
        }, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({
            "status":   "error",
            "detail":   str(exc),
            "base_url": _QL_BASE,
            "tenant":   _effective_service(fiware_service) or "(sin tenant)",
        }, ensure_ascii=False)


@mcp.tool(
    name="ql_list_entity_types",
    description=(
        "ESCAPE HATCH — lista los tipos de entidad que tienen datos históricos en "
        "QL. Solo úsalo si el usuario pregunta literalmente 'qué hay en QL'. "
        "Para preguntas de histórico/agregado usa get_historical_aggregate."
        + _TENANT_PARAM_DOC
    ),
)
def ql_list_entity_types(fiware_service: str | None = None) -> str:
    try:
        data = _get("/v2/entities", params={"limit": 100}, fiware_service=fiware_service)

        if "_ql_not_found" in data or "_ql_no_content" in data:
            return json.dumps({
                "entity_types": [],
                "total":        0,
                "tenant":       _effective_service(fiware_service) or "(sin tenant)",
                "note": (
                    "No se encontraron entidades en QuantumLeap para este tenant. "
                    "Posible subscription Orion→QL no configurada o tenant incorrecto."
                ),
            }, ensure_ascii=False)

        entities = data if isinstance(data, list) else data.get("data", [])
        types = sorted({
            e.get("entityType") or e.get("type", "unknown")
            for e in entities
            if e.get("entityType") or e.get("type")
        })

        return json.dumps({
            "entity_types": types,
            "total":        len(types),
            "tenant":       _effective_service(fiware_service) or "(sin tenant)",
        }, ensure_ascii=False)

    except Exception as exc:
        return f"ERROR en ql_list_entity_types: {exc}"


@mcp.tool(
    name="ql_list_entities",
    description=(
        "ESCAPE HATCH — lista entidades en QL, opcionalmente filtradas por tipo. "
        "Solo útil para exploración. Para histórico/agregado usa "
        "get_historical_aggregate, no esto."
        + _TENANT_PARAM_DOC
    ),
)
def ql_list_entities(
    entity_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    fiware_service: str | None = None,
) -> str:
    try:
        if entity_type:
            path = f"/v2/types/{entity_type}"
            params = {"limit": limit, "offset": offset, "lastN": 1}
            data = _get(path, params=params, fiware_service=fiware_service)
            formatted = _format_type_response(data)
            entities = [
                {"entity_id": e["entity_id"], "entity_type": entity_type}
                for e in formatted.get("entities", [])
            ]
            return json.dumps({
                "entity_type": entity_type,
                "entities":    entities,
                "total":       len(entities),
                "tenant":      _effective_service(fiware_service) or "(sin tenant)",
            }, ensure_ascii=False)
        else:
            data = _get(
                "/v2/entities",
                params={"limit": limit, "offset": offset, "lastN": 1},
                fiware_service=fiware_service,
            )
            if "_ql_not_found" in data or "_ql_no_content" in data:
                return json.dumps({
                    "entities": [],
                    "total":    0,
                    "tenant":   _effective_service(fiware_service) or "(sin tenant)",
                    "note": (
                        "Sin entidades en QL para este tenant. Verifica subscription "
                        "Orion→QL y que el tenant es correcto."
                    ),
                }, ensure_ascii=False)

            entities = data if isinstance(data, list) else data.get("data", [])
            simplified = [
                {
                    "entity_id":   e.get("entityId",   e.get("id")),
                    "entity_type": e.get("entityType", e.get("type")),
                }
                for e in entities
            ]
            return json.dumps({
                "entities": simplified,
                "total":    len(simplified),
                "tenant":   _effective_service(fiware_service) or "(sin tenant)",
            }, ensure_ascii=False)

    except Exception as exc:
        return f"ERROR en ql_list_entities: {exc}"


@mcp.tool(
    name="ql_get_entity_history",
    description=(
        "ESCAPE HATCH — histórico completo de una entidad. Solo úsalo si ya tienes "
        "una URN canónica exacta y necesitas varios atributos. Para casos normales "
        "usa get_historical_aggregate.\n\n"
        "Parámetros:\n"
        "- entity_id: URN completo de la entidad\n"
        "- entity_type: tipo NGSI-LD (mejora rendimiento, opcional)\n"
        "- attrs: lista de atributos (None = todos)\n"
        "- from_date: ISO8601 o 'last_hour','last_day','last_week','last_month'\n"
        "- to_date: ISO8601 (None = ahora)\n"
        "- last_n: últimos N registros\n"
        "- limit / offset: paginación"
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_entity_history(
    entity_id: str,
    entity_type: Optional[str] = None,
    attrs: Optional[List[str]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    last_n: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    fiware_service: str | None = None,
) -> str:
    try:
        path = f"/v2/entities/{entity_id}"
        params = {
            "type":     entity_type,
            "attrs":    ",".join(attrs) if attrs else None,
            "fromDate": _parse_relative_date(from_date),
            "toDate":   _parse_relative_date(to_date),
            "lastN":    last_n,
            "limit":    limit,
            "offset":   offset,
        }
        data      = _get(path, params=params, fiware_service=fiware_service)
        formatted = _format_entity_response(data, from_date=from_date)
        return json.dumps(formatted, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"ERROR en ql_get_entity_history: {exc}"


@mcp.tool(
    name="ql_get_attribute_history",
    description=(
        "ESCAPE HATCH — histórico de UN atributo con URN exacta. Para casos "
        "normales (asset descrito en lenguaje natural) usa get_historical_aggregate.\n\n"
        "Parámetros:\n"
        "- entity_id: URN completo\n"
        "- attr_name: nombre del atributo (ej: 'numValue', 'temperature')\n"
        "- entity_type: tipo NGSI-LD (opcional)\n"
        "- from_date / to_date / last_n: ventana temporal\n"
        "- aggr_method: 'avg','max','min','sum','count' (None = raw)\n"
        "- aggr_period: 'minute','hour','day','month','year'"
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_attribute_history(
    entity_id: str,
    attr_name: str,
    entity_type: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    last_n: Optional[int] = None,
    aggr_method: Optional[str] = None,
    aggr_period: Optional[str] = None,
    fiware_service: str | None = None,
) -> str:
    try:
        if aggr_method and aggr_method not in _VALID_AGGR_METHODS:
            return (
                f"ERROR: aggr_method '{aggr_method}' no válido. "
                f"Usa uno de: {sorted(_VALID_AGGR_METHODS)}"
            )
        if aggr_period and aggr_period not in _VALID_AGGR_PERIODS:
            return (
                f"ERROR: aggr_period '{aggr_period}' no válido. "
                f"Usa uno de: {sorted(_VALID_AGGR_PERIODS)}"
            )

        path = f"/v2/entities/{entity_id}/attrs/{attr_name}"
        params = {
            "type":       entity_type,
            "fromDate":   _parse_relative_date(from_date),
            "toDate":     _parse_relative_date(to_date),
            "lastN":      last_n,
            "aggrMethod": aggr_method,
            "aggrPeriod": aggr_period,
        }
        data      = _get(path, params=params, fiware_service=fiware_service)
        formatted = _format_entity_response(data, from_date=from_date)
        return json.dumps(formatted, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"ERROR en ql_get_attribute_history: {exc}"


@mcp.tool(
    name="ql_get_type_history",
    description=(
        "ESCAPE HATCH — histórico de todas las entidades de un tipo. Útil para "
        "comparar varios sensores del mismo tipo.\n\n"
        "Parámetros:\n"
        "- entity_type: tipo NGSI-LD\n"
        "- attrs: atributos (None = todos)\n"
        "- from_date / to_date / last_n: ventana temporal\n"
        "- limit / offset: paginación"
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_type_history(
    entity_type: str,
    attrs: Optional[List[str]] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    last_n: Optional[int] = None,
    limit: int = 10,
    offset: int = 0,
    fiware_service: str | None = None,
) -> str:
    try:
        path = f"/v2/types/{entity_type}"
        params = {
            "attrs":    ",".join(attrs) if attrs else None,
            "fromDate": _parse_relative_date(from_date),
            "toDate":   _parse_relative_date(to_date),
            "lastN":    last_n,
            "limit":    limit,
            "offset":   offset,
        }
        data      = _get(path, params=params, fiware_service=fiware_service)
        formatted = _format_type_response(data)
        return json.dumps(formatted, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"ERROR en ql_get_type_history: {exc}"


@mcp.tool(
    name="ql_get_type_attribute_stats",
    description=(
        "ESCAPE HATCH — estadísticas agregadas de un atributo para todas las "
        "entidades de un tipo durante un período.\n\n"
        "Parámetros:\n"
        "- entity_type: tipo NGSI-LD\n"
        "- attr_name: atributo a agregar (ej: 'numValue')\n"
        "- aggr_method: 'avg','max','min','sum','count'\n"
        "- aggr_period: 'minute','hour','day','month','year'\n"
        "- from_date / to_date / last_n: ventana temporal"
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_type_attribute_stats(
    entity_type: str,
    attr_name: str,
    aggr_method: str = "avg",
    aggr_period: str = "hour",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    last_n: Optional[int] = None,
    fiware_service: str | None = None,
) -> str:
    try:
        if aggr_method not in _VALID_AGGR_METHODS:
            return (
                f"ERROR: aggr_method '{aggr_method}' no válido. "
                f"Opciones: {sorted(_VALID_AGGR_METHODS)}"
            )
        if aggr_period not in _VALID_AGGR_PERIODS:
            return (
                f"ERROR: aggr_period '{aggr_period}' no válido. "
                f"Opciones: {sorted(_VALID_AGGR_PERIODS)}"
            )

        path = f"/v2/types/{entity_type}/attrs/{attr_name}"
        params = {
            "fromDate":   _parse_relative_date(from_date),
            "toDate":     _parse_relative_date(to_date),
            "lastN":      last_n,
            "aggrMethod": aggr_method,
            "aggrPeriod": aggr_period,
        }
        data      = _get(path, params=params, fiware_service=fiware_service)
        formatted = _format_type_response(data)
        return json.dumps(formatted, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"ERROR en ql_get_type_attribute_stats: {exc}"


@mcp.tool(
    name="ql_get_last_value",
    description=(
        "ESCAPE HATCH — último valor registrado en QL para una URN concreta. "
        "Para 'valor actual' usa el especialista de Orion-LD (vive en Orion). "
        "Solo útil si necesitas explícitamente la última muestra de la SERIE."
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_last_value(
    entity_id: str,
    attr_name: str,
    entity_type: Optional[str] = None,
    fiware_service: str | None = None,
) -> str:
    try:
        path = f"/v2/entities/{entity_id}/attrs/{attr_name}"
        params = {"type": entity_type, "lastN": 1}
        data      = _get(path, params=params, fiware_service=fiware_service)
        formatted = _format_entity_response(data)

        series = formatted.get("series", [])
        last   = series[-1] if series else None

        return json.dumps({
            "entity_id":   formatted.get("entity_id", entity_id),
            "entity_type": formatted.get("entity_type"),
            "attr_name":   attr_name,
            "last_value":  last,
            "found":       last is not None,
            "tenant":      _effective_service(fiware_service) or "(sin tenant)",
        }, ensure_ascii=False, default=str)
    except Exception as exc:
        return f"ERROR en ql_get_last_value: {exc}"


@mcp.tool(
    name="ql_get_multiple_entities_last_value",
    description=(
        "ESCAPE HATCH — último valor de un atributo para múltiples URNs. Útil "
        "para comparar varias entidades a la vez con las URNs ya resueltas."
        + _TENANT_PARAM_DOC
    ),
)
def ql_get_multiple_entities_last_value(
    entity_ids: List[str],
    attr_name: str,
    entity_type: Optional[str] = None,
    fiware_service: str | None = None,
) -> str:
    results = []
    errors  = []

    for eid in entity_ids:
        try:
            path   = f"/v2/entities/{eid}/attrs/{attr_name}"
            params = {"type": entity_type, "lastN": 1}
            data   = _get(path, params=params, fiware_service=fiware_service)
            fmt    = _format_entity_response(data)

            series = fmt.get("series", [])
            last   = series[-1] if series else None

            results.append({
                "entity_id":   eid,
                "entity_type": fmt.get("entity_type", entity_type),
                "attr_name":   attr_name,
                "last_value":  last,
                "found":       last is not None,
            })
        except Exception as exc:
            errors.append({"entity_id": eid, "error": str(exc)})

    return json.dumps({
        "attr_name": attr_name,
        "results":   results,
        "errors":    errors,
        "total_ok":  sum(1 for r in results if r["found"]),
        "total_err": len(errors),
        "tenant":    _effective_service(fiware_service) or "(sin tenant)",
    }, ensure_ascii=False, default=str)


# ─── ENTRYPOINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    _log("🚀 Iniciando servidor MCP Quantum Leap v2.1 (multi-tenant + get_historical_aggregate)...")
    _log(f"   Base URL QL    : {_QL_BASE}")
    _log(f"   Base URL Orion : {ORION_API_BASE}")
    _log(f"   Tenant default : {QL_FIWARE_SERVICE or '(sin tenant)'}")
    _log(f"   ServicePath    : {QL_FIWARE_SERVICEPATH}")
    _log(f"   VALUE TYPE     : {SDM_VALUE_TYPE_SHORT} ({SDM_VALUE_TYPE_URI})")
    _log(f"   VALUE attr     : {SDM_VALUE_ATTR}")
    _log(f"   Multi-tenant   : activado (fiware_service por petición)")

    if not REQUESTS_AVAILABLE:
        _log("❌ 'requests' no instalado. Ejecuta: pip install requests")
        sys.exit(1)

    try:
        r = requests.get(f"{_QL_BASE}/v2/entities", headers=_headers(),
                         params={"limit": 1}, timeout=5)
        if r.ok or r.status_code == 404:
            _log("Quantum Leap OK — conectividad verificada")
        else:
            _log(f"Quantum Leap respondió HTTP {r.status_code}")
    except Exception as exc:
        _log(f"Advertencia de conectividad QL (continuando): {exc}")

    try:
        r = requests.get(f"{ORION_API_BASE}/types", timeout=5)
        if r.ok or r.status_code == 404:
            _log("Orion-LD OK — conectividad verificada (para resolución interna)")
        else:
            _log(f"Orion-LD respondió HTTP {r.status_code} (la resolución podría fallar)")
    except Exception as exc:
        _log(f"⚠️  Sin conectividad a Orion: {exc}. get_historical_aggregate NO funcionará.")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server_type", type=str, default="stdio", choices=["sse", "stdio"]
    )
    parser.add_argument("--port", type=int, default=8002, help="Puerto para modo SSE")
    args = parser.parse_args()

    if args.server_type == "stdio":
        try:
            mcp.run(transport="stdio")
        except Exception as exc:
            _log(f"❌ Error fatal MCP STDIO: {exc}")
            sys.exit(1)
    else:
        _log(f"📡 Arrancando modo SSE en puerto {args.port}...")
        try:
            import uvicorn
            original_init = uvicorn.Config.__init__
            def _patched_init(self, *a, **kw):
                kw["port"] = args.port
                kw["host"] = "0.0.0.0"
                original_init(self, *a, **kw)
            uvicorn.Config.__init__ = _patched_init
            mcp.run(transport="sse")
        except ImportError:
            _log("❌ Instala uvicorn para modo SSE.")
            sys.exit(1)