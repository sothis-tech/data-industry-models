# src/engine/tool_wrapper.py
# -*- coding: utf-8 -*-
"""
Envoltura de las tools MCP con: conteo por petición, inyección forzosa de
tenant, validación de precondiciones (guardrails) y logging por llamada.

Piezas:
  - ContextVars por petición: contador de tools, contador de errores y el
    contexto de la petición (de donde sale el tenant).
  - extract_tool_text(result): saca el texto real del resultado de una tool
    MCP, sorteando el doble-wrapping de LlamaIndex (ToolOutput → CallToolResult).
  - wrap_tools_with_logging(tools, server): envuelve cada tool.acall para
    contar, inyectar tenant (vía el mapa que el proyecto registró en
    engine.validators), validar precondiciones y loguear.

Parte del MOTOR. El nombre del parámetro de tenant y las reglas de validación
los aporta el proyecto a través de engine.validators (registro). Si el
proyecto no registra nada, no se inyecta tenant ni se rechaza ninguna tool.
"""
from __future__ import annotations

import json
import time
from contextvars import ContextVar
from typing import Optional

from engine.logging_setup import get_logger, log_tool_call
from engine.validators import run_validators, run_normalizers, get_tenant_param

logger = get_logger("mcp.client")


# ─── ContextVars por petición ──────────────────────────────────────────────

_tool_call_counter: ContextVar[int]  = ContextVar("tool_call_counter", default=0)
_tool_call_errors:  ContextVar[int]  = ContextVar("tool_call_errors",  default=0)
_request_context:   ContextVar[dict] = ContextVar("request_context",   default={})
# ─── Salidas de los especialistas por petición (para el render final) ──────
# Ver nota arriba: NO usamos .set() (no cruza las tasks de los sub-agentes,
# por eso el contador marca tools=0 en multi-agente). Usamos UNA lista
# compartida que los hijos mutan con append; reset fija la lista en el
# contexto padre y los hijos heredan la misma referencia.
_specialist_outputs: ContextVar[tuple] = ContextVar("specialist_outputs", default=())


def reset_specialist_outputs() -> None:
    """Fija una lista nueva para la petición (llamar en el contexto padre)."""
    _specialist_outputs.set([])


def record_specialist_output(agent: str, instruction: str, output: str) -> None:
    """Añade (mutación) la salida fiel de un especialista a la petición."""
    try:
        _specialist_outputs.get().append(
            {"agent": agent, "instruction": instruction, "output": output or ""}
        )
    except AttributeError:
        pass  # get() devolvió el default () (no hubo reset): ignorar


def get_specialist_outputs() -> list:
    try:
        return list(_specialist_outputs.get())
    except TypeError:
        return []

def reset_tool_counters() -> None:
    _tool_call_counter.set(0)
    _tool_call_errors.set(0)


def get_tool_counters() -> dict:
    return {
        "tools_called": _tool_call_counter.get(),
        "tools_errors": _tool_call_errors.get(),
    }


def get_tool_call_count() -> int:
    return _tool_call_counter.get()


def set_request_context(context: dict) -> None:
    _request_context.set(context or {})


def get_request_context() -> dict:
    return _request_context.get({})


# ─── Extracción de texto del resultado de una tool ─────────────────────────

