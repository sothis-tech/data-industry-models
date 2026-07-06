# servers/chart_engine_server.py
# -*- coding: utf-8 -*-
"""
MCP Server — Chart Engine con URL delivery
═══════════════════════════════════════════════════════════════

El LLM llama a generate_chart con entity_id + attribute + period.
El server internamente:
  1. Consulta Quantum Leap via REST
  2. Hace fuzzy match del atributo
  3. Trae el histórico agregado
  4. Construye el template de gráfico
  5. Lo guarda como fichero JSON en disco
  6. Devuelve al LLM SOLO: URL del fichero + stats

El LLM pasa la URL al usuario. Las gafas Vuzix (o cualquier cliente)
hacen GET a esa URL y obtienen el template completo.

Los datos NUNCA pasan por el LLM.

Config (env vars):
  ORION_URL              — URL de Orion-LD (default: http://localhost:1026)
  QL_HOST / QL_PORT      — Quantum Leap (default: localhost:8668)
  NGSI_TENANT            — Tenant FIWARE (default: "")
  CHART_OUTPUT_DIR       — Donde guardar los JSONs (default: ./chart_outputs)
  CHART_BASE_URL         — URL base pública (default: http://localhost:8081)
  CHART_TTL_MINUTES      — Tiempo de vida de los ficheros (default: 60)
  CHART_ENGINE_TIMEOUT   — Timeout HTTP en segundos (default: 15)
"""

import sys
import os
import json
import re
import uuid
import time
import argparse
import unicodedata
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP
from project.chart_builder import build_chart_payload, compute_stats


def _log(msg: str):
    print(f"[ChartEngine] {msg}", file=sys.stderr)


# ─── Config ───────────────────────────────────────────────────────────────────

ORION_URL      = os.getenv("ORION_URL", "http://localhost:1026").rstrip("/")
QL_HOST        = os.getenv("QL_HOST", "localhost")
QL_PORT        = int(os.getenv("QL_PORT", "8668"))
NGSI_TENANT    = os.getenv("NGSI_TENANT", "")
TIMEOUT        = int(os.getenv("CHART_ENGINE_TIMEOUT", "15"))
CHART_DIR      = os.getenv("CHART_OUTPUT_DIR", "./chart_outputs")
CHART_BASE_URL = os.getenv("CHART_BASE_URL", "http://localhost:8081").rstrip("/")
CHART_TTL_MIN  = int(os.getenv("CHART_TTL_MINUTES", "60"))

QL_BASE = f"http://{QL_HOST}:{QL_PORT}"

# Crear directorio de salida
Path(CHART_DIR).mkdir(parents=True, exist_ok=True)

mcp = FastMCP("chart-engine-server")


# ─── HTTP ─────────────────────────────────────────────────────────────────────

def _ql_get(path: str, params: Optional[dict] = None) -> dict:
    url = f"{QL_BASE}{path}"
    if params:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        if qs:
            url = f"{url}?{qs}"
    headers = {"Accept": "application/json"}
    if NGSI_TENANT:
        headers["Fiware-Service"] = NGSI_TENANT
        headers["Fiware-ServicePath"] = "/"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"_not_found": True}
        body = e.read().decode("utf-8") if e.fp else ""
        return {"_error": True, "status": e.code, "body": body[:200]}
    except Exception as e:
        return {"_error": True, "detail": str(e)}


# ─── Fuzzy Match ──────────────────────────────────────────────────────────────

