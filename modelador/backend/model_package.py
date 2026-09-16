"""Carga de paquete de modelo comprimido (.zip / .tar.gz) y persistencia opcional."""
from __future__ import annotations

import io
import json
import tarfile
import zipfile
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile

from context_server_proxy import persist_model_to_context_server, stable_context_url

router = APIRouter(tags=["model-package"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_ZIP_MEMBERS = 200
MAX_MEMBER_BYTES = 10 * 1024 * 1024  # 10 MB por fichero descomprimido


def _safe_member_name(name: str) -> str | None:
    """Devuelve el nombre normalizado o None si contiene path traversal."""
    normalized = name.replace("\\", "/").lstrip("/")
    parts = normalized.split("/")
    if any(p == ".." for p in parts):
        return None
    return normalized


def _extract_zip(content: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        if len(names) > MAX_ZIP_MEMBERS:
            raise HTTPException(400, f"El ZIP supera el límite de {MAX_ZIP_MEMBERS} ficheros")
        for name in names:
            safe = _safe_member_name(name)
            if safe is None:
                continue
            info = zf.getinfo(name)
            if info.file_size > MAX_MEMBER_BYTES:
                continue
            with zf.open(name) as f:
                result[safe] = f.read().decode("utf-8", errors="replace")
    return result


def _extract_tar(content: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(content)) as tf:
        members = [m for m in tf.getmembers() if m.isfile() and not m.issym() and not m.islnk()]
        if len(members) > MAX_ZIP_MEMBERS:
            raise HTTPException(400, f"El TAR supera el límite de {MAX_ZIP_MEMBERS} ficheros")
        for member in members:
            safe = _safe_member_name(member.name)
            if safe is None:
                continue
            if member.size > MAX_MEMBER_BYTES:
                continue
            f = tf.extractfile(member)
            if f:
                result[safe] = f.read().decode("utf-8", errors="replace")
    return result


def _strip_root_folder(members: dict[str, str]) -> dict[str, str]:
    if not members:
        return members
    paths = list(members.keys())
    first_segments = [p.lstrip("/").split("/")[0] for p in paths]
    if len(set(first_segments)) == 1 and all("/" in p.lstrip("/") for p in paths):
        prefix = first_segments[0] + "/"
        return {p[len(prefix) :] if p.startswith(prefix) else p: v for p, v in members.items()}
    return members


def _classify_members(members: dict[str, str]) -> dict[str, Any]:
    schemas: list[Any] = []
    context = None
    descriptor = None
    examples: dict[str, Any] = {}
    unrecognized: list[str] = []

    for path, raw in members.items():
        parts = path.strip("/").split("/")
        if not parts or not parts[-1]:
            continue

        fname = parts[-1].lower()
        folder = parts[0].lower() if len(parts) > 1 else ""

        parsed = None
        if fname.endswith((".json", ".jsonld")):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                unrecognized.append(path)
                continue

        if folder == "schemas" and fname.endswith(".json") and parsed is not None:
            schemas.append(parsed)

        elif folder == "context" and fname.endswith((".jsonld", ".json")) and parsed is not None:
            if context is None:
                context = parsed

        elif fname == "descriptor.json" and parsed is not None:
            if descriptor is None:
                descriptor = parsed

        elif folder == "examples" and fname.endswith(".json") and parsed is not None:
            if len(parts) >= 3:
                example_key = parts[1]
                if example_key not in examples:
                    examples[example_key] = parsed
            else:
                example_key = parts[-1][:-5] if parts[-1].lower().endswith(".json") else parts[-1]
                if example_key not in examples:
                    examples[example_key] = parsed

    return {
        "schemas": schemas,
        "context": context,
        "descriptor": descriptor,
        "examples": examples,
        "unrecognized": unrecognized,
    }


@router.post("/api/upload/model-package")
async def upload_model_package(
    file: UploadFile = File(...),
    tenant: str = "",
    context_url: str = "",
):
    """
    Carga un paquete de modelo comprimido (.zip, .tar.gz, .tgz, .tar).

    Si ?tenant=<tenant>:
      - sin context_url → persiste todo (incluido context del zip) y devuelve URL estable
      - con context_url → persiste schemas/descriptor/examples sin materializar context;
        conserva context previo en disco; contextUrl = la URL externa
    """
    filename = (file.filename or "").lower()
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            detail=f"El archivo supera el límite de {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
        )

    try:
        if filename.endswith(".zip") or content[:2] == b"PK":
            members = _extract_zip(content)
        elif filename.endswith((".tar.gz", ".tgz", ".tar")) or content[:2] in (b"\x1f\x8b", b"us"):
            members = _extract_tar(content)
        else:
            try:
                members = _extract_zip(content)
            except Exception:
                members = _extract_tar(content)
    except Exception as e:
        raise HTTPException(400, detail=f"No se pudo descomprimir el archivo: {e}")

    members = _strip_root_folder(members)
    classified = _classify_members(members)

    if (
        not classified["schemas"]
        and classified["context"] is None
        and classified["descriptor"] is None
    ):
        raise HTTPException(
            422,
            detail=(
                "El paquete no contiene ficheros reconocibles. "
                "Asegúrate de que incluye las carpetas 'schemas/', 'context/' "
                "y/o el fichero 'descriptor.json'."
            ),
        )

    tenant = tenant.strip()
    external_ctx = context_url.strip()
    resolved_context_url: str | None = None

    if tenant:
        if external_ctx:
            # URL gana sobre el context del zip: no se materializa context/ en disco.
            await persist_model_to_context_server(
                tenant,
                {
                    "schemas": classified["schemas"],
                    "context": None,
                    "descriptor": classified["descriptor"],
                    "examples": classified["examples"],
                    "packageName": file.filename,
                    "contextUrl": external_ctx,
                },
            )
            resolved_context_url = external_ctx
        else:
            stable = (
                stable_context_url(tenant) if classified["context"] is not None else None
            )
            await persist_model_to_context_server(
                tenant,
                {
                    "schemas": classified["schemas"],
                    "context": classified["context"],
                    "descriptor": classified["descriptor"],
                    "examples": classified["examples"],
                    "packageName": file.filename,
                    "contextUrl": stable,
                },
            )
            resolved_context_url = stable

    return {
        "ok": True,
        "persisted": bool(tenant),
        "tenant": tenant or None,
        "contextUrl": resolved_context_url,
        "schemas": classified["schemas"],
        "context": classified["context"],
        "descriptor": classified["descriptor"],
        "examples": classified["examples"],
        "summary": {
            "schemas": len(classified["schemas"]),
            "context": classified["context"] is not None,
            "descriptor": classified["descriptor"] is not None,
            "examples": len(classified["examples"]),
            "unrecognized": classified["unrecognized"],
        },
    }
