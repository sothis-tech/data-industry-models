# src/project/tenant_config.py
# -*- coding: utf-8 -*-
"""
Mapa de inyección de tenant por servidor MCP (específico NGSI-LD).

El MECANISMO de forzar el tenant en cada tool call vive en el motor
(engine.tool_wrapper). Pero el NOMBRE del parámetro es de dominio:
  - Orion-LD   usa 'ngsild_tenant'
  - QuantumLeap usa 'fiware_service'  (FIWARE-Service header)
  - RAG        usa 'tenant'

Al importar `project`, este mapa queda registrado en el motor. Si no se
registra, el motor no inyecta tenant (modo básico).
"""
from engine.validators import register_tenant_params

TENANT_PARAM_BY_SERVER = {
    "orion_ld":      "ngsild_tenant",
    "rag_knowledge": "tenant",
    "quantumleap":   "fiware_service",
}

register_tenant_params(TENANT_PARAM_BY_SERVER)
