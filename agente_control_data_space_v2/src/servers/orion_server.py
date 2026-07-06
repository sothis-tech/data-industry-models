# servers/orion_server.py
# -*- coding: utf-8 -*-
"""
Servidor MCP para Orion-LD (NGSI-LD Context Broker) — Solo Lectura
====================================================================
Expone únicamente herramientas de lectura y exploración.
Las operaciones de escritura están reservadas al agente Sparkplug.

Incluye descubrimiento semántico dinámico (describe_entity_schema) que combina
datos reales del broker con esquemas Smart Data Models externos.

Soporte multi-tenant
---------------------
Cada tool acepta un parámetro `ngsild_tenant: str | None = None`.
  - Si se proporciona → usa ese tenant para esa llamada concreta.
  - Si no → usa NGSI_TENANT del entorno (config.yaml).
Esto permite al mismo proceso atender peticiones de distintos tenants
sin reiniciarse.

Versión: 2.4.0-readonly
"""

import re
import sys
import os
from pathlib import Path
import json
import argparse
import urllib.request
import urllib.error
import urllib.parse
from typing import Optional

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print("[OrionLD] ERROR: 'mcp' no instalado.", file=sys.stderr)
    sys.exit(1)


# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(msg: str):
    print(f"[OrionLD] {msg}", file=sys.stderr)


# ─── Configuración ────────────────────────────────────────────────────────────

ORION_URL             = os.getenv("ORION_URL", "http://localhost:1026").rstrip("/")
NGSI_BASE             = f"{ORION_URL}/ngsi-ld/v1"
DEFAULT_CONTEXT       = "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
CUSTOM_CONTEXT_URL    = os.getenv("NGSI_CONTEXT_URL",  "")
CUSTOM_CONTEXT_PATH   = os.getenv("NGSI_CONTEXT_PATH", "")
NGSI_TENANT           = os.getenv("NGSI_TENANT", "")
HTTP_TIMEOUT          = int(os.getenv("ORION_TIMEOUT",   "15"))
EXTERNAL_HTTP_TIMEOUT = int(os.getenv("EXTERNAL_TIMEOUT", "10"))

mcp = FastMCP("orion-ld-server")


# ─── Tenant dinámico ──────────────────────────────────────────────────────────

def _effective_tenant(override: str | None = None) -> str:
    """
    Resuelve el tenant efectivo para una llamada concreta.
    Prioridad: override (parámetro del tool) > NGSI_TENANT (config/env).
    Un override de cadena vacía se trata como "sin tenant" explícito.
    """
    if override is not None:
        return override
    return NGSI_TENANT


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def _http(
    method:          str,
    path:            str,
    body:            Optional[dict] = None,
    params:          Optional[dict] = None,
    content_type:    str            = "application/ld+json",
    tenant_override: str | None     = None,
) -> tuple[int, str]:
    url = f"{NGSI_BASE}{path}"
    if params:
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""}
        )
        if qs:
            url = f"{url}?{qs}"
    data    = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/ld+json"}
    if data is not None:
        headers["Content-Type"] = content_type
    if method.upper() == "GET" and (CUSTOM_CONTEXT_URL or CUSTOM_CONTEXT_PATH):
        ctx_url = CUSTOM_CONTEXT_URL if CUSTOM_CONTEXT_URL else DEFAULT_CONTEXT
        headers["Link"] = (
            f'<{ctx_url}>; rel="http://www.w3.org/ns/json-ld#context"; '
            f'type="application/ld+json"'
        )
    tenant = _effective_tenant(tenant_override)
    if tenant:
        headers["NGSILD-Tenant"] = tenant
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8") if e.fp else "")
    except urllib.error.URLError as e:
        return 0, f"Connection error: {e.reason}"
    except Exception as e:
        return 0, f"Unexpected error: {e}"


