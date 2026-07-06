# src/engine/token_tracking.py
# -*- coding: utf-8 -*-
"""
Conteo de tokens del LLM por dos vías complementarias:

  1. install_token_interceptor(llm): parchea el cliente OpenAI/Azure (async,
     con fallback sync) para leer `usage` de CADA respuesta y registrarlo en
     el token_tracker global de engine.metrics. Es el conteo directo y exacto
     del proveedor.

  2. install_llamaindex_token_handler(): instala el TokenCountingHandler de
     LlamaIndex como callback global. Este SÍ ve los sub-agentes
     (especialistas), por lo que sirve para reconciliar cuando el interceptor
     directo se queda corto (ver project.behavior_guards.reconcile_token_metrics).

Parte del MOTOR. No conoce el dominio.
"""
from __future__ import annotations

from typing import Any, Optional

from llama_index.core import Settings

from engine.logging_setup import get_logger
from engine.metrics import token_tracker

logger = get_logger("mcp.client")


def _extract_usage_from_response(response) -> None:
    """Lee response.usage y lo registra en el token_tracker global."""
    try:
        usage = getattr(response, "usage", None)
        if usage is not None:
            token_tracker.record(
                prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            )
    except Exception as e:
        logger.debug("Token extraction failed (non-critical): %s", e)


def install_token_interceptor(llm) -> None:
    """
    Parchea el cliente HTTP del LLM para interceptar `usage` en cada llamada.
    Intenta primero el cliente async; si el LLM no lo expone, prueba el sync.
    Idempotente: marca el método create como ya interceptado.
    """
    try:
        original_get_aclient = llm._get_aclient

        def _patched_get_aclient(**kwargs):
            aclient = original_get_aclient(**kwargs)
            if hasattr(aclient.chat.completions, "_token_intercepted"):
                return aclient
            original_create = aclient.chat.completions.create

            async def _intercepted_create(*args, **kwargs):
                response = await original_create(*args, **kwargs)
                _extract_usage_from_response(response)
                return response

            aclient.chat.completions.create = _intercepted_create
            aclient.chat.completions._token_intercepted = True
            return aclient

        llm._get_aclient = _patched_get_aclient
        logger.info("Token interceptor instalado (async client)")

    except AttributeError:
        logger.warning("No se pudo instalar token interceptor async, intentando sync...")
        try:
            original_get_client = llm._get_client

            def _patched_get_client(**kwargs):
                client = original_get_client(**kwargs)
                if hasattr(client.chat.completions, "_token_intercepted"):
                    return client
                original_create = client.chat.completions.create

                def _intercepted_create_sync(*args, **kwargs):
                    response = original_create(*args, **kwargs)
                    _extract_usage_from_response(response)
                    return response

                client.chat.completions.create = _intercepted_create_sync
                client.chat.completions._token_intercepted = True
                return client

            llm._get_client = _patched_get_client
            logger.info("Token interceptor instalado (sync client)")
        except Exception as e2:
            logger.warning("No se pudo instalar token interceptor: %s", e2)


def install_llamaindex_token_handler() -> Optional[Any]:
    """
    Instala el TokenCountingHandler de LlamaIndex como callback global.
    Devuelve el handler (para reconciliar tokens más tarde) o None si no se
    pudo instalar (p.ej. tiktoken ausente).
    """
    try:
        from llama_index.core.callbacks import CallbackManager, TokenCountingHandler
        import tiktoken
        token_counter = TokenCountingHandler(
            tokenizer=tiktoken.encoding_for_model("gpt-4o-mini").encode,
            verbose=False,
        )
        Settings.callback_manager = CallbackManager([token_counter])
        logger.info("LlamaIndex TokenCountingHandler instalado")
        return token_counter
    except ImportError:
        logger.debug("tiktoken no disponible, usando solo interceptor directo")
        return None
    except Exception as e:
        logger.debug("No se pudo instalar TokenCountingHandler: %s", e)
        return None


__all__ = [
    "install_token_interceptor",
    "install_llamaindex_token_handler",
]
