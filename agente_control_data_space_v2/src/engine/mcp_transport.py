# src/engine/mcp_transport.py
# -*- coding: utf-8 -*-
"""
Polyfill de cliente MCP por STDIO.

Fallback para cuando la versión de BasicMCPClient instalada no acepta
`transport_params` (firmas antiguas). Mantiene una ClientSession sobre el
transporte stdio mediante un AsyncExitStack. Parte del MOTOR.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from typing import Optional

from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client

from engine.logging_setup import get_logger

logger = get_logger("mcp.client")


class StdioMCPClient:
    def __init__(self, server_params: StdioServerParameters):
        self.server_params = server_params
        self._session:   Optional[ClientSession] = None
        self._exit_stack = AsyncExitStack()

    async def connect(self):
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(self.server_params)
        )
        read_stream, write_stream = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()
        return self

    async def list_tools(self):
        if not self._session:
            raise RuntimeError("Cliente no conectado.")
        return await self._session.list_tools()

    async def call_tool(self, name: str, arguments: dict):
        if not self._session:
            raise RuntimeError("Cliente no conectado.")
        return await self._session.call_tool(name, arguments)

    async def aclose(self):
        try:
            await self._exit_stack.aclose()
        except Exception as e:
            logger.debug("Cierre StdioMCPClient (ignorado): %s", e)


__all__ = ["StdioMCPClient"]
