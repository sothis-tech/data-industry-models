"""
INN Data Space — Context Server.

Servidor de contexto multi-tenant: almacena el modelo NGSI-LD de cada tenant
(schemas, contexto JSON-LD, descriptor de relaciones y ejemplos) en disco,
organizado por carpetas con la misma estructura que el paquete .zip estándar:

    <TENANTS_ROOT>/<tenant>/
        descriptor.json
        meta.json                 (metadatos: packageName, updatedAt)
        context/context.jsonld
        schemas/<Entidad>.json
        examples/<Entidad>/example.json

API:
    GET    /health
    GET    /tenants
    POST   /tenants                     {"name": "<tenant>"}
    DELETE /tenants/{tenant}
    GET    /tenants/{tenant}/model
    PUT    /tenants/{tenant}/model      (reemplaza el modelo completo)
    DELETE /tenants/{tenant}/model
    GET    /tenants/{tenant}/context.jsonld
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

TENANTS_ROOT = Path(os.environ.get("TENANTS_ROOT", "/data/tenants"))

# Mismo criterio que los tenants NGSILD (Orion-LD): minúsculas, dígitos, _ y -.
TENANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

# Nombres de fichero derivados de títulos de schema / claves de ejemplo.
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_-]+")

app = FastAPI(title="INN Data Space — Context Server", version="1.0.0")


class TenantIn(BaseModel):
    name: str


class ModelIn(BaseModel):
    schemas: List[Any] = []
    context: Any = None
    descriptor: Any = None
    examples: Dict[str, Any] = {}
    packageName: Optional[str] = None
    contextUrl: Optional[str] = None


def _validate_tenant(tenant: str) -> str:
    tenant = (tenant or "").strip()
    if not TENANT_RE.match(tenant):
        raise HTTPException(
            400,
            "Nombre de tenant no válido: usa minúsculas, dígitos, '-' o '_' (máx. 64).",
        )
    return tenant


def _tenant_dir(tenant: str) -> Path:
    return TENANTS_ROOT / _validate_tenant(tenant)


def _safe_filename(name: str, fallback: str) -> str:
    cleaned = SAFE_NAME_RE.sub("_", (name or "").strip()).strip("_")
    return cleaned or fallback


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _model_paths(base: Path) -> dict[str, Path]:
    return {
        "context_dir": base / "context",
        "schemas_dir": base / "schemas",
        "examples_dir": base / "examples",
        "descriptor": base / "descriptor.json",
        "meta": base / "meta.json",
    }


def _clear_model_files(base: Path) -> None:
    """Borra todo el modelo del tenant (cada carga sustituye el contenido anterior)."""
    p = _model_paths(base)
    for d in (p["context_dir"], p["schemas_dir"], p["examples_dir"]):
        shutil.rmtree(d, ignore_errors=True)
    for f in (p["descriptor"], p["meta"]):
        f.unlink(missing_ok=True)


def _has_context_on_disk(base: Path) -> bool:
    p = _model_paths(base)
    if not p["context_dir"].is_dir():
        return False
    return bool(
        list(p["context_dir"].glob("*.jsonld")) or list(p["context_dir"].glob("*.json"))
    )


def _read_model(base: Path) -> dict[str, Any]:
    p = _model_paths(base)

    schemas: list[Any] = []
    if p["schemas_dir"].is_dir():
        for f in sorted(p["schemas_dir"].glob("*.json")):
            try:
                schemas.append(_read_json(f))
            except (json.JSONDecodeError, OSError):
                continue

    context: Any = None
    if p["context_dir"].is_dir():
        candidates = sorted(p["context_dir"].glob("*.jsonld")) or sorted(
            p["context_dir"].glob("*.json")
        )
        for f in candidates:
            try:
                context = _read_json(f)
                break
            except (json.JSONDecodeError, OSError):
                continue

    descriptor: Any = None
    if p["descriptor"].is_file():
        try:
            descriptor = _read_json(p["descriptor"])
        except (json.JSONDecodeError, OSError):
            descriptor = None

    examples: dict[str, Any] = {}
    if p["examples_dir"].is_dir():
        for entity_dir in sorted(p["examples_dir"].iterdir()):
            if not entity_dir.is_dir():
                continue
            for f in sorted(entity_dir.glob("*.json")):
                try:
                    examples[entity_dir.name] = _read_json(f)
                    break
                except (json.JSONDecodeError, OSError):
                    continue

    meta: dict[str, Any] = {}
    if p["meta"].is_file():
        try:
            meta = _read_json(p["meta"])
        except (json.JSONDecodeError, OSError):
            meta = {}

    return {
        "schemas": schemas,
        "context": context,
        "descriptor": descriptor,
        "examples": examples,
        "packageName": meta.get("packageName"),
        "contextUrl": meta.get("contextUrl"),
        "updatedAt": meta.get("updatedAt"),
    }


def _write_model(base: Path, model: ModelIn) -> dict[str, Any]:
    """
    Sustituye el modelo del tenant por el de esta carga.

    - Si `context` viene informado → se materializa en context/context.jsonld
      (carga solo-zip).
    - Si `context` es null → no queda context/ en disco (carga por URL o zip+URL,
      donde la URL gana y el contexto es solo referencia en meta.contextUrl).
    """
    p = _model_paths(base)
    _clear_model_files(base)
    base.mkdir(parents=True, exist_ok=True)

    used_names: set[str] = set()
    for i, schema in enumerate(model.schemas):
        title = schema.get("title") if isinstance(schema, dict) else None
        name = _safe_filename(str(title) if title else "", f"schema-{i:03d}")
        if name in used_names:
            name = f"{name}-{i:03d}"
        used_names.add(name)
        _write_json(p["schemas_dir"] / f"{name}.json", schema)

    if model.context is not None:
        _write_json(p["context_dir"] / "context.jsonld", model.context)

    if model.descriptor is not None:
        _write_json(p["descriptor"], model.descriptor)

    for key, example in model.examples.items():
        entity = _safe_filename(key, "Entity")
        _write_json(p["examples_dir"] / entity / "example.json", example)

    _write_json(
        p["meta"],
        {
            "packageName": model.packageName,
            "contextUrl": model.contextUrl,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        },
    )

    return {
        "schemas": len(model.schemas),
        "context": _has_context_on_disk(base),
        "descriptor": model.descriptor is not None,
        "examples": len(model.examples),
        "contextUrl": model.contextUrl,
    }


# ---------- Endpoints ----------


@app.get("/health")
def health():
    return {"ok": True, "service": "context-server"}


@app.get("/tenants")
def list_tenants():
    if not TENANTS_ROOT.is_dir():
        return {"tenants": []}
    tenants = sorted(d.name for d in TENANTS_ROOT.iterdir() if d.is_dir())
    return {"tenants": tenants}


@app.post("/tenants")
def create_tenant(body: TenantIn):
    base = _tenant_dir(body.name)
    created = not base.is_dir()
    base.mkdir(parents=True, exist_ok=True)
    return {"ok": True, "tenant": base.name, "created": created}


@app.delete("/tenants/{tenant}")
def delete_tenant(tenant: str):
    base = _tenant_dir(tenant)
    removed = base.is_dir()
    shutil.rmtree(base, ignore_errors=True)
    return {"ok": True, "tenant": base.name, "removed": removed}


@app.get("/tenants/{tenant}/model")
def get_model(tenant: str):
    base = _tenant_dir(tenant)
    if not base.is_dir():
        raise HTTPException(404, f"El tenant '{base.name}' no existe en el servidor de contexto.")
    return _read_model(base)


@app.put("/tenants/{tenant}/model")
def put_model(tenant: str, model: ModelIn):
    base = _tenant_dir(tenant)
    summary = _write_model(base, model)
    return {"ok": True, "tenant": base.name, "summary": summary}


@app.delete("/tenants/{tenant}/model")
def delete_model(tenant: str):
    base = _tenant_dir(tenant)
    if not base.is_dir():
        raise HTTPException(404, f"El tenant '{base.name}' no existe en el servidor de contexto.")
    _clear_model_files(base)
    return {"ok": True, "tenant": base.name}


@app.get("/tenants/{tenant}/context.jsonld")
def get_context(tenant: str):
    """Contexto JSON-LD crudo, apto para usarse como URL de @context."""
    base = _tenant_dir(tenant)
    if not base.is_dir():
        raise HTTPException(404, f"El tenant '{base.name}' no existe en el servidor de contexto.")
    model = _read_model(base)
    if model["context"] is None:
        raise HTTPException(404, f"El tenant '{base.name}' no tiene contexto cargado.")
    return JSONResponse(content=model["context"], media_type="application/ld+json")