def _http_raw(
    path:            str,
    params:          Optional[dict] = None,
    tenant_override: str | None     = None,
) -> tuple[int, str]:
    """GET sin Link header. Para discovery interno sin resolución de contexto."""
    url = f"{NGSI_BASE}{path}"
    if params:
        qs = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None and v != ""}
        )
        if qs:
            url = f"{url}?{qs}"
    raw_headers = {"Accept": "application/ld+json"}
    tenant = _effective_tenant(tenant_override)
    if tenant:
        raw_headers["NGSILD-Tenant"] = tenant
    req = urllib.request.Request(url, headers=raw_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8") if e.fp else "")
    except urllib.error.URLError as e:
        return 0, f"Connection error: {e.reason}"
    except Exception as e:
        return 0, f"Unexpected error: {e}"


# ─── Contexto JSON-LD ─────────────────────────────────────────────────────────

_CUSTOM_CTX_CACHE = None


def _load_custom_context() -> Optional[dict]:
    if not CUSTOM_CONTEXT_PATH:
        return None
    try:
        path = Path(CUSTOM_CONTEXT_PATH)
        if not path.is_absolute():
            path = Path.cwd() / path
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
                return data.get("@context", data)
        else:
            _log(f"⚠️  NGSI_CONTEXT_PATH no encontrado: {path}")
    except Exception as e:
        _log(f"⚠️  Error cargando contexto: {e}")
    return None


def _build_context():
    global _CUSTOM_CTX_CACHE
    if CUSTOM_CONTEXT_PATH and _CUSTOM_CTX_CACHE is None:
        loaded = _load_custom_context()
        if loaded is not None:
            _CUSTOM_CTX_CACHE = loaded
            _log(f"✅ Contexto cargado desde archivo: {CUSTOM_CONTEXT_PATH}")
    if _CUSTOM_CTX_CACHE is not None:
        return _CUSTOM_CTX_CACHE
    ctx = [DEFAULT_CONTEXT]
    if CUSTOM_CONTEXT_URL and CUSTOM_CONTEXT_URL != DEFAULT_CONTEXT:
        ctx.append(CUSTOM_CONTEXT_URL)
    return ctx if len(ctx) > 1 else ctx[0]


# ─── Type URI resolver ────────────────────────────────────────────────────────

_TYPE_URI_CACHE:  dict = {}
_SCHEMA_CACHE:    dict = {}   # type_short → {attrs, sample_ids, rel_targets}
_SCHEMA_SUMMARY:  dict = {}   # tenant_key → texto del resumen


def _build_type_cache(tenant_override: str | None = None) -> None:
    """Construye el cache de tipos consultando Orion. Acepta tenant override."""
    global _TYPE_URI_CACHE
    for params in [{"local": "true"}, {}]:
        status, body = _http_raw("/types", params=params, tenant_override=tenant_override)
        if status == 200:
            try:
                data      = json.loads(body)
                type_list = data.get("typeList", []) if isinstance(data, dict) else data
                if isinstance(type_list, list) and type_list:
                    for uri in type_list:
                        if isinstance(uri, str):
                            short = uri.split("/")[-1]
                            _TYPE_URI_CACHE[short] = uri
                            _TYPE_URI_CACHE[uri]   = uri
                    _log(
                        f"✅ Type URI cache ({len(_TYPE_URI_CACHE)//2} tipos): "
                        f"{[k for k in _TYPE_URI_CACHE if not k.startswith('http')]}"
                    )
                    return
            except Exception as e:
                _log(f"⚠️  Error construyendo type cache: {e}")
    _log("⚠️  Type URI cache vacío")


def _resolve_type_uri(name: str, tenant_override: str | None = None) -> str:
    if not name:
        return name
    if name.startswith("http"):
        return name
    if not _TYPE_URI_CACHE:
        _build_type_cache(tenant_override=tenant_override)
    resolved = _TYPE_URI_CACHE.get(name, name)
    if resolved != name:
        _log(f"🔗 Tipo resuelto: '{name}' → '{resolved}'")
    return resolved


# ─── Formato de respuesta ─────────────────────────────────────────────────────

def _fmt(status: int, body: str, operation: str = "") -> str:
    prefix = f"[{operation}] " if operation else ""
    if status in (200, 201, 204):
        if not body or body.strip() == "":
            return f"{prefix}✅ Operación exitosa (HTTP {status})"
        try:
            parsed = json.loads(body)
            return (
                f"{prefix}✅ HTTP {status}\n"
                f"```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```"
            )
        except Exception:
            return f"{prefix}✅ HTTP {status}: {body}"
    else:
        try:
            err     = json.loads(body)
            detail  = err.get("detail", err.get("description", body))
            err_type = err.get("type", err.get("title", ""))
            return f"{prefix}❌ HTTP {status} - {err_type}: {detail}"
        except Exception:
            return f"{prefix}❌ HTTP {status}: {body}"


# ─── Schema Discovery ─────────────────────────────────────────────────────────

# Tabla de ayuda interna: mapea nombres de tipo → dominio SDM para construir
# URLs de esquemas en smartdatamodels.org.
# No representa lo que hay en Orion — eso lo reporta _startup_health_check().
_SDM_DOMAIN_MAP = {
    "ManufacturingMachine":          "dataModel.ManufacturingIndustry",
    "ManufacturingMachineOperation": "dataModel.ManufacturingIndustry",
    "ManufacturingMachineModel":     "dataModel.ManufacturingIndustry",
    "Device":                        "dataModel.Device",
    "DeviceMeasurement":             "dataModel.Device",
    "DeviceModel":                   "dataModel.Device",
    "Building":                      "dataModel.Building",
    "BuildingSpace":                 "dataModel.Building",
    "Person":                        "dataModel.User",
    "AirQualityObserved":            "dataModel.Environment",
    "WaterQualityObserved":          "dataModel.Environment",
    "NoiseLevelObserved":            "dataModel.Environment",
    "WeatherObserved":               "dataModel.Weather",
    "WeatherForecast":               "dataModel.Weather",
    "TrafficFlowObserved":           "dataModel.Transportation",
    "Vehicle":                       "dataModel.Transportation",
    "VehicleModel":                  "dataModel.Transportation",
    "EnergyConsumptionMonitoring":   "dataModel.Energy",
    "GreenEnergyMeasurement":        "dataModel.Energy",
    "AgriParcel":                    "dataModel.Agrifood",
    "AgriCrop":                      "dataModel.Agrifood",
    "AgriSoil":                      "dataModel.Agrifood",
}

_SDM_SCHEMA_CACHE: dict = {}


def _fetch_url_safe(url: str, timeout: int = None) -> Optional[dict]:
    t = timeout or EXTERNAL_HTTP_TIMEOUT
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/json, */*",
                "User-Agent": "ChatMCP-Industrial/2.4",
            },
        )
        with urllib.request.urlopen(req, timeout=t) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log(f"⚠️  No se pudo descargar {url}: {e}")
        return None


def _build_sdm_candidates(entity_type: str, domain: Optional[str] = None) -> list:
    resolved   = domain or _SDM_DOMAIN_MAP.get(entity_type)
    candidates = []
    if resolved:
        candidates.append(
            f"https://smart-data-models.github.io/{resolved}/{entity_type}/schema.json"
        )
    for suffix in ("Observed", "Monitoring", "Measurement", "Model", "Flow"):
        base = entity_type.replace(suffix, "")
        if base != entity_type:
            candidates.append(
                f"https://smart-data-models.github.io/dataModel.{base}/{entity_type}/schema.json"
            )
    candidates.append(
        f"https://smart-data-models.github.io/dataModel.{entity_type}/{entity_type}/schema.json"
    )
    seen, unique = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def _extract_schema_summary(schema: dict) -> dict:
    _SKIP = {
        "id", "type", "@context", "location", "address", "alternateName",
        "areaServed", "dataProvider", "dateCreated", "dateModified",
        "description", "name", "owner", "seeAlso", "source",
    }
    summary = {
        "description": schema.get("description", schema.get("title", "")),
        "properties":  {},
    }
    for attr, defn in schema.get("properties", {}).items():
        if attr in _SKIP:
            continue
        info = {}
        desc = defn.get("description", "")
        if desc:
            info["description"] = desc[:220] + ("…" if len(desc) > 220 else "")
        dtype = defn.get("type")
        if not dtype and "anyOf" in defn:
            types = [x.get("type") for x in defn["anyOf"]
                     if x.get("type") and x.get("type") != "null"]
            dtype = " | ".join(types) if types else None
        if dtype:
            info["data_type"] = dtype
        ngsi_meta = defn.get("x-ngsi", {})
        units = (
            defn.get("units")
            or ngsi_meta.get("units")
            or ngsi_meta.get("unitCode")
            or defn.get("model")
        )
        if units:
            info["units"] = units
        ngsi_type = ngsi_meta.get("type")
        if ngsi_type:
            info["ngsi_type"] = ngsi_type
        enum_vals = defn.get("enum")
        if enum_vals and isinstance(enum_vals, list):
            info["enum"] = [str(v) for v in enum_vals[:10]]
        example = defn.get("example") or ngsi_meta.get("example")
        if example is not None:
            info["example"] = example
        if info:
            summary["properties"][attr] = info
    return summary


def _resolve_context_mapping() -> dict:
    ctx     = _build_context()
    mapping = {}
    if isinstance(ctx, str):
        data = _fetch_url_safe(ctx)
        if data:
            raw = data.get("@context", {})
            if isinstance(raw, dict):
                mapping = {k: v for k, v in raw.items()
                           if isinstance(v, str) and k != "@vocab"}
    elif isinstance(ctx, dict):
        mapping = {k: v for k, v in ctx.items()
                   if isinstance(v, str) and k != "@vocab"}
    elif isinstance(ctx, list):
        for item in ctx:
            if isinstance(item, dict):
                mapping.update(
                    {k: v for k, v in item.items()
                     if isinstance(v, str) and k != "@vocab"}
                )
    return mapping


# ══════════════════════════════════════════════════════════════════════════════
# HERRAMIENTAS MCP — solo lectura
# Todas aceptan ngsild_tenant: str | None = None para soporte multi-tenant.
# Si se omite, se usa el tenant configurado en el entorno (NGSI_TENANT).
# ══════════════════════════════════════════════════════════════════════════════

_TENANT_PARAM_DOC = (
    "\n- ngsild_tenant: (opcional) tenant NGSI-LD. Si se omite, usa el configurado por defecto."
)


# ─── 0. Schema summary (CALL FIRST — zero-cost, cached) ──────────────────────

@mcp.tool(
    name="get_schema_summary",
    description=(
        "Returns the complete pre-built data model schema: all entity types, "
        "their attributes, relationship targets, and controlledProperty values. "
        "CALL THIS FIRST at the start of any conversation to understand the data "
        "space without additional API calls. Zero latency — served from memory. "
        "Replaces explore_data_model() + describe_entity_schema() for initial discovery."
    ),
)
def get_schema_summary(
    ngsild_tenant: str | None = None,
) -> str:
    """
    Returns the cached schema summary. If the cache is empty (e.g. Orion was
    empty at startup), triggers a fresh build and returns the result.
    """
    global _SCHEMA_SUMMARY, _SCHEMA_CACHE
    tenant_key = ngsild_tenant or NGSI_TENANT or "__default__"

    # Lazy loading: build schema on first access for this tenant
    if tenant_key not in _SCHEMA_SUMMARY:
        _log(f"Schema cache miss para tenant '{tenant_key}' — construyendo...")
        _build_schema_cache(tenant_override=ngsild_tenant)

    summary = _SCHEMA_SUMMARY.get(tenant_key, "")
    if not summary:
        return (
            f"Sin datos para tenant '{tenant_key}'. "
            "El broker está vacío o el tenant no existe. "
            "Usa explore_data_model() para verificar el estado del broker."
        )
    return summary

@mcp.tool(
    name="get_entity_counts",
    description=(
        "Devuelve conteos EXACTOS de entidades del data space, leídos del schema "
        "precargado (cero latencia, sin enumerar). Úsalo para CUALQUIER pregunta "
        "de conteo: 'cuántas entidades en total', 'cuántas de cada tipo', "
        "'cuántos tipos hay', 'cuántas unidades por tipo'. Devuelve JSON: "
        "{types:{<Tipo>:<n>,...}, total:<suma de entidades>, type_count:<nº de "
        "tipos>}. NOTA: 'total' es el número de ENTIDADES (no de tipos); "
        "'type_count' es el número de TIPOS. No los confundas."
        + _TENANT_PARAM_DOC
    ),
)
def get_entity_counts(
    ngsild_tenant: str | None = None,
) -> str:
    """
    Conteo determinista por tipo + total, servido desde _SCHEMA_CACHE.
    Si el cache aún no existe para este tenant, lo construye (lazy).
    """
    global _SCHEMA_CACHE
    tenant_key = ngsild_tenant or NGSI_TENANT or "__default__"
 
    if tenant_key not in _SCHEMA_CACHE:
        _log(f"get_entity_counts: schema cache miss para '{tenant_key}' — construyendo...")
        _build_schema_cache(tenant_override=ngsild_tenant)
 
    cache = _SCHEMA_CACHE.get(tenant_key, {})
    if not cache:
        return json.dumps(
            {"types": {}, "total": 0, "type_count": 0,
             "hint": "Broker vacío o tenant inexistente."},
            ensure_ascii=False,
        )
 
    types = {short: int(info.get("count", 0)) for short, info in cache.items()}
    total = sum(types.values())
    return json.dumps(
        {"types": types, "total": total, "type_count": len(types)},
        ensure_ascii=False,
    )

# ─── 1. Estado del broker ─────────────────────────────────────────────────────

@mcp.tool(
    name="broker_version",
    description="Consulta la versión y estado del broker Orion-LD.",
)
def broker_version() -> str:
    try:
        req = urllib.request.Request(f"{ORION_URL}/version", method="GET")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
            return (
                f"✅ Broker disponible:\n"
                f"```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```"
            )
    except Exception as e:
        return f"❌ Broker no disponible en {ORION_URL}: {e}"


# ─── 2. Contextos ─────────────────────────────────────────────────────────────

@mcp.tool(
    name="list_contexts",
    description="Lista todos los contextos JSON-LD registrados en el broker." + _TENANT_PARAM_DOC,
)
def list_contexts(
    ngsild_tenant: str | None = None,
) -> str:
    status, body = _http("GET", "/jsonldContexts", tenant_override=ngsild_tenant)
    return _fmt(status, body, "list_contexts")


# ─── 3. Exploración y tipos ───────────────────────────────────────────────────

@mcp.tool(
    name="explore_data_model",
    description=(
        "Exploración completa del broker: tipos de entidades, conteos y ejemplos. "
        "PRIMERA herramienta a usar para entender qué datos hay disponibles."
        + _TENANT_PARAM_DOC
    ),
)
def explore_data_model(
    ngsild_tenant: str | None = None,
) -> str:
    lines = ["## 📊 Exploración del broker Orion-LD\n"]

    def _short(uri: str) -> str:
        return uri.split("/")[-1] if uri.startswith("http") else uri

    try:
        req = urllib.request.Request(f"{ORION_URL}/version", method="GET")
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            ver_data = json.loads(resp.read().decode())
            version  = ver_data.get("orionld version", ver_data.get("version", "?"))
            lines.append(f"**Broker:** Orion-LD {version} en `{ORION_URL}`\n")
    except Exception as e:
        lines.append(f"**Broker:** `{ORION_URL}` (versión no disponible: {e})\n")

    if ngsild_tenant or _effective_tenant():
        lines.append(
            f"**Tenant activo:** `{_effective_tenant(ngsild_tenant) or 'default'}`\n"
        )

    type_list = []
    for params_try in [{"local": "true"}, {}]:
        status, body = _http_raw("/types", params=params_try, tenant_override=ngsild_tenant)
        if status == 200:
            try:
                types_data = json.loads(body)
                if isinstance(types_data, list):
                    type_list = types_data
                elif isinstance(types_data, dict):
                    type_list = types_data.get("typeList", [])
                if type_list:
                    for uri in type_list:
                        if isinstance(uri, str):
                            short = uri.split("/")[-1]
                            _TYPE_URI_CACHE[short] = uri
                            _TYPE_URI_CACHE[uri]   = uri
                    break
            except Exception as e:
                lines.append(f"⚠️ Error parseando tipos: {e}")
                break

    if type_list:
        lines.append(f"**Tipos de entidad disponibles ({len(type_list)}):**\n")
        for t in type_list:
            uri   = t if isinstance(t, str) else t.get("type", str(t))
            short = _short(uri)
            s2, b2 = _http(
                "GET", "/entities",
                params={"type": uri, "limit": 5, "options": "keyValues", "local": "true"},
                tenant_override=ngsild_tenant,
            )
            count_info, sample_names = "", []
            if s2 == 200:
                try:
                    items = json.loads(b2)
                    count_info = f" → {len(items)} entidades"
                    for item in items[:3]:
                        sample_names.append(
                            str(item.get("name", item.get("id", "").split(":")[-1]))
                        )
                except Exception:
                    pass
            lines.append(
                f"  - **{short}**{count_info}"
                + (f": {', '.join(sample_names)}" if sample_names else "")
            )
        lines.append(
            "\n> 💡 Usa `describe_entity_schema(\"<NombreCorto>\")` para ver "
            "los atributos de un tipo concreto."
        )
    else:
        lines.append("⚠️ No hay tipos de entidad registrados (broker vacío o error).")

    return "\n".join(lines)


@mcp.tool(
    name="list_entity_types",
    description=(
        "Lista todos los tipos de entidad disponibles en el broker."
        + _TENANT_PARAM_DOC
    ),
)
def list_entity_types(
    ngsild_tenant: str | None = None,
) -> str:
    for params in [{"local": "true"}, {}]:
        status, body = _http_raw("/types", params=params, tenant_override=ngsild_tenant)
        if status == 200:
            try:
                data      = json.loads(body)
                type_list = data.get("typeList", []) if isinstance(data, dict) else data
                if type_list:
                    short_list = []
                    for t in type_list:
                        uri   = t if isinstance(t, str) else t.get("type", str(t))
                        short = uri.split("/")[-1] if uri.startswith("http") else uri
                        _TYPE_URI_CACHE[short] = uri
                        _TYPE_URI_CACHE[uri]   = uri
                        entry = f"**{short}**" + (f" (`{uri}`)" if short != uri else "")
                        short_list.append(entry)
                    return (
                        f"✅ Tipos disponibles en el broker ({len(short_list)}):\n"
                        + "\n".join(f"  - {s}" for s in short_list)
                        + "\n\nUsa `describe_entity_schema(\"<NombreCorto>\")` para explorar cualquier tipo."
                    )
            except Exception:
                pass
    return _fmt(status, body, "list_entity_types")


@mcp.tool(
    name="get_entity_type_info",
    description=(
        "Obtiene información estructural de un tipo de entidad (atributos presentes)."
        + _TENANT_PARAM_DOC
    ),
)
def get_entity_type_info(
    entity_type:   str,
    ngsild_tenant: str | None = None,
) -> str:
    resolved = _resolve_type_uri(entity_type, tenant_override=ngsild_tenant)
    encoded  = urllib.parse.quote(resolved, safe="")
    status, body = _http("GET", f"/types/{encoded}", tenant_override=ngsild_tenant)
    if status != 200 and resolved != entity_type:
        encoded2 = urllib.parse.quote(entity_type, safe="")
        status, body = _http("GET", f"/types/{encoded2}", tenant_override=ngsild_tenant)
    return _fmt(status, body, f"type_info:{entity_type}")


@mcp.tool(
    name="describe_entity_schema",
    description=(
        "HERRAMIENTA DE COMPRENSIÓN SEMÁNTICA: Obtiene la descripción completa de un tipo "
        "de entidad NGSI-LD. Combina datos reales del broker con esquemas Smart Data Models."
        + _TENANT_PARAM_DOC
    ),
)
def describe_entity_schema(
    entity_type:          str,
    sdm_domain:           Optional[str] = None,
    include_sample_values: bool         = True,
    ngsild_tenant:        str | None    = None,
) -> str:
    lines = [f"## 📋 Esquema del tipo: `{entity_type}`\n"]

    resolved_type = _resolve_type_uri(entity_type, tenant_override=ngsild_tenant)
    encoded_type  = urllib.parse.quote(resolved_type, safe="")

    def _get_sample_entities(fmt_options: str, limit: int = 1) -> list:
        params_q: dict = {"type": resolved_type, "limit": limit, "local": "true"}
        if fmt_options:
            params_q["options"] = fmt_options
        s, b = _http("GET", "/entities", params=params_q, tenant_override=ngsild_tenant)
        if s == 200:
            try:
                items = json.loads(b)
                if items:
                    return items
            except Exception:
                pass
        if resolved_type != entity_type:
            params_q["type"] = entity_type
            s, b = _http("GET", "/entities", params=params_q, tenant_override=ngsild_tenant)
            if s == 200:
                try:
                    items = json.loads(b)
                    if items:
                        return items
                except Exception:
                    pass
        params_all: dict = {"limit": 100, "local": "true"}
        if fmt_options:
            params_all["options"] = fmt_options
        s, b = _http("GET", "/entities", params=params_all, tenant_override=ngsild_tenant)
        if s == 200:
            try:
                all_items    = json.loads(b)
                short_target = resolved_type.split("/")[-1]
                filtered     = [
                    item for item in all_items
                    if str(item.get("type", "")).split("/")[-1] == short_target
                    or item.get("type", "") in (resolved_type, entity_type)
                ]
                return filtered[:limit]
            except Exception:
                pass
        return []

    broker_attrs: dict = {}
    sample_entity = None

    s_type, b_type = _http_raw(f"/types/{encoded_type}", tenant_override=ngsild_tenant)
    if s_type != 200:
        s_type, b_type = _http_raw(
            f"/types/{urllib.parse.quote(entity_type, safe='')}",
            tenant_override=ngsild_tenant,
        )

    if s_type == 200:
        try:
            type_data  = json.loads(b_type)
            attr_names = type_data.get("attributeNames", [])
            attr_meta  = type_data.get("attrs", {})
            if isinstance(attr_names, list):
                for a in attr_names:
                    broker_attrs[a] = {"source": "orion"}
            if isinstance(attr_meta, dict):
                for a, meta in attr_meta.items():
                    broker_attrs.setdefault(a, {})
                    broker_attrs[a]["ngsi_attr_types"] = meta.get("attributeTypes", [])
        except Exception as e:
            _log(f"⚠️  Error parseando type info: {e}")

    if include_sample_values:
        kv_items = _get_sample_entities("keyValues", limit=1)
        if kv_items:
            sample_entity = kv_items[0]
        norm_items = _get_sample_entities("", limit=1)
        if norm_items:
            for attr_name, attr_val in norm_items[0].items():
                if attr_name in ("id", "type", "@context"):
                    continue
                broker_attrs.setdefault(attr_name, {})
                if isinstance(attr_val, dict):
                    ngsi_t = attr_val.get("type", "Property")
                    broker_attrs[attr_name]["ngsi_type"] = ngsi_t
                    if ngsi_t == "Property":
                        broker_attrs[attr_name]["sample_value"] = attr_val.get("value")
                        if "unitCode" in attr_val:
                            broker_attrs[attr_name]["unitCode"] = attr_val["unitCode"]
                        if "observedAt" in attr_val:
                            broker_attrs[attr_name]["has_timestamp"] = True
                    elif ngsi_t == "Relationship":
                        broker_attrs[attr_name]["sample_value"] = attr_val.get("object")
                    elif ngsi_t == "GeoProperty":
                        broker_attrs[attr_name]["sample_value"] = (
                            attr_val.get("value", {}).get("type")
                        )

    sdm_summary  = None
    sdm_url_used = None
    cache_key    = f"{entity_type}:{sdm_domain or ''}"

    if cache_key in _SDM_SCHEMA_CACHE:
        sdm_summary  = _SDM_SCHEMA_CACHE[cache_key]
        sdm_url_used = "(caché)"
    else:
        for url in _build_sdm_candidates(entity_type, sdm_domain):
            _log(f"🔍 Intentando esquema SDM: {url}")
            schema_data = _fetch_url_safe(url)
            if schema_data and "properties" in schema_data:
                sdm_summary  = _extract_schema_summary(schema_data)
                sdm_url_used = url
                _SDM_SCHEMA_CACHE[cache_key] = sdm_summary
                break

    ctx_mapping = {}
    if not sdm_summary and CUSTOM_CONTEXT_PATH:
        ctx_mapping = _resolve_context_mapping()

    if sdm_url_used and sdm_url_used != "(caché)":
        lines.append(f"**Fuente SDM:** {sdm_url_used}")
    if sdm_summary and sdm_summary.get("description"):
        lines.append(f"**Descripción del tipo:** {sdm_summary['description']}\n")
    if sample_entity:
        lines.append(f"**Ejemplo de ID en el broker:** `{sample_entity.get('id', '')}`\n")

    if not broker_attrs and not sdm_summary:
        return (
            f"❌ No se encontró información para el tipo `{entity_type}`.\n"
            f"   URI resuelta: `{resolved_type}`\n"
            f"   Verifica que existe con `list_entity_types()` o `explore_data_model()`."
        )

    lines.append("### Atributos\n")
    lines.append(
        "| Atributo | Tipo NGSI | Descripción | Unidades | Valores posibles | Valor actual |"
    )
    lines.append(
        "|----------|-----------|-------------|----------|------------------|--------------|"
    )

    all_attrs = set(broker_attrs.keys())
    if sdm_summary:
        all_attrs.update(sdm_summary["properties"].keys())
    all_attrs -= {"id", "type", "@context"}

    for attr in sorted(all_attrs):
        bi = broker_attrs.get(attr, {})
        si = (sdm_summary or {}).get("properties", {}).get(attr, {})

        ngsi_type   = bi.get("ngsi_type") or si.get("ngsi_type", "Property")
        description = si.get("description", "")
        if not description and attr in ctx_mapping:
            description = f"URI: `{ctx_mapping[attr]}`"
        description = (
            (description[:90] + "…") if len(description) > 90 else (description or "—")
        )
        units    = bi.get("unitCode") or si.get("units", "—")
        enum_str = ", ".join(f"`{v}`" for v in si.get("enum", [])) or "—"
        sample   = bi.get("sample_value")
        if sample is None and sample_entity:
            sample = sample_entity.get(attr)
        if isinstance(sample, (dict, list)):
            sample_str = json.dumps(sample, ensure_ascii=False)[:55] + "…"
        elif sample is not None:
            sample_str = f"`{str(sample)[:55]}`"
        else:
            sample_str = "—"
        ts = " ⏱" if bi.get("has_timestamp") else ""
        lines.append(
            f"| `{attr}`{ts} | {ngsi_type} | {description} | {units} | {enum_str} | {sample_str} |"
        )

    rels = {k: v for k, v in broker_attrs.items() if v.get("ngsi_type") == "Relationship"}
    if rels:
        lines.append("\n### Relaciones (para navegación)\n")
        lines.append("Usa `get_entity(object_urn)` para resolver las entidades enlazadas:\n")
        for rel_name, rel_info in rels.items():
            target = rel_info.get("sample_value", "")
            if target:
                parts       = str(target).split(":")
                target_type = parts[2] if len(parts) >= 4 else "?"
                lines.append(f"- `{rel_name}` → tipo `{target_type}` (ej: `{target}`)")
            else:
                lines.append(f"- `{rel_name}` → referencia a otra entidad")

    lines.append(f"\n### Cómo consultar este tipo\n```")
    lines.append(f'list_entities(entity_type="{entity_type}")')
    lines.append(f'list_entities(entity_type="{entity_type}", q="<atributo>==<valor>")')
    lines.append(f'get_entity_history("<entity_id>")')
    lines.append("```")

    if not sdm_summary:
        lines.append(
            f"\n> ℹ️ No se encontró esquema SDM estándar para `{entity_type}`. "
            f"Si conoces el dominio, pásalo como `sdm_domain=\"dataModel.XYZ\"`."
        )

    return "\n".join(lines)


# ─── 4. Entidades ─────────────────────────────────────────────────────────────

@mcp.tool(
    name="list_entities",
    description=(
        "Lista entidades NGSI-LD del broker con filtros opcionales. "
        "Soporta filtros por tipo, atributos, expresiones q y paginación."
        + _TENANT_PARAM_DOC
    ),
)
def list_entities(
    entity_type:   Optional[str] = None,
    attrs:         Optional[str] = None,
    q:             Optional[str] = None,
    georel:        Optional[str] = None,
    geometry:      Optional[str] = None,
    coordinates:   Optional[str] = None,
    limit:         int           = 20,
    offset:        int           = 0,
    ngsild_tenant: str | None    = None,
) -> str:
    resolved_type = _resolve_type_uri(entity_type, tenant_override=ngsild_tenant) if entity_type else None
    params = {
        "options": "keyValues",
        "limit":   min(limit, 1000),
        "offset":  offset,
        "local":   "true",
    }
    if resolved_type: params["type"]        = resolved_type
    if attrs:         params["attrs"]        = attrs
    if q:             params["q"]            = q
    if georel:        params["georel"]       = georel
    if geometry:      params["geometry"]     = geometry
    if coordinates:   params["coordinates"]  = coordinates

    status, body = _http("GET", "/entities", params=params, tenant_override=ngsild_tenant)

    if status == 200 and entity_type and resolved_type != entity_type:
        try:
            items = json.loads(body)
            if not items:
                params["type"] = entity_type
                s2, b2 = _http("GET", "/entities", params=params, tenant_override=ngsild_tenant)
                if s2 == 200:
                    status, body = s2, b2
        except Exception:
            pass

    if status == 200 and entity_type:
        try:
            items = json.loads(body)
            if not items:
                params_all = {
                    "options": "keyValues", "limit": min(limit, 1000), "local": "true"
                }
                if q:
                    params_all["q"] = q
                s3, b3 = _http("GET", "/entities", params=params_all, tenant_override=ngsild_tenant)
                if s3 == 200:
                    all_items    = json.loads(b3)
                    short_target = resolved_type.split("/")[-1] if resolved_type else entity_type
                    filtered     = [
                        item for item in all_items
                        if str(item.get("type", "")).split("/")[-1] == short_target
                        or item.get("type", "") == resolved_type
                        or item.get("type", "") == entity_type
                    ]
                    if filtered:
                        body = json.dumps(filtered)
                        _log(f"🔄 Fallback Python-filter: {len(filtered)} entidades de tipo '{entity_type}'")
        except Exception:
            pass

    return _fmt(status, body, f"list_entities(type={entity_type})")

@mcp.tool(
    name="resolve_entity_ids",
    description=(
        "Resuelve un nombre o fragmento a IDs NGSI-LD exactos SIN traer las "
        "entidades completas. Devuelve solo la lista de URNs que coinciden. "
        "Acepta varios términos separados por espacios: TODOS deben aparecer "
        "en el ID (ej. 'carroceria 002 carga' → 1 resultado). Tolera espacios, "
        "guiones y guiones bajos indistintamente. Si se indica entity_type y "
        "el fragmento va vacío, devuelve TODAS las entidades de ese tipo "
        "(útil para 'lista todas las máquinas'). USAR en vez de list_entities "
        "cuando solo necesitas el ID. Payload mínimo."
        + _TENANT_PARAM_DOC
    ),
)
def resolve_entity_ids(
    name_fragment: str = "",
    entity_type:   Optional[str] = None,
    ngsild_tenant: str | None    = None,
) -> str:
    resolved = _resolve_type_uri(entity_type, tenant_override=ngsild_tenant) if entity_type else None
    params = {"options": "keyValues", "limit": 1000, "local": "true"}
    if resolved:
        params["type"] = resolved
    status, body = _http("GET", "/entities", params=params, tenant_override=ngsild_tenant)
    if status != 200:
        return _fmt(status, body, "resolve_entity_ids")
    try:
        items = json.loads(body)
    except Exception:
        return "❌ Respuesta no parseable"

    def _norm(s: str) -> str:
        # minúsculas + colapsa espacios/guiones/guiones_bajos a un único '-'
        return re.sub(r"[\s_\-]+", "-", s.strip().lower())

    # cada palabra del fragmento es un token que DEBE aparecer en el id
    tokens = [_norm(t) for t in (name_fragment or "").split() if t.strip()]

    if not tokens:
        # Sin fragmento: si hay un entity_type, "dame todas las de ese tipo".
        # Si tampoco hay tipo, no hay nada por lo que filtrar → aviso.
        if not entity_type:
            return (
                "Indica un entity_type o un fragmento de búsqueda. "
                "Para enumerar todas las entidades de un tipo, pasa "
                "entity_type sin name_fragment."
            )
        all_ids = [it.get("id", "") for it in items if it.get("id")]
        if not all_ids:
            return f"No hay entidades del tipo '{entity_type}'."
            
        _ENUM_CAP = 50  # enumeración de un tipo completo: tope generoso
        if len(all_ids) > _ENUM_CAP:
            return json.dumps({
                "matches": all_ids[:_ENUM_CAP],
                "count": len(all_ids),
                "truncated": True,
                "hint": f"{len(all_ids)} entidades de tipo '{entity_type}'; "
                        "se muestran las primeras 50. Añade un fragmento para acotar."
            }, ensure_ascii=False)
        return json.dumps({"matches": all_ids, "count": len(all_ids)}, ensure_ascii=False)

    matches = []
    for it in items:
        eid  = it.get("id", "")
        norm = _norm(eid)
        if all(tok in norm for tok in tokens):
            matches.append(eid)

    if not matches:
        return f"Sin coincidencias para '{name_fragment}'."

    # si hay demasiados, devuelve un aviso útil en vez de una lista gigante
    if len(matches) > 25:
        return json.dumps({
            "matches": matches[:25],
            "count": len(matches),
            "truncated": True,
            "hint": "Demasiadas coincidencias; añade más términos para acotar."
        }, ensure_ascii=False)

    return json.dumps({"matches": matches, "count": len(matches)}, ensure_ascii=False)
    
@mcp.tool(
    name="get_entity",
    description=(
        "Obtiene una entidad NGSI-LD por su URN completo."
        + _TENANT_PARAM_DOC
    ),
)
def get_entity(
    entity_id:     str,
    attrs:         Optional[str] = None,
    ngsild_tenant: str | None    = None,
) -> str:
    params = {"options": "keyValues"}
    if attrs:
        params["attrs"] = attrs
    encoded_id   = urllib.parse.quote(entity_id, safe="")
    status, body = _http("GET", f"/entities/{encoded_id}", params=params, tenant_override=ngsild_tenant)
    if status == 404:
        params2      = {k: v for k, v in params.items() if k != "options"}
        status, body = _http("GET", f"/entities/{encoded_id}", params=params2, tenant_override=ngsild_tenant)
    return _fmt(status, body, f"get_entity:{entity_id}")


@mcp.tool(
    name="get_entity_attributes",
    description=(
        "Obtiene metadatos de los atributos de una entidad (tipos NGSI-LD, observedAt, etc.)."
        + _TENANT_PARAM_DOC
    ),
)
def get_entity_attributes(
    entity_id:     str,
    ngsild_tenant: str | None = None,
) -> str:
    encoded_id   = urllib.parse.quote(entity_id, safe="")
    status, body = _http("GET", f"/entities/{encoded_id}/attrs", tenant_override=ngsild_tenant)
    return _fmt(status, body, f"get_attributes:{entity_id}")


@mcp.tool(
    name="query_entities",
    description=(
        "Consulta avanzada de entidades NGSI-LD con POST /entityOperations/query."
        + _TENANT_PARAM_DOC
    ),
)
def query_entities(
    query_json:    str,
    ngsild_tenant: str | None = None,
) -> str:
    try:
        query = json.loads(query_json)
    except json.JSONDecodeError as e:
        return f"❌ JSON inválido: {e}"
    status, body = _http(
        "POST", "/entityOperations/query",
        body=query,
        params={"options": "keyValues"},
        content_type="application/json",
        tenant_override=ngsild_tenant,
    )
    return _fmt(status, body, "query_entities")


@mcp.tool(
    name="count_entities",
    description=(
        "Cuenta entidades en el broker, opcionalmente filtradas por tipo o expresión q."
        + _TENANT_PARAM_DOC
    ),
)
def count_entities(
    entity_type:   Optional[str] = None,
    q:             Optional[str] = None,
    ngsild_tenant: str | None    = None,
) -> str:
    resolved_type = _resolve_type_uri(entity_type, tenant_override=ngsild_tenant) if entity_type else None
    params = {"limit": 1000, "local": "true"}
    if resolved_type: params["type"] = resolved_type
    if q:             params["q"]    = q
    status, body = _http("GET", "/entities", params=params, tenant_override=ngsild_tenant)
    if status == 200:
        try:
            count  = len(json.loads(body))
            label  = f" de tipo '{entity_type}'" if entity_type else ""
            flabel = f" con q='{q}'" if q else ""
            return f"✅ Entidades{label}{flabel}: {count}"
        except Exception:
            pass
    return _fmt(status, body, "count_entities")


@mcp.tool(
    name="get_entity_history",
    description=(
        "Historial temporal de una entidad vía API temporal NGSI-LD."
        + _TENANT_PARAM_DOC
    ),
)
def get_entity_history(
    entity_id:     str,
    attrs:         Optional[str] = None,
    time_from:     Optional[str] = None,
    time_to:       Optional[str] = None,
    limit:         int           = 20,
    ngsild_tenant: str | None    = None,
) -> str:
    encoded_id = urllib.parse.quote(entity_id, safe="")
    params     = {"options": "temporalValues", "limit": limit}
    if attrs:     params["attrs"]     = attrs
    if time_from: params["timeAt"]    = time_from
    if time_to:   params["endTimeAt"] = time_to
    qs  = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{NGSI_BASE}/temporal/entities/{encoded_id}"
    url = f"{url}?{qs}" if qs else url

    req_headers = {"Accept": "application/ld+json"}
    tenant = _effective_tenant(ngsild_tenant)
    if tenant:
        req_headers["NGSILD-Tenant"] = tenant

    req = urllib.request.Request(url, headers=req_headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8")
            try:
                parsed = json.loads(body)
                return (
                    f"✅ Historial de {entity_id}:\n"
                    f"```json\n{json.dumps(parsed, indent=2, ensure_ascii=False)}\n```"
                )
            except Exception:
                return f"✅ HTTP {resp.status}: {body}"
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        if e.code == 404:
            return "❌ API temporal no disponible o entidad no encontrada."
        return f"❌ HTTP {e.code}: {body}"
    except Exception as e:
        return f"❌ Error: {e}"


# ─── 5. Suscripciones ─────────────────────────────────────────────────────────

@mcp.tool(
    name="list_subscriptions",
    description="Lista todas las suscripciones activas en el broker." + _TENANT_PARAM_DOC,
)
def list_subscriptions(
    limit:         int        = 20,
    offset:        int        = 0,
    ngsild_tenant: str | None = None,
) -> str:
    status, body = _http(
        "GET", "/subscriptions",
        params={"limit": limit, "offset": offset},
        tenant_override=ngsild_tenant,
    )
    return _fmt(status, body, "list_subscriptions")


@mcp.tool(
    name="get_subscription",
    description="Obtiene los detalles de una suscripción por su ID." + _TENANT_PARAM_DOC,
)
def get_subscription(
    subscription_id: str,
    ngsild_tenant:   str | None = None,
) -> str:
    encoded_id   = urllib.parse.quote(subscription_id, safe="")
    status, body = _http("GET", f"/subscriptions/{encoded_id}", tenant_override=ngsild_tenant)
    return _fmt(status, body, f"get_subscription:{subscription_id}")


# ─── 6. Registros ─────────────────────────────────────────────────────────────

@mcp.tool(
    name="list_registrations",
    description="Lista los registros de fuentes de contexto (arquitecturas federadas)." + _TENANT_PARAM_DOC,
)
def list_registrations(
    limit:         int        = 20,
    offset:        int        = 0,
    ngsild_tenant: str | None = None,
) -> str:
    status, body = _http(
        "GET", "/csourceRegistrations",
        params={"limit": limit, "offset": offset},
        tenant_override=ngsild_tenant,
    )
    return _fmt(status, body, "list_registrations")


# ══════════════════════════════════════════════════════════════════════════════
# HEALTH CHECK DE ARRANQUE
# ══════════════════════════════════════════════════════════════════════════════

def _build_schema_cache(tenant_override: str | None = None) -> None:
    global _SCHEMA_CACHE, _SCHEMA_SUMMARY, _TYPE_URI_CACHE
    tenant_key = tenant_override or NGSI_TENANT or "__default__"

    _TYPE_URI_CACHE.clear()
    _build_type_cache(tenant_override=tenant_override)
    if not _TYPE_URI_CACHE:
        return

    short_types = sorted(set(k for k in _TYPE_URI_CACHE if not k.startswith("http")))
    lines: list = ["## DATA SPACE SCHEMA (pre-built at startup)\n"]
    cache: dict = {}
    value_types: list = []

    _STOP_TOKENS = {"meas", "urn", "ngsi", "ld"}

    for short in short_types:
        uri     = _TYPE_URI_CACHE.get(short, short)
        encoded = urllib.parse.quote(uri, safe="")

        # 1) attributeNames del /types/<uri>
        attr_names: list = []
        s, b = _http_raw(f"/types/{encoded}", tenant_override=tenant_override)
        if s == 200:
            try:
                td = json.loads(b)
                attr_names = td.get("attributeNames", [])
            except Exception:
                pass

        # 2) limit=1000 keyValues → count, ids, controlledProperty
        all_ids: list = []
        count: int = 0
        controlled_props: set = set()
        s4, b4 = _http("GET", "/entities", params={
            "type": uri, "limit": 1000, "options": "keyValues", "local": "true"
        }, tenant_override=tenant_override)
        if s4 == 200:
            try:
                items_full = json.loads(b4)
                count = len(items_full)
                for item in items_full:
                    eid = item.get("id", "")
                    if not eid:
                        continue
                    all_ids.append(eid)
                    for k, v in item.items():
                        if k in ("id", "type", "@context"):
                            continue
                        attr_key = k.split("/")[-1] if "/" in k else k
                        if attr_key == "controlledProperty":
                            if isinstance(v, list):
                                controlled_props.update(v)
                            elif isinstance(v, str):
                                controlled_props.add(v)
            except Exception:
                pass

        # 3) 1 entidad normalizada → Properties + Relationships + has_num_value
        rel_map: dict = {}
        sample_props: set = set()
        has_num_value: bool = False
        s3, b3 = _http("GET", "/entities", params={
            "type": uri, "limit": 1, "local": "true"
        }, tenant_override=tenant_override)
        if s3 == 200:
            try:
                items3 = json.loads(b3)
                if items3:
                    for k, v in items3[0].items():
                        if k in ("id", "type", "@context"):
                            continue
                        attr_key = k.split("/")[-1] if "/" in k else k
                        if isinstance(v, dict):
                            ngsi_t = v.get("type", "Property")
                            if ngsi_t == "Relationship":
                                obj = v.get("object", "")
                                if obj.startswith("urn:ngsi-ld:"):
                                    rel_map[attr_key] = obj.split(":")[2]
                            elif ngsi_t in ("Property", "GeoProperty"):
                                sample_props.add(attr_key)
                                if attr_key == "numValue":
                                    has_num_value = True
            except Exception:
                pass

        # 4) keyword index
        id_keywords: set = set()
        for eid in all_ids:
            last_segment = eid.split(":")[-1]
            for tok in re.split(r"[-_\s]+", last_segment.lower()):
                if not tok or tok.isdigit() or len(tok) < 3 or tok in _STOP_TOKENS:
                    continue
                id_keywords.add(tok)
        sorted_keywords = sorted(id_keywords)
        sample_ids = [eid.split(":")[-1] for eid in all_ids[:15]]

        # 5) attrs merged (de /types + sample) con flecha en Relationships
        all_attr_names = set(
            a.split("/")[-1] if "/" in a else a for a in attr_names
        ) | sample_props | set(rel_map.keys())
        attr_parts: list = []
        for short_a in sorted(all_attr_names):
            if short_a in rel_map:
                attr_parts.append(f"{short_a}→{rel_map[short_a]}")
            else:
                attr_parts.append(short_a)

        # 6) escritura
        marker = " [VALUE TYPE — has numValue]" if has_num_value else ""
        lines.append(f"TYPE {short} ({count} entities){marker}")
        if attr_parts:
            lines.append(f"  attrs: {', '.join(attr_parts[:20])}")
        if controlled_props:
            lines.append(f"  controlledProperties: {', '.join(sorted(controlled_props))}")
        if sorted_keywords:
            lines.append(f"  id keywords: {', '.join(sorted_keywords)}")
        if sample_ids:
            lines.append(f"  sample ids: {', '.join(sample_ids)}")
        lines.append("")

        if has_num_value:
            value_types.append(short)
        cache[short] = {
            "uri": uri, "count": count, "attrs": attr_parts,
            "relationships": rel_map,
            "controlled_properties": sorted(controlled_props),
            "id_keywords": sorted_keywords,
            "sample_ids": sample_ids,
            "is_value_type": has_num_value,
        }

    # 7) sección VALUE TYPES — crítica para queries de valor
    if value_types:
        lines.append("## VALUE TYPES (where live numeric readings live)")
        lines.append("These types carry the actual numeric reading (numValue) and its")
        lines.append("observedAt timestamp. For ANY 'what is the current X of <asset>?'")
        lines.append("question, ALWAYS use one of these types (NOT the asset type, NOT")
        lines.append("the sensor/device descriptor type — those only have metadata):")
        for vt in value_types:
            lines.append(f"  - {vt}")
        lines.append("")

    # 8) anti-q-misuse
    lines.append("## HOW TO FIND ENTITIES BY KEYWORD")
    lines.append("The 'id keywords' lists are EXHAUSTIVE. To find/enumerate entities:")
    lines.append("  1. Locate the keyword in the appropriate type's 'id keywords'.")
    lines.append("  2. resolve_entity_ids(name_fragment='<keyword(s)>', entity_type='<Type>').")
    lines.append("NEVER use list_entities(q='<keyword>') for id search — `q` filters")
    lines.append("attribute values (q='attr==v'), not id substrings. Returns [] otherwise.")
    lines.append("")
    lines.append("## RELATIONSHIP MAP")
    for short, info in sorted(cache.items()):
        rels = info.get("relationships", {})
        if rels:
            rel_str = ", ".join(f"{k}→{v}" for k, v in rels.items())
            lines.append(f"  {short}: {rel_str}")

    _SCHEMA_CACHE[tenant_key] = cache
    _SCHEMA_SUMMARY[tenant_key] = "\n".join(lines)
    _log(f"✅ Schema cache [{tenant_key}]: {len(cache)} tipos, "
         f"{sum(v['count'] for v in cache.values())} entidades totales")
    _log(f"   VALUE TYPES: {value_types}")
    _log(f"   Schema summary: {len(_SCHEMA_SUMMARY[tenant_key])} chars / "
         f"~{len(_SCHEMA_SUMMARY[tenant_key])//4} tokens estimados")
    total_kw = sum(len(v['id_keywords']) for v in cache.values())
    _log(f"   Keyword index: {total_kw} keywords únicos en {len(cache)} tipos")


def _startup_health_check() -> None:
    """
    Consulta Orion al arranque para mostrar cuántos tipos y entidades tiene
    en ese momento con el tenant configurado por defecto.
    También precarga _TYPE_URI_CACHE para acelerar el primer tool call.
    """
    tenant_label = NGSI_TENANT if NGSI_TENANT else "(default / sin tenant)"
    _log(f"   Tenant activo: {tenant_label}")
    _log(f"   API base:      {NGSI_BASE}")

    # ── Tipos de entidad ─────────────────────────────────────────────────────
    type_count  = 0
    type_names: list[str] = []

    for params in [{"local": "true"}, {}]:
        status, body = _http_raw("/types", params=params)

        if status == 0:
            _log(f"   ❌ Sin conexión: {ORION_URL}")
            _log(f"      {body}")
            _log(f"      Verifica ORION_URL en config.yaml")
            return

        if status == 200:
            try:
                data      = json.loads(body)
                type_list = data.get("typeList", []) if isinstance(data, dict) else data
                if isinstance(type_list, list) and type_list:
                    for uri in type_list:
                        if isinstance(uri, str):
                            short = uri.split("/")[-1] if uri.startswith("http") else uri
                            _TYPE_URI_CACHE[short] = uri
                            _TYPE_URI_CACHE[uri]   = uri
                    type_count = len(type_list)
                    type_names = sorted(
                        k for k in _TYPE_URI_CACHE if not k.startswith("http")
                    )
                    break
            except Exception as e:
                _log(f"   ⚠️  Error parseando tipos: {e}")
                break

    # ── Total de entidades ────────────────────────────────────────────────────
    entity_count = 0
    items_found  = []
    status, body = _http("GET", "/entities", params={"limit": 1000, "local": "true"})
    if status == 200:
        try:
            items_found  = json.loads(body)
            entity_count = len(items_found)
        except Exception:
            pass

    sdm_known = sum(1 for t in type_names if t in _SDM_DOMAIN_MAP)

    if type_count == 0 and entity_count == 0:
        _log("   ⚠️  Orion responde pero está vacío (0 tipos · 0 entidades)")
        _log("      El broker está en línea pero aún no tiene datos cargados.")
        if NGSI_TENANT:
            _log(f"      ¿Los datos se cargaron con el mismo tenant '{NGSI_TENANT}'?")
        else:
            _log("      ¿Los datos se cargaron con NGSILD-Tenant o sin él?")
    else:
        sdm_note = f" · {sdm_known} con esquema SDM" if sdm_known else ""
        _log(f"   ✅ Orion con datos — {type_count} tipos · {entity_count} entidades{sdm_note}")
        if items_found:
            _log("   Entidades:")
            for item in items_found:
                _log(f"      {item.get('id', '?')}")
        # Schema cache builds lazily on first tenant use — no startup pre-build.


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _log("🚀 Iniciando servidor MCP Orion-LD v2.5.0-readonly...")
    _log(f"   Broker: {ORION_URL}")
    _log(f"   Contexto custom URL: {CUSTOM_CONTEXT_URL or '(no configurado)'}")
    if CUSTOM_CONTEXT_PATH:
        _log(f"   Contexto custom PATH: {CUSTOM_CONTEXT_PATH}")
    _log(f"   Type URI resolver: activado (local=true en Orion-LD 1.x)")
    _log(f"   Multi-tenant: activado (ngsild_tenant por petición)")
    _log(f"   Comprobando Orion...")
    _startup_health_check()

    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", default="stdio", choices=["stdio", "sse"])
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()

    if args.server_type == "stdio":
        _log("📡 Modo STDIO (producción)")
        try:
            mcp.run(transport="stdio")
        except Exception as e:
            _log(f"❌ Error fatal: {e}")
            sys.exit(1)
    else:
        _log(f"📡 Modo SSE en puerto {args.port}")
        try:
            import uvicorn
            orig = uvicorn.Config.__init__
            def patched(self, *a, **kw):
                kw["port"] = args.port
                kw["host"] = "0.0.0.0"
                orig(self, *a, **kw)
            uvicorn.Config.__init__ = patched
            mcp.run(transport="sse")
        except ImportError:
            _log("❌ uvicorn no instalado.")
            sys.exit(1)