def extract_tool_text(result) -> str:
    """
    Extrae el texto real del resultado de una tool MCP.

    `tool.acall()` de LlamaIndex devuelve un ToolOutput que ENVUELVE el
    CallToolResult original de MCP en `result.raw_output`. Hacer
    str(raw_output) da la repr del CallToolResult, con el texto DUPLICADO
    (en .content y .structuredContent) y los '\\n' escapados, lo que rompe
    count("\\nTYPE ") y json.loads().

    Orden de preferencia (en raw_output primero, luego en result):
      1. CallToolResult.structuredContent['result']   (más limpio)
      2. CallToolResult.content[0].text               (TextContent estándar)
      3. ToolOutput.content como str                  (ya formateado)
      4. str(result)                                  (último recurso)
    """
    candidates = []
    raw_output = getattr(result, "raw_output", None)
    if raw_output is not None:
        candidates.append(raw_output)
    candidates.append(result)

    for obj in candidates:
        structured = getattr(obj, "structuredContent", None)
        if isinstance(structured, dict):
            val = structured.get("result")
            if isinstance(val, str):
                return val
            if val is not None:
                return json.dumps(val, ensure_ascii=False, default=str)

        content = getattr(obj, "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            text = getattr(first, "text", None)
            if isinstance(text, str):
                return text

        if isinstance(content, str) and content.strip():
            return content

    return str(result)


# ─── Validación de precondiciones (delegada al proyecto) ───────────────────
# El motor no conoce el dominio. Las reglas (URN canónica, q con operador,
# etc.) viven en el proyecto y se registran en engine.validators. Aquí solo
# se invocan vía run_validators. Sin proyecto, devuelve None y no rechaza nada.

def validate_tool_args(server: str, tool: str, kwargs: dict) -> Optional[str]:
    return run_validators(server, tool, kwargs)


# ─── Envoltura de tools ─────────────────────────────────────────────────────

def wrap_tools_with_logging(tools: list, server_name: str) -> list:
    """
    Envuelve cada tool.acall del servidor `server_name` para:
      1. contar la llamada (ContextVar),
      2. inyectar el tenant forzosamente si el proyecto registró un param
         para este servidor (el LLM nunca decide el tenant),
      3. validar precondiciones; si fallan, rechazar con un error que el LLM
         recibe y debe corregir,
      4. loguear la llamada (ok o error) con duración.
    """
    tenant_param = get_tenant_param(server_name)

    for tool in tools:
        tool_name      = tool.metadata.name
        original_acall = tool.acall

        def _make_acall(name: str, server: str, orig, t_param: Optional[str]):
            async def _logged_acall(*args, **kwargs):
                start     = time.time()
                call_args = {"args": args, "kwargs": kwargs} if args else dict(kwargs)

                _tool_call_counter.set(_tool_call_counter.get() + 1)

                # Override forzoso del tenant: el LLM nunca lo decide.
                if t_param:
                    ctx    = _request_context.get({})
                    tenant = ctx.get("ngsild_tenant") or ctx.get("x_modelador_tenant")
                    if tenant:
                        if t_param in kwargs and kwargs[t_param] != tenant:
                            logger.warning(
                                "Tenant del LLM sobrescrito │ server=%s │ tool=%s │ "
                                "llm='%s' → real='%s'",
                                server, name, kwargs[t_param], tenant,
                            )
                        kwargs[t_param] = tenant
                        logger.debug(
                            "Tenant inyectado │ server=%s │ tool=%s │ %s=%s",
                            server, name, t_param, tenant,
                        )

                # Normalización determinista de argumentos (quita acentos,
                # palabras de relleno de los fragmentos de búsqueda, etc.).
                # La aporta el proyecto; sin normalizadores registrados, no
                # toca nada.
                kwargs = run_normalizers(server, name, kwargs)

                # Validación genérica de precondiciones (guardrails del proyecto).
                precond_error = validate_tool_args(server, name, kwargs)
                if precond_error:
                    logger.warning(
                        "Tool call rechazada por precondición │ server=%s │ "
                        "tool=%s │ %s",
                        server, name, precond_error,
                    )
                    _tool_call_errors.set(_tool_call_errors.get() + 1)
                    log_tool_call(
                        server=server, tool=name,
                        args=call_args,
                        duration_ms=(time.time() - start) * 1000,
                        error=f"PreconditionError: {precond_error}",
                    )
                    # El agent entrega este error al LLM, que debe corregir el
                    # flujo (típicamente pidiendo a Orion el URN canónico).
                    raise ValueError(precond_error)

                try:
                    result = await orig(*args, **kwargs)
                    raw = (
                        getattr(result, "raw_output", None)
                        or getattr(result, "content", None)
                        or str(result)
                    )
                    log_tool_call(
                        server=server, tool=name,
                        args=call_args,
                        result_preview=str(raw),
                        duration_ms=(time.time() - start) * 1000,
                    )
                    raw_str = str(raw)
                    if any(m in raw_str for m in ("❌ HTTP 4", "❌ HTTP 5", "isError=True")):
                        _tool_call_errors.set(_tool_call_errors.get() + 1)
                    return result

                except Exception as e:
                    _tool_call_errors.set(_tool_call_errors.get() + 1)
                    log_tool_call(
                        server=server, tool=name,
                        args=call_args,
                        duration_ms=(time.time() - start) * 1000,
                        error=f"{type(e).__name__}: {e}",
                    )
                    raise

            return _logged_acall

        tool.acall = _make_acall(tool_name, server_name, original_acall, tenant_param)

    return tools


__all__ = [
    "reset_tool_counters", "get_tool_counters", "get_tool_call_count",
    "set_request_context", "get_request_context",
    "extract_tool_text", "validate_tool_args", "wrap_tools_with_logging",
    "get_tenant_param", "reset_specialist_outputs", "record_specialist_output", "get_specialist_outputs",
]
