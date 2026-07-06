# src/engine/llm_providers.py
# -*- coding: utf-8 -*-
"""
Construcción del LLM según el proveedor configurado.

Aísla del cliente toda la lógica de "qué LLM instanciar y cómo":
  - Subclases VLLMOpenAI / VLLMAzureOpenAI que fijan metadata correcta
    (context_window, is_function_calling_model) que LlamaIndex necesita.
  - build_llm(agent_config) → (llm, cost_model_name): factory única que lee
    provider (azure | openai | local) y devuelve el LLM listo, además del
    nombre de modelo que se usará para calcular coste.
  - Hotfix de robustez de JSON Schema en el resolver de tipos de MCP.

Es parte del MOTOR: no conoce nada del dominio NGSI-LD.
"""
from __future__ import annotations

import os
from typing import Any, Tuple

from llama_index.core.llms import LLMMetadata

from engine.logging_setup import get_logger

logger = get_logger("mcp.client")

try:
    from llama_index.llms.openai import OpenAI as LlamaOpenAI
    _OPENAI_AVAILABLE = True
except ImportError:
    LlamaOpenAI = object  # type: ignore
    _OPENAI_AVAILABLE = False

try:
    from llama_index.llms.azure_openai import AzureOpenAI as LlamaAzureOpenAI
    _AZURE_AVAILABLE = True
except ImportError:
    LlamaAzureOpenAI = object  # type: ignore
    _AZURE_AVAILABLE = False


# ─── Hotfix: robustez JSON Schema ─────────────────────────────────────────
# Algunos servidores MCP exponen JSON Schemas con campos booleanos o null
# donde el resolver de tipos de LlamaIndex espera un dict. Sin esto, la
# carga de tools peta. Parche idempotente: si el field_schema es bool/None,
# devolvemos Any en vez de explotar.
try:
    from llama_index.tools.mcp.tool_spec_mixins import ToolSpecTypeResolverMixin as _ResolverClass
except Exception:
    _ResolverClass = None

if _ResolverClass is not None and not getattr(_ResolverClass, "_mcp_hotfix_applied", False):
    _orig_resolve = _ResolverClass._resolve_field_type

    def _patched_resolve_field_type(self, field_schema, defs):
        if isinstance(field_schema, (bool, type(None))):
            return Any
        return _orig_resolve(self, field_schema, defs)

    _ResolverClass._resolve_field_type = _patched_resolve_field_type
    _ResolverClass._mcp_hotfix_applied = True


# ─── Subclases LLM ─────────────────────────────────────────────────────────

class VLLMOpenAI(LlamaOpenAI):
    """OpenAI/vLLM con context_window y function-calling forzados en metadata."""
    _context_window: int = 16384

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self._context_window,
            num_output=self.max_tokens or 1024,
            is_chat_model=True,
            is_function_calling_model=True,
            model_name=self.model,
        )


class VLLMAzureOpenAI(LlamaAzureOpenAI):
    """Azure OpenAI con context_window y function-calling forzados en metadata."""
    _context_window: int = 128000

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=self._context_window,
            num_output=self.max_tokens or 1024,
            is_chat_model=True,
            is_function_calling_model=True,
            model_name=self.model,
        )


# ─── Factory ───────────────────────────────────────────────────────────────

def build_llm(agent_config: dict) -> Tuple[Any, str]:
    """
    Construye el LLM a partir de la sección `agent` del config.

    Devuelve (llm, cost_model_name):
      - llm: instancia lista para usar en LlamaIndex Settings/agents.
      - cost_model_name: nombre de modelo para calcular coste (en Azure es el
        deployment; en el resto, el default_model).

    Lee credenciales de variables de entorno con fallback al config.
    """
    provider   = agent_config.get("provider", "local")
    model_name = agent_config.get(
        "default_model", "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4"
    )
    timeout         = float(agent_config.get("request_timeout", 240.0))
    cost_model_name = model_name

    if provider == "azure":
        if not _AZURE_AVAILABLE:
            raise ImportError("Instala llama-index-llms-azure-openai para usar provider=azure")
        azure_endpoint    = os.getenv("AZURE_OPENAI_ENDPOINT")    or agent_config.get("azure_endpoint",    "")
        azure_deployment  = os.getenv("AZURE_OPENAI_DEPLOYMENT")  or agent_config.get("azure_deployment",  "")
        azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION") or agent_config.get("azure_api_version", "2024-10-01-preview")
        azure_api_key     = os.getenv("AZURE_OPENAI_API_KEY")     or agent_config.get("azure_api_key",     "")
        logger.info("Conectando a Azure OpenAI │ deployment=%s │ endpoint=%s",
                    azure_deployment, azure_endpoint)
        llm = VLLMAzureOpenAI(
            model=azure_deployment,
            deployment_name=azure_deployment,
            azure_endpoint=azure_endpoint,
            api_key=azure_api_key,
            api_version=azure_api_version,
            temperature=0.0,
            timeout=timeout,
        )
        llm._context_window = 128000
        cost_model_name = azure_deployment

    elif provider == "openai":
        if not _OPENAI_AVAILABLE:
            raise ImportError("Instala llama-index-llms-openai para usar provider=openai")
        openai_key = os.getenv("OPENAI_API_KEY") or agent_config.get("openai_api_key", "")
        logger.info("Conectando a OpenAI Cloud │ model=%s", model_name)
        llm = LlamaOpenAI(
            model=model_name,
            api_key=openai_key,
            temperature=0.0,
            max_tokens=1024,
            timeout=timeout,
        )

    else:  # local / vLLM
        if not _OPENAI_AVAILABLE:
            raise ImportError("Instala llama-index-llms-openai")
        api_base = os.getenv("VLLM_API_BASE") or agent_config.get("api_base", "http://localhost:8000/v1")
        api_key  = os.getenv("VLLM_API_KEY")  or agent_config.get("api_key",  "vllm-industrial-key")
        logger.info("Conectando a vLLM Local │ model=%s │ api_base=%s", model_name, api_base)
        llm = VLLMOpenAI(
            model=model_name,
            api_base=api_base,
            api_key=api_key,
            temperature=0.0,
            max_tokens=1024,
            timeout=timeout,
            is_function_calling_model=True,
            additional_kwargs={
                "top_p": 0.9,
                "stop": ["<|eot_id|>", "<|end_of_text|>"],
            },
        )
        llm._context_window = 16384

    return llm, cost_model_name


__all__ = [
    "VLLMOpenAI", "VLLMAzureOpenAI", "build_llm",
    "_OPENAI_AVAILABLE", "_AZURE_AVAILABLE",
]