def _normalize(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[\s_\-\.]+", "", s.lower())


def _match_attribute(requested: str, available: List[str]) -> Optional[str]:
    if not available or not requested:
        return None
    nr = _normalize(requested)
    if not nr:
        return None
    for a in available:
        if _normalize(a) == nr:
            return a
    for a in available:
        na = _normalize(a)
        if na and (na in nr or nr in na):
            return a
    aliases = {
        "temperatura": ["temperature", "temp"],
        "peso":        ["weight", "pesocarga", "load"],
        "presion":     ["pressure"],
        "humedad":     ["humidity"],
        "velocidad":   ["speed", "rpm"],
        "caudal":      ["flow", "flowrate"],
        "potencia":    ["power", "watt"],
        "energia":     ["energy", "kwh"],
    }
    for es, ens in aliases.items():
        if nr == es or nr in ens:
            for a in available:
                na = _normalize(a)
                if na == es or na in ens or any(x in na for x in [es] + ens):
                    return a
    return None


# ─── Date ─────────────────────────────────────────────────────────────────────

def _iso_offset(hours=0, days=0):
    dt = datetime.now(timezone.utc) - timedelta(hours=hours, days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

PERIOD_TO_AGGR = {
    "last_hour": "minute", "last_day": "hour",
    "last_week": "day",    "last_month": "day",
}
PERIOD_TO_FROM = {
    "last_hour":  lambda: _iso_offset(hours=1),
    "last_day":   lambda: _iso_offset(days=1),
    "last_week":  lambda: _iso_offset(days=7),
    "last_month": lambda: _iso_offset(days=30),
}
PERIOD_DISPLAY = {
    "last_hour": "última hora", "last_day": "último día",
    "last_week": "última semana", "last_month": "último mes",
}


# ─── File management ─────────────────────────────────────────────────────────

def _save_chart(payload: dict) -> str:
    """Guarda el template como JSON, devuelve el chart_id."""
    chart_id = f"chart_{uuid.uuid4().hex[:12]}"
    filepath = Path(CHART_DIR) / f"{chart_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    _log(f"  Guardado: {filepath} ({filepath.stat().st_size} bytes)")
    return chart_id


def _cleanup_old_charts():
    """Limpia ficheros más viejos que CHART_TTL_MIN."""
    cutoff = time.time() - (CHART_TTL_MIN * 60)
    chart_dir = Path(CHART_DIR)
    removed = 0
    for f in chart_dir.glob("chart_*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    if removed:
        _log(f"  Cleanup: {removed} ficheros viejos eliminados")


def _build_url(chart_id: str) -> str:
    """Construye la URL pública del chart."""
    return f"{CHART_BASE_URL}/charts/{chart_id}.json"


# ═══════════════════════════════════════════════════════════════════
# HERRAMIENTAS MCP
# ═══════════════════════════════════════════════════════════════════

@mcp.tool(
    name="generate_chart",
    description=(
        "Genera un gráfico temporal completo para una entidad NGSI-LD. "
        "Internamente consulta Quantum Leap (fuzzy match de atributos: "
        "'peso'->'Peso_Carga', 'temp'->'Temperatura'), construye la plantilla "
        "y la guarda como fichero accesible via URL. "
        "Devuelve la URL del gráfico + estadísticas. "
        "Requiere entity_id (URN completo de Orion-LD). "
        "El LLM debe pasar la chart_url en el campo 'data' de su respuesta."
    ),
)
def generate_chart(
    entity_id: str,
    attribute: str,
    period: str = "last_day",
    chart_type: str = "line",
    aggr_method: str = "avg",
    color_hex: str = "#00FFFF",
) -> str:
    _log(f"generate_chart │ entity={entity_id} attr={attribute} "
         f"period={period} type={chart_type}")

    # Limpieza periódica
    #_cleanup_old_charts()

    # ── Validaciones ───────────────────────────────────────────
    if not entity_id or not entity_id.startswith("urn:"):
        return json.dumps({"error": "entity_id debe ser un URN completo (urn:ngsi-ld:...)."})

    if period not in PERIOD_TO_AGGR:
        return json.dumps({"error": f"period debe ser: {list(PERIOD_TO_AGGR.keys())}"})

    if chart_type not in ("line", "bar"):
        return json.dumps({"error": "chart_type debe ser 'line' o 'bar'."})

    # ── 1. Descubrir atributos en QL ───────────────────────────
    disc = _ql_get(f"/v2/entities/{entity_id}", params={"lastN": "1"})
    if disc.get("_not_found") or disc.get("_error"):
        return json.dumps({
            "error": "entity_not_in_ql",
            "message": f"La entidad '{entity_id}' no tiene histórico en Quantum Leap.",
        })

    available = [a.get("attrName", "") for a in disc.get("attributes", []) if a.get("attrName")]
    if not available:
        return json.dumps({"error": "La entidad existe en QL pero sin atributos históricos."})

    # ── 2. Fuzzy match ─────────────────────────────────────────
    real_attr = _match_attribute(attribute, available)
    if real_attr is None:
        return json.dumps({
            "error": "attribute_not_found",
            "message": f"'{attribute}' no encontrado. Disponibles: {available}.",
            "available": available,
        })
    if real_attr != attribute:
        _log(f"  Fuzzy match: '{attribute}' → '{real_attr}'")

    # ── 3. Traer histórico ─────────────────────────────────────
    aggr_period = PERIOD_TO_AGGR[period]
    from_date = PERIOD_TO_FROM[period]()

    ql_data = _ql_get(
        f"/v2/entities/{entity_id}/attrs/{real_attr}",
        params={"fromDate": from_date, "aggrMethod": aggr_method, "aggrPeriod": aggr_period},
    )

    # Retry con periodo más amplio
    if ql_data.get("_not_found") or ql_data.get("_error"):
        _log(f"  Sin datos en {period}, reintentando last_week")
        ql_data = _ql_get(
            f"/v2/entities/{entity_id}/attrs/{real_attr}",
            params={"fromDate": _iso_offset(days=7), "aggrMethod": aggr_method, "aggrPeriod": "day"},
        )
        if ql_data.get("_not_found") or ql_data.get("_error"):
            return json.dumps({"error": f"Sin datos de '{real_attr}' en ningún rango reciente."})
        period = "last_week"

    index = ql_data.get("index", [])
    values = ql_data.get("values", [])
    series = [{"timestamp": ts, "value": v} for ts, v in zip(index, values)]

    if not series:
        return json.dumps({"error": f"Serie vacía para '{real_attr}' en '{period}'."})

    # ── 4. Construir template ──────────────────────────────────
    payload = build_chart_payload(real_attr, series, chart_type=chart_type, color_hex=color_hex)
    stats = compute_stats(payload["dataset"]["values"])

    # ── 5. Guardar como fichero ────────────────────────────────
    chart_id = _save_chart(payload)
    chart_url = _build_url(chart_id)

    _log(f"  OK │ attr={real_attr} points={stats['count']} url={chart_url}")

    # ── 6. Devolver URL + stats al LLM ─────────────────────────
    period_es = PERIOD_DISPLAY.get(period, period)

    return json.dumps({
        "status": "ok",
        "chart_url": chart_url,
        "parameter": real_attr,
        "requested_as": attribute,
        "period": period_es,
        "chart_type": chart_type,
        "stats": stats,
        "instruction": (
            f"Gráfico generado. Pon chart_url en el campo 'data' de tu respuesta: "
            f"\"data\": {{\"chart_url\": \"{chart_url}\", \"event\": \"chart_data\"}}. "
            f"En speech/text usa solo los stats."
        ),
    }, ensure_ascii=False)


@mcp.tool(
    name="list_chartable_attributes",
    description=(
        "Lista los atributos con histórico disponible en Quantum Leap "
        "para una entidad. Útil para saber qué se puede graficar."
    ),
)
def list_chartable_attributes(entity_id: str) -> str:
    if not entity_id or not entity_id.startswith("urn:"):
        return json.dumps({"error": "entity_id debe ser un URN completo."})

    disc = _ql_get(f"/v2/entities/{entity_id}", params={"lastN": "1"})
    if disc.get("_not_found") or disc.get("_error"):
        return json.dumps({"entity_id": entity_id, "attributes": [], "message": "Sin histórico en QL."})

    index = disc.get("index", [])
    last_ts = index[-1] if index else None
    attrs = []
    for attr in disc.get("attributes", []):
        name = attr.get("attrName", "")
        vals = attr.get("values", [])
        if name:
            attrs.append({"name": name, "last_value": vals[-1] if vals else None, "last_timestamp": last_ts})

    return json.dumps({"entity_id": entity_id, "attributes": attrs, "count": len(attrs)}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _log("🚀 Iniciando Chart Engine MCP Server (URL mode)")
    _log(f"   QL:        {QL_BASE}")
    _log(f"   Tenant:    {NGSI_TENANT or '(sin tenant)'}")
    _log(f"   Output:    {CHART_DIR}")
    _log(f"   Base URL:  {CHART_BASE_URL}")
    _log(f"   TTL:       {CHART_TTL_MIN} min")

    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", default="stdio", choices=["stdio", "sse"])
    parser.add_argument("--port", type=int, default=8004)
    args = parser.parse_args()

    if args.server_type == "stdio":
        _log("📡 Modo STDIO")
        try:
            mcp.run(transport="stdio")
        except Exception as e:
            _log(f"❌ Error fatal: {e}")
            sys.exit(1)
    else:
        _log(f"📡 Modo SSE en puerto {args.port}")
        import uvicorn
        orig = uvicorn.Config.__init__
        def patched(self, *a, **kw):
            kw["port"] = args.port
            kw["host"] = "0.0.0.0"
            orig(self, *a, **kw)
        uvicorn.Config.__init__ = patched
        mcp.run(transport="sse")