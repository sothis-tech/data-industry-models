#!/usr/bin/env python3
"""
benchmark.py — Benchmarking MCP Multi-Agente (Data Space Industrial)

Estructura de preguntas:
  - GENÉRICAS: sirven para cualquier tenant/fábrica — el modelo descubre el schema primero
  - IBERMOT-específicas: preguntas con IDs concretos del tenant IBERMOT
  - METAPAN-específicas: preguntas con IDs concretos del tenant METAPAN (añadir según schema)

Uso:
  python benchmark.py --config config.local.yaml --agent orion ql
  python benchmark.py --config config.local.yaml --level 1 2 3 --agent orion ql
  python benchmark.py --config config.local.yaml --tenant ibermot --agent orion ql
  python benchmark.py --config config.local.yaml --model mistral-large-3 --agent orion ql
  python benchmark.py --config config.local.yaml --category ibermot_specific
  python tests/benchmark.py --config config/config.local.yaml --level 1 2 3 --tenant ibermot --agent orion ql
"""

import asyncio
import argparse
import json
import time
import statistics
import sys
import re
import logging
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from engine.client import MCPChatClient
import project  # noqa: F401  → registra guardrails + prompts + behavior en el motor

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False

_XL_MAX = 32700


def _xl(v) -> str:
    s = str(v) if v is not None else ""
    return s if len(s) <= _XL_MAX else s[:_XL_MAX] + "…[truncado]"


# ══════════════════════════════════════════════════════════════════════════════
# CAPTURA DE TRAZAS
# ══════════════════════════════════════════════════════════════════════════════

class TraceCapture(logging.Handler):
    _RE_DELEGATE_REQ = re.compile(r'Gestor\s*[→>]\s*([\w_]+)\s*[│|]\s*(.*)', re.DOTALL)
    _RE_DELEGATE_RES = re.compile(r'([\w_]+)\s*[←<]\s*Gestor\s*[│|]\s*(\d+)ms\s*[│|]\s*(.*)', re.DOTALL)
    _RE_TOOL_CALL    = re.compile(
        r'tool_call_ok\s*[│|]\s*([\w_]+)\.([\w_]+)\s*[│|]\s*([\d.]+)ms\s*[│|]\s*args=(.*?)\s*[│|]\s*result=(.*)',
        re.DOTALL
    )

    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self):
        self._trace: Dict[str, List] = {"delegations": [], "tool_calls": []}

    def get_trace(self):
        return {"delegations": list(self._trace["delegations"]),
                "tool_calls":  list(self._trace["tool_calls"])}

    def get_agents_called(self):
        return list({d["agent"] for d in self._trace["delegations"]})

    def get_tools_called(self):
        return list({f'{t["server"]}.{t["tool"]}' for t in self._trace["tool_calls"]})

    def emit(self, record: logging.LogRecord):
        msg = record.getMessage()
        ts  = record.created
        if record.name == "mcp.agent":
            m = self._RE_DELEGATE_REQ.search(msg)
            if m:
                self._trace["delegations"].append({
                    "direction": "request", "agent": m.group(1).strip(),
                    "instruction": m.group(2).strip(), "timestamp": ts,
                })
                return
            m = self._RE_DELEGATE_RES.search(msg)
            if m:
                self._trace["delegations"].append({
                    "direction": "response", "agent": m.group(1).strip(),
                    "duration_ms": int(m.group(2)), "result_preview": m.group(3).strip(),
                    "timestamp": ts,
                })
                return
        if record.name == "mcp.tools":
            m = self._RE_TOOL_CALL.search(msg)
            if m:
                self._trace["tool_calls"].append({
                    "server": m.group(1).strip(), "tool": m.group(2).strip(),
                    "duration_ms": float(m.group(3)), "args_preview": m.group(4).strip(),
                    "result_preview": m.group(5).strip(), "timestamp": ts,
                })


# ══════════════════════════════════════════════════════════════════════════════
# VALIDADORES AUTOMÁTICOS
# ══════════════════════════════════════════════════════════════════════════════

class AutoValidator:
    FORBIDDEN_PHRASES = [
        "si necesitas más", "espero que", "házmelo saber", "no dudes en",
        "quedo a tu disposición", "estoy aquí para", "cualquier otra pregunta",
        "si tienes alguna", "espero haberte ayudado", "con gusto te ayudo",
    ]

    # Patrón de EVASIÓN: el modelo ofrece/pregunta en vez de actuar. Es el
    # fallo nº1 del benchmark (22/91). Determinista, mismo patrón que el
    # guardarraíl de runtime (chatmcp.core.behavior_guards.is_dodge).
    DODGE_PATTERN = re.compile(
        r"¿\s*(quieres|necesitas|deseas|te gustar|quiere|prefieres|le gustar)"
        r"|por favor,?\s+(indí|indica|especifica|dime|aclar)",
        re.IGNORECASE,
    )

    @staticmethod
    def check_terse(response: str):
        lower = response.lower()
        for phrase in AutoValidator.FORBIDDEN_PHRASES:
            if phrase in lower:
                return False, f"Frase prohibida: '{phrase}'"
        return True, "ok"

    @staticmethod
    def check_no_prefix(response: str):
        if re.match(r'^(assistant|asistente)\s*:', response.strip(), re.IGNORECASE):
            return False, "Prefijo de rol en respuesta"
        return True, "ok"

    @staticmethod
    def check_no_json_pollution(response: str):
        if re.search(r'"speech"\s*:', response) or re.search(r'"text"\s*:', response):
            return False, "JSON interno visible en respuesta"
        return True, "ok"

    @staticmethod
    def check_no_dodge(response: str, tool_calls: List):
        """Falla si el modelo evade: ofrece/pregunta SIN haber llamado tools."""
        if tool_calls:
            return True, "ok"
        if AutoValidator.DODGE_PATTERN.search(response or ""):
            return False, "Evasión: ofrece/pregunta en vez de actuar (tools=0)"
        return True, "ok"

    @staticmethod
    def check_tools_called_for_data(response: str, tool_calls: List):
        has_numbers = bool(re.search(r'\b\d+[.,]\d+\b', response))
        if has_numbers and not tool_calls:
            return False, "Datos numéricos sin tool calls"
        return True, "ok"

    @staticmethod
    def check_routing(expected_agents: List[str], actual_agents: List[str]):
        if not expected_agents:
            return True, "sin restricción"
        missing = set(expected_agents) - set(actual_agents)
        if missing:
            return False, f"Agentes no llamados: {sorted(missing)}"
        return True, f"ok: {sorted(actual_agents)}"

    @staticmethod
    def check_not_empty(response: str):
        if len(response.strip()) < 10:
            return False, f"Respuesta demasiado corta ({len(response.strip())} chars)"
        return True, "ok"

    @classmethod
    def run_all(cls, response, tool_calls, expected_agents, actual_agents):
        checks = [
            ("not_empty",          cls.check_not_empty(response)),
            ("terse_mode",         cls.check_terse(response)),
            ("no_prefix",          cls.check_no_prefix(response)),
            ("no_json_pollution",  cls.check_no_json_pollution(response)),
            ("anti_hallucination", cls.check_tools_called_for_data(response, tool_calls)),
            ("no_dodge",           cls.check_no_dodge(response, tool_calls)),
            ("routing",            cls.check_routing(expected_agents, actual_agents)),
        ]
        results = {}
        passed = 0
        for name, (ok, detail) in checks:
            results[name] = {"passed": ok, "detail": detail}
            if ok:
                passed += 1
        results["_score"] = f"{passed}/{len(checks)}"
        results["_all_passed"] = passed == len(checks)
        return results


# ══════════════════════════════════════════════════════════════════════════════
# BATERÍAS DE PREGUNTAS
# ══════════════════════════════════════════════════════════════════════════════
#
# CONVENCIÓN DE SCOPE:
#   scope="generic"  → válida para cualquier tenant/fábrica (el modelo descubre el schema)
#   scope="ibermot"  → IDs/entidades concretas del tenant IBERMOT
#   scope="metapan"  → IDs/entidades concretas del tenant METAPAN
#
# Las queries genéricas NO hardcodean IDs — preguntan "una máquina", "el sensor más activo",
# "el tipo de entidad con mediciones numéricas", etc. El agente debe descubrir el schema primero.
#
# ══════════════════════════════════════════════════════════════════════════════

TEST_QUERIES = {

    # ── DISCOVERY GENÉRICO ────────────────────────────────────────────────────
    "discovery": {
        "description": "Descubrimiento del modelo de datos — válido para cualquier tenant",
        "complexity": 2,
        "queries": [
            # Nivel 1 — reconocimiento básico (cualquier fábrica)
            {"id": "DISC-001", "scope": "generic",
             "prompt": "¿Qué tipos de entidades existen en este espacio de datos? Dime cuántas hay de cada tipo.",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "explore_data_model + conteos. Debe funcionar con cualquier schema NGSI-LD industrial."},
            {"id": "DISC-002", "scope": "generic",
             "prompt": "¿Cuántas entidades hay en total en este espacio de datos?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "count_entities total."},
            {"id": "DISC-003", "scope": "generic",
             "prompt": "¿Qué tipo de activos industriales o maquinaria hay registrada en el sistema?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "Descubrir ManufacturingMachine o equivalente."},
            {"id": "DISC-004", "scope": "generic",
             "prompt": "¿Qué tipo de sensores o dispositivos están conectados a este sistema?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "Descubrir Device o equivalente."},
            {"id": "DISC-005", "scope": "generic",
             "prompt": "¿Qué magnitudes físicas se están midiendo en la planta? (temperatura, presión, vibración…)",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "controlledProperties del schema."},
            # Nivel 2 — exploración de schema (cualquier fábrica)
            {"id": "DISC-006", "scope": "generic",
             "prompt": "¿Qué tipo de entidad contiene los valores numéricos en tiempo real? Descríbela con sus atributos y unidades.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "VALUE TYPE — DeviceMeasurement o equivalente."},
            {"id": "DISC-007", "scope": "generic",
             "prompt": "¿Qué zonas, naves o áreas productivas están definidas en el sistema?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "BuildingSpace o equivalente."},
            {"id": "DISC-008", "scope": "generic",
             "prompt": "¿Qué modelos o marcas de maquinaria están presentes en la planta?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ManufacturingMachineModel o equivalente."},
            {"id": "DISC-009", "scope": "generic",
             "prompt": "¿Hay personal registrado en el sistema? ¿Qué roles o cargos tienen?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Person o equivalente."},
            {"id": "DISC-010", "scope": "generic",
             "prompt": "¿Qué operaciones de fabricación o producción están registradas actualmente?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ManufacturingMachineOperation o equivalente."},
            # Nivel 3 — navegación de relaciones (cualquier fábrica)
            {"id": "DISC-011", "scope": "generic",
             "prompt": "Elige cualquier máquina de fabricación y explora todas sus relaciones: a qué edificio pertenece, qué modelo es y qué sensores tiene.",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "get_entity + follow all relationships."},
            {"id": "DISC-012", "scope": "generic",
             "prompt": "Encuentra una medición numérica activa y traza su cadena completa: valor → sensor → máquina → nave.",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "DeviceMeasurement → Device → ManufacturingMachine → BuildingSpace."},
            {"id": "DISC-013", "scope": "generic",
             "prompt": "¿Cuántos tipos de máquinas diferentes hay y cuántas unidades de cada tipo?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Agrupar ManufacturingMachine por tipo o modelo."},
            {"id": "DISC-014", "scope": "generic",
             "prompt": "¿Qué máquinas están actualmente en línea (online) y cuáles están offline?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "filter online attribute."},
            {"id": "DISC-015", "scope": "generic",
             "prompt": "Lista todos los identificadores de máquinas disponibles en el sistema.",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "resolve_entity_ids o list_entities ManufacturingMachine."},
        ],
    },

    # ── CURRENT STATE GENÉRICO ────────────────────────────────────────────────
    "current_state": {
        "description": "Estado actual — preguntas genéricas válidas para cualquier tenant",
        "complexity": 2,
        "queries": [
            # Nivel 1 — valores directos descubriendo entidades
            {"id": "CURR-001", "scope": "generic",
             "prompt": "Busca cualquier entidad con mediciones numéricas y dime su valor actual, unidad y cuándo se midió.",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "Descubrir VALUE TYPE + leer numValue."},
            {"id": "CURR-002", "scope": "generic",
             "prompt": "¿Cuál es la temperatura actual de alguna máquina o sensor de temperatura en el sistema?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "Buscar controlledProperty=temperature."},
            {"id": "CURR-003", "scope": "generic",
             "prompt": "¿Qué presiones están siendo monitorizadas ahora mismo en la planta?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "controlledProperty=pressure."},
            {"id": "CURR-004", "scope": "generic",
             "prompt": "¿Hay algún vehículo de transporte automatizado (AGV, robot móvil…)? Si los hay, dime su estado actual.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Buscar AGV o vehículo autónomo + batería/velocidad."},
            {"id": "CURR-005", "scope": "generic",
             "prompt": "¿Cuál es el estado de producción actual? ¿Qué máquinas están activas?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ManufacturingMachine online + ManufacturingMachineOperation status."},
            {"id": "CURR-006", "scope": "generic",
             "prompt": "Dame los valores actuales de vibración de cualquier máquina que tenga ese sensor.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "controlledProperty=vibration."},
            {"id": "CURR-007", "scope": "generic",
             "prompt": "¿Qué máquina tiene el valor de temperatura más alto en este momento?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Comparar todas las temp readings."},
            {"id": "CURR-008", "scope": "generic",
             "prompt": "¿Hay sensores de energía o potencia eléctrica? ¿Cuánto consume la planta ahora?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "controlledProperty=power o electricCurrent."},
            {"id": "CURR-009", "scope": "generic",
             "prompt": "¿Cuántas operaciones de fabricación están en curso ahora mismo?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ManufacturingMachineOperation filter status=running/in-progress."},
            {"id": "CURR-010", "scope": "generic",
             "prompt": "Dame un resumen rápido del estado general de la planta: máquinas online, sensores activos y alertas visibles.",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Vista global multi-entidad."},
            # Nivel 3 — análisis sobre el estado actual
            {"id": "CURR-011", "scope": "generic",
             "prompt": "¿Algún sensor muestra un valor que podría ser anómalo o fuera de rango típico?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Comparar numValue vs minValue/maxValue del schema."},
            {"id": "CURR-012", "scope": "generic",
             "prompt": "¿Cuál es la máquina con más sensores asociados?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Contar Device por controlledAsset."},
            {"id": "CURR-013", "scope": "generic",
             "prompt": "¿Qué área de la planta tiene más actividad de medición en este momento?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Agrupar DeviceMeasurement por BuildingSpace."},
        ],
    },

    # ── HISTORICAL GENÉRICO ───────────────────────────────────────────────────
    "historical": {
        "description": "Consultas históricas — genéricas para cualquier tenant",
        "complexity": 4,
        "queries": [
            # Nivel 2
            {"id": "HIST-001", "scope": "generic",
             "prompt": "¿Hay datos históricos en QuantumLeap? ¿Qué tipos de entidades tienen histórico disponible?",
             "expected_agents": ["quantumleap"], "difficulty": 2,
             "notes": "ql_list_entity_types."},
            {"id": "HIST-002", "scope": "generic",
             "prompt": "Encuentra cualquier máquina con sensores y dame el último valor registrado en QuantumLeap de su sensor principal.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 2,
             "notes": "Orion para entity_id → QL last_value."},
            {"id": "HIST-003", "scope": "generic",
             "prompt": "¿Cuándo fue la última vez que se registró un dato de temperatura en el sistema histórico?",
             "expected_agents": ["quantumleap"], "difficulty": 2,
             "notes": "QL last timestamp para temperature."},
            {"id": "HIST-004", "scope": "generic",
             "prompt": "Dame la media de temperatura de cualquier máquina disponible en las últimas 24 horas.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 3,
             "notes": "aggr avg last_day temperatura."},
            {"id": "HIST-005", "scope": "generic",
             "prompt": "¿Cuál fue el valor máximo de presión registrado en el sistema durante la última semana?",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 3,
             "notes": "aggr max last_week presión."},
            {"id": "HIST-006", "scope": "generic",
             "prompt": "Dame la evolución horaria de temperatura de la máquina con más datos históricos en los últimos 3 días.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Descubrir entidad más activa + aggr_period hour."},
            {"id": "HIST-007", "scope": "generic",
             "prompt": "Compara la actividad de dos máquinas similares en la última semana usando sus datos históricos.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Dos entidades del mismo tipo, métricas comparadas."},
            {"id": "HIST-008", "scope": "generic",
             "prompt": "¿Hay tendencia de aumento o disminución en algún parámetro crítico en los últimos 7 días?",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Serie temporal, analizar tendencia."},
            {"id": "HIST-009", "scope": "generic",
             "prompt": "Para la entidad con más datos históricos, calcula la media del último día. Si no hay datos del último día, amplía el rango.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Descubrir entidad + aggr avg adaptativo."},
            # Nivel 5
            {"id": "HIST-010", "scope": "generic",
             "prompt": "Diagnostica si el flujo de datos entre Orion y QuantumLeap funciona correctamente. Verifica suscripciones si es necesario.",
             "expected_agents": ["quantumleap", "orion_ld"], "difficulty": 5,
             "notes": "ql_get_entity_history + list_subscriptions."},
        ],
    },

    # ── EDGE CASES GENÉRICOS ──────────────────────────────────────────────────
    "edge_cases": {
        "description": "Casos límite — ambigüedad, preguntas incompletas, inferencia",
        "complexity": 3,
        "queries": [
            {"id": "EDGE-001", "scope": "generic",
             "prompt": "¿Cómo está la máquina?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Ambiguo sin ID — debe pedir aclaración o listar opciones."},
            {"id": "EDGE-002", "scope": "generic",
             "prompt": "Estado del sensor.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Ambiguo — debe resolver o preguntar cuál."},
            {"id": "EDGE-003", "scope": "generic",
             "prompt": "¿Hay alguna alarma activa en la planta?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "No hay entidad alarma — inferir de valores fuera de rango."},
            {"id": "EDGE-004", "scope": "generic",
             "prompt": "¿Algún vehículo autónomo necesita atención?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Inferir batería baja o estado offline."},
            {"id": "EDGE-005", "scope": "generic",
             "prompt": "¿La producción va bien hoy?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Pregunta vaga — debe interpretar estado general."},
            {"id": "EDGE-006", "scope": "generic",
             "prompt": "Dame información sobre la máquina número 5.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ID incompleto — debe resolver qué máquina es el número 5."},
            {"id": "EDGE-007", "scope": "generic",
             "prompt": "¿Qué pasó ayer en la planta?",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Consulta temporal vaga — last_day en QL + operaciones."},
            {"id": "EDGE-008", "scope": "generic",
             "prompt": "¿Qué máquinas llevan más tiempo encendidas?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "online + timestamps installedAt o últimas operaciones."},
            {"id": "EDGE-009", "scope": "generic",
             "prompt": "¿Todo está funcionando correctamente?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Vista global: online, valores, operaciones."},
            {"id": "EDGE-010", "scope": "generic",
             "prompt": "Temperatura.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Pregunta de una sola palabra — debe buscar y devolver algo útil."},
        ],
    },

    # ── MULTI-AGENT GENÉRICO ──────────────────────────────────────────────────
    "multi_agent": {
        "description": "Consultas multi-agente — genéricas, coordinan Orion + QuantumLeap",
        "complexity": 4,
        "queries": [
            {"id": "MULTI-001", "scope": "generic",
             "prompt": "¿Alguna máquina está funcionando fuera de sus parámetros normales? Comprueba los valores actuales y el histórico reciente.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Valor actual Orion + contexto histórico QL."},
            {"id": "MULTI-002", "scope": "generic",
             "prompt": "Dame un resumen ejecutivo del estado del sistema: qué hay en Orion y qué histórico hay en QuantumLeap.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 5,
             "notes": "Exploración completa ambos sistemas."},
            {"id": "MULTI-003", "scope": "generic",
             "prompt": "¿Las máquinas están rindiendo igual que la semana pasada? Compara el estado actual con el histórico.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Actual vs avg last_week métricas clave."},
            {"id": "MULTI-004", "scope": "generic",
             "prompt": "Genera un informe de mantenimiento predictivo: valores actuales, tendencia histórica y cualquier señal de alerta.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 5,
             "notes": "Multi-sensor current + QL trends + interpretación."},
            {"id": "MULTI-005", "scope": "generic",
             "prompt": "Detecta cualquier anomalía posible comparando los valores actuales con los históricos de la última semana.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 5,
             "notes": "Multisensor actual vs avg histórico, detectar desviaciones."},
        ],
    },

    # ── RAG GENÉRICO ──────────────────────────────────────────────────────────
    "rag": {
        "description": "Documentación técnica — genérico",
        "complexity": 2,
        "queries": [
            {"id": "RAG-001", "scope": "generic",
             "prompt": "¿Qué documentos técnicos hay disponibles en la base de conocimiento?",
             "expected_agents": ["rag_knowledge"], "difficulty": 1,
             "notes": "listar_documentos_vectorizados."},
            {"id": "RAG-002", "scope": "generic",
             "prompt": "Busca procedimientos de mantenimiento preventivo en la documentación disponible.",
             "expected_agents": ["rag_knowledge"], "difficulty": 2,
             "notes": "consultar_base_conocimiento — mantenimiento."},
            {"id": "RAG-003", "scope": "generic",
             "prompt": "¿Hay códigos de error o tablas de alarmas documentadas?",
             "expected_agents": ["rag_knowledge"], "difficulty": 2,
             "notes": "consultar_base_conocimiento — códigos error."},
            {"id": "RAG-004", "scope": "generic",
             "prompt": "¿Qué procedimientos de seguridad están documentados para trabajos de mantenimiento?",
             "expected_agents": ["rag_knowledge"], "difficulty": 2,
             "notes": "consultar_base_conocimiento — seguridad."},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PREGUNTAS ESPECÍFICAS — IBERMOT
    # IDs reales del tenant IBERMOT: prensas, robots, AGVs, etc.
    # ══════════════════════════════════════════════════════════════════════════
    "ibermot_specific": {
        "description": "Preguntas específicas con IDs reales del tenant IBERMOT",
        "complexity": 3,
        "queries": [
            # Nivel 1 — valores directos IBERMOT
            {"id": "IB-001", "scope": "ibermot",
             "prompt": "¿Cuál es la temperatura actual del aceite de la prensa 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "prensa-001-temp-aceite-meas."},
            {"id": "IB-002", "scope": "ibermot",
             "prompt": "¿Cuál es la presión hidráulica actual de la prensa 002?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "prensa-002-presion-hid-meas."},
            {"id": "IB-003", "scope": "ibermot",
             "prompt": "¿Cuántos golpes ha dado la prensa 001 hasta ahora?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "prensa-001-contador-golpes-meas."},
            {"id": "IB-004", "scope": "ibermot",
             "prompt": "¿Cuál es el nivel de batería actual del AGV carrocería 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "agv-carroceria-001-bateria-meas."},
            {"id": "IB-005", "scope": "ibermot",
             "prompt": "¿A qué velocidad se mueve ahora mismo el AGV montaje 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "agv-montaje-001-velocidad-meas."},
            {"id": "IB-006", "scope": "ibermot",
             "prompt": "¿Cuál es la corriente eléctrica del robot de soldadura 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "robot-soldadura-001-corriente-meas."},
            {"id": "IB-007", "scope": "ibermot",
             "prompt": "¿Cuántas soldaduras ha realizado el robot soldadura 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "robot-soldadura-001-contador-sold-meas."},
            {"id": "IB-008", "scope": "ibermot",
             "prompt": "¿Cuál es la fuerza que está ejerciendo la prensa 001 ahora mismo?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "prensa-001-fuerza-meas."},
            {"id": "IB-009", "scope": "ibermot",
             "prompt": "¿Cuál es la velocidad de la ram de la prensa 001?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "prensa-001-velocidad-ram-meas."},
            {"id": "IB-010", "scope": "ibermot",
             "prompt": "¿Cuánta carga lleva ahora el AGV carrocería 002?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "agv-carroceria-002-carga-meas."},
            # Nivel 2 — estado de máquinas IBERMOT
            {"id": "IB-011", "scope": "ibermot",
             "prompt": "Dame el estado completo de la prensa 002: temperatura, presión, fuerza y vibración actuales.",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Múltiples DeviceMeasurement prensa-002."},
            {"id": "IB-012", "scope": "ibermot",
             "prompt": "¿Cuántos AGVs hay disponibles en IBERMOT y cuál es su nivel de batería?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "6 AGVs (carroceria 001-002, motores 001, montaje 001-003)."},
            {"id": "IB-013", "scope": "ibermot",
             "prompt": "¿Está online la prensa 001? ¿Y la prensa 002?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "ManufacturingMachine.online."},
            {"id": "IB-014", "scope": "ibermot",
             "prompt": "¿Cuántos robots de soldadura hay en la planta de IBERMOT?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "resolve robot-soldadura → 6 robots."},
            {"id": "IB-015", "scope": "ibermot",
             "prompt": "¿Qué temperatura tiene el motor del robot soldadura 001 en este momento?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "robot-soldadura-001-temp-motor-meas."},
            {"id": "IB-016", "scope": "ibermot",
             "prompt": "¿Cuál es la diferencia de temperatura de aceite entre la prensa 001 y la prensa 002?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "Dos mediciones, calcular diferencia."},
            {"id": "IB-017", "scope": "ibermot",
             "prompt": "¿Qué máquinas están en la nave de carrocería y cuál es su estado?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "BuildingSpace nave-carroceria → ManufacturingMachine."},
            {"id": "IB-018", "scope": "ibermot",
             "prompt": "¿Cuál es el recuento de soldaduras de todos los robots de soldadura de IBERMOT?",
             "expected_agents": ["orion_ld"], "difficulty": 3,
             "notes": "6 robots × contador-sold-meas."},
            {"id": "IB-019", "scope": "ibermot",
             "prompt": "¿Quién es el director de planta de IBERMOT y cuál es su extensión telefónica?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "Person director-planta."},
            {"id": "IB-020", "scope": "ibermot",
             "prompt": "¿Qué operaciones están registradas en IBERMOT y cuál es su estado?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "list_entities ManufacturingMachineOperation."},
            # Nivel 3 — histórico IBERMOT
            {"id": "IB-021", "scope": "ibermot",
             "prompt": "¿Cuál fue la temperatura media de aceite de la prensa 001 en la última semana?",
             "expected_agents": ["quantumleap"], "difficulty": 3,
             "notes": "QL aggr avg last_week prensa-001-temp-aceite."},
            {"id": "IB-022", "scope": "ibermot",
             "prompt": "¿Cuál fue la presión máxima de la prensa 002 en los últimos 7 días?",
             "expected_agents": ["quantumleap"], "difficulty": 3,
             "notes": "QL aggr max last_week prensa-002-presion-hid."},
            {"id": "IB-023", "scope": "ibermot",
             "prompt": "¿Cuál fue la media de batería del AGV carrocería 002 la última semana?",
             "expected_agents": ["quantumleap"], "difficulty": 3,
             "notes": "QL aggr avg last_week agv-carroceria-002-bateria."},
            {"id": "IB-024", "scope": "ibermot",
             "prompt": "¿Cuántos golpes en total ha dado la prensa 001 en el último mes?",
             "expected_agents": ["quantumleap"], "difficulty": 3,
             "notes": "QL aggr sum last_month contador-golpes."},
            {"id": "IB-025", "scope": "ibermot",
             "prompt": "Compara la temperatura media de aceite de la prensa 001 y la prensa 002 en la última semana.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Dos series QL, comparar."},
            {"id": "IB-026", "scope": "ibermot",
             "prompt": "¿Cuál de los dos AGVs de carrocería consume más batería en promedio? Compara la última semana.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "agv-carroceria-001 vs 002."},
            {"id": "IB-027", "scope": "ibermot",
             "prompt": "¿Qué robot de soldadura ha registrado mayor temperatura de motor en la última semana?",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "6 robots, max temp-motor last_week."},
            {"id": "IB-028", "scope": "ibermot",
             "prompt": "Genera un informe de actividad de los robots de soldadura (1 al 6) en la última semana: soldaduras totales, temperatura media y corriente media.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 5,
             "notes": "6 robots × 3 métricas × last_week."},
            {"id": "IB-029", "scope": "ibermot",
             "prompt": "¿Hay tendencia de aumento en la vibración de la prensa 001 en los últimos 7 días?",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Serie temporal vibración, analizar tendencia."},
            {"id": "IB-030", "scope": "ibermot",
             "prompt": "Dame un resumen del estado actual de la nave de estampación: prensas activas, golpes actuales y media histórica de la semana.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 4,
             "notes": "Prensas + golpes actuales + QL histórico."},
        ],
    },

    # ══════════════════════════════════════════════════════════════════════════
    # PREGUNTAS ESPECÍFICAS — METAPAN
    # Placeholder — completar cuando se conozca el schema de METAPAN
    # ══════════════════════════════════════════════════════════════════════════
    "metapan_specific": {
        "description": "Preguntas específicas del tenant METAPAN — completar según schema",
        "complexity": 2,
        "queries": [
            # Estas preguntas son genéricas hasta conocer el schema de METAPAN
            # Una vez conocido el schema, añadir preguntas con IDs concretos
            # igual que se hizo con IBERMOT arriba.
            {"id": "MP-001", "scope": "metapan",
             "prompt": "¿Qué tipos de entidades existen en el espacio de datos de METAPAN?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "Descubrimiento inicial schema METAPAN."},
            {"id": "MP-002", "scope": "metapan",
             "prompt": "¿Cuántas máquinas hay en METAPAN y de qué tipos?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "count_entities por tipo."},
            {"id": "MP-003", "scope": "metapan",
             "prompt": "¿Qué magnitudes físicas se están midiendo en la planta de METAPAN?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "controlledProperties del schema METAPAN."},
            {"id": "MP-004", "scope": "metapan",
             "prompt": "Lista todas las máquinas de fabricación disponibles en METAPAN.",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "resolve_entity_ids ManufacturingMachine METAPAN."},
            {"id": "MP-005", "scope": "metapan",
             "prompt": "¿Cuál es el valor actual del sensor con medición más reciente en METAPAN?",
             "expected_agents": ["orion_ld"], "difficulty": 2,
             "notes": "VALUE TYPE más reciente."},
            {"id": "MP-006", "scope": "metapan",
             "prompt": "¿Hay datos históricos en QuantumLeap para las entidades de METAPAN?",
             "expected_agents": ["quantumleap"], "difficulty": 2,
             "notes": "ql_list_entity_types tenant metapan."},
            {"id": "MP-007", "scope": "metapan",
             "prompt": "Dame la media de temperatura de cualquier máquina de METAPAN en la última semana.",
             "expected_agents": ["orion_ld", "quantumleap"], "difficulty": 3,
             "notes": "Descubrir entidad + aggr avg last_week."},
            {"id": "MP-008", "scope": "metapan",
             "prompt": "¿Qué zonas o áreas productivas existen en METAPAN?",
             "expected_agents": ["orion_ld"], "difficulty": 1,
             "notes": "BuildingSpace o equivalente tenant METAPAN."},
            # ── Añadir aquí preguntas concretas cuando se conozca el schema ──
            # {"id": "MP-009", "scope": "metapan",
            #  "prompt": "¿Cuál es la temperatura actual de la máquina X de METAPAN?",
            #  "expected_agents": ["orion_ld"], "difficulty": 1,
            #  "notes": "ID real METAPAN."},
        ],
    },
}

# RAG-TEST se mantiene separado ya que son 60 preguntas sobre documentos específicos
RAG_TEST_QUERIES = {
    "rag-test": {
        "description": "60 preguntas sobre 4 documentos de prueba (15 por documento)",
        "complexity": 3,
        "queries": [
            {"id": "HPX-001", "scope": "generic", "prompt": "¿Cuál es la presión máxima admisible de la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["280", "bar"], "difficulty": 1, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-002", "scope": "generic", "prompt": "¿Con qué frecuencia hay que cambiar el aceite hidráulico de la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["2000 horas", "12 meses"], "difficulty": 1, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-003", "scope": "generic", "prompt": "¿Qué significa el código de error E-02 en la bomba hidráulica?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["temperatura", "aceite"], "difficulty": 1, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-004", "scope": "generic", "prompt": "¿Qué viscosidad de aceite recomienda el fabricante para la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["VG 46", "ISO"], "difficulty": 1, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-005", "scope": "generic", "prompt": "¿Cuál es el caudal nominal de la bomba HPX-200 a 1450 rpm?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["45", "litros"], "difficulty": 1, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-006", "scope": "generic", "prompt": "¿Cada cuántas horas de operación hay que limpiar el filtro de aspiración de la bomba?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["50", "horas"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-007", "scope": "generic", "prompt": "¿Qué EPIs son obligatorios según el manual cuando se interviene en la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["guantes", "gafas"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-008", "scope": "generic", "prompt": "¿Con qué par de apriete deben fijarse los tornillos del conjunto motobomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["45", "N·m"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-009", "scope": "generic", "prompt": "¿Cuánto aceite tiene el depósito de la bomba HPX-200 y qué tipo se usa para el cambio anual?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["80 litros", "VG 46", "HLP"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-010", "scope": "generic", "prompt": "¿Cuándo debe enviarse la bomba HPX-200 al servicio técnico oficial para inspección?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["5000 horas", "24 meses"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-011", "scope": "generic", "prompt": "¿Qué temperatura del aceite se considera normal durante la operación de la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["40", "65"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-012", "scope": "generic", "prompt": "¿Qué tipo de análisis se recomienda hacer mensualmente al aceite de la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["muestra", "contaminación", "laboratorio"], "difficulty": 3, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-013", "scope": "generic", "prompt": "¿Cuál es el consumo de corriente nominal del motor eléctrico que acciona la bomba HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["7.2", "A", "400 V"], "difficulty": 2, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-014", "scope": "generic", "prompt": "¿Qué referencia tiene el filtro de retorno que hay que cambiar mensualmente en la HPX-200?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["HT-FLT-RET-10"], "difficulty": 3, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "HPX-015", "scope": "generic", "prompt": "¿Qué pasa con la garantía de la bomba HPX-200 si no se realiza la inspección periódica?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["garantía", "anula"], "difficulty": 3, "doc": "Manual_Bomba_Hidraulica_HPX200.pdf"},
            {"id": "MQTT-001", "scope": "generic", "prompt": "¿En qué puerto se debe conectar el broker MQTT en entornos de producción?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["8883", "TLS"], "difficulty": 1, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-002", "scope": "generic", "prompt": "¿Cuál es el tamaño máximo de mensaje permitido en el broker MQTT de la guía?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["256", "KB"], "difficulty": 1, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-003", "scope": "generic", "prompt": "Explica cuándo se debe usar QoS 2 en MQTT y qué garantiza.", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["exactamente", "alarmas", "críticas"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-004", "scope": "generic", "prompt": "¿Cuál es la estructura estándar de los topics MQTT en la planta industrial?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["fabrica", "planta", "dispositivo"], "difficulty": 1, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-005", "scope": "generic", "prompt": "¿Cuánto tiempo tiene un cliente MQTT para enviar un PINGREQ antes de que expire la conexión?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["60", "segundos"], "difficulty": 1, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-006", "scope": "generic", "prompt": "¿Qué versión del broker Mosquitto se utiliza según la guía de red industrial?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["2.0", "Mosquitto"], "difficulty": 1, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-007", "scope": "generic", "prompt": "¿Cuál es la estrategia de reconexión recomendada para clientes MQTT en caso de corte de red?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["exponencial"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-008", "scope": "generic", "prompt": "¿Qué permisos tiene el usuario 'dashboard_readonly' en el sistema ACL MQTT?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["lectura", "read"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-009", "scope": "generic", "prompt": "¿Para qué se usan los mensajes retenidos (retained) en MQTT y cuándo NO se deben usar?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["estado", "alarmas"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-010", "scope": "generic", "prompt": "¿Cuántos mensajes en cola como máximo puede tener cada cliente MQTT antes de que se descarten?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["1000"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-011", "scope": "generic", "prompt": "¿Qué significa un código CONNACK 5 y cómo se soluciona según la guía?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["credenciales", "passwd"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-012", "scope": "generic", "prompt": "¿Cuántos clientes conectados simultáneos se consideran en la zona de alerta del broker MQTT?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["400"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-013", "scope": "generic", "prompt": "¿Cuándo caducan los certificados de cliente en el sistema de autenticación X.509?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["365", "días"], "difficulty": 2, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-014", "scope": "generic", "prompt": "¿Cuántos mensajes por segundo se consideran una situación de alerta en el broker MQTT industrial?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["10000"], "difficulty": 3, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "MQTT-015", "scope": "generic", "prompt": "¿En qué versión de la guía de red MQTT se añadió soporte para MQTT 5.0?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["2.4"], "difficulty": 3, "doc": "Guia_Red_Industrial_MQTT.md"},
            {"id": "SP5-001", "scope": "generic", "prompt": "¿Cuál es el rango de medición del sensor de presión SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["500", "bar"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-002", "scope": "generic", "prompt": "¿Cuál es la señal de salida estándar recomendada del sensor SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["4-20", "mA"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-003", "scope": "generic", "prompt": "¿Cuál es el grado de protección IP del sensor de presión SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["IP67"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-004", "scope": "generic", "prompt": "¿Qué tipo de conector eléctrico usa el sensor SP-500 y cómo están asignados los pines?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["M12", "4"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-005", "scope": "generic", "prompt": "¿Cuál es la precisión del sensor SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["0,25", "FS"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-006", "scope": "generic", "prompt": "¿Cuánto tiempo tarda en responder el sensor SP-500 a un cambio de presión?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["5", "ms"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-007", "scope": "generic", "prompt": "¿Cada cuánto tiempo debe calibrarse el sensor SP-500 en condiciones normales?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["12", "meses"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-008", "scope": "generic", "prompt": "¿Qué significa si el LED del sensor SP-500 está rojo y parpadeando?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["sobrepresión", "525"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-009", "scope": "generic", "prompt": "¿Cuál es la tensión de alimentación mínima y máxima del sensor SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["12", "36", "VDC"], "difficulty": 1, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-010", "scope": "generic", "prompt": "¿Qué materiales están en contacto con el proceso en el sensor SP-500 y qué fluidos NO son admisibles?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["316L", "AISI"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-011", "scope": "generic", "prompt": "¿Cuántos ciclos de presión garantiza el fabricante del sensor SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["10 millones"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-012", "scope": "generic", "prompt": "¿Cuál es el par de apriete máximo al instalar el sensor SP-500 para no dañar la membrana?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["30", "N·m"], "difficulty": 3, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-013", "scope": "generic", "prompt": "¿Qué opciones de junta de proceso están disponibles para el sensor SP-500?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["FKM", "EPDM", "PTFE"], "difficulty": 3, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-014", "scope": "generic", "prompt": "¿Cuál es el código de pedido del sensor SP-500 con salida 4-20 mA, conexión G1/2 y junta FKM?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["ST-SP500-4-20-G12-FKM"], "difficulty": 3, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SP5-015", "scope": "generic", "prompt": "¿Qué ocurre con la salida 4-20 mA del sensor SP-500 si hay un fallo o circuito abierto?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["3,6", "mA"], "difficulty": 2, "doc": "Especificaciones_Sensor_Presion_SP500.txt"},
            {"id": "SEG-001", "scope": "generic", "prompt": "¿Qué pasos hay que seguir en caso de parada de emergencia en la planta industrial?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["pulsador", "evacuar", "notificar"], "difficulty": 1, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-002", "scope": "generic", "prompt": "¿Qué EPIs son obligatorios en toda la planta de producción?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["casco", "gafas", "calzado"], "difficulty": 1, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-003", "scope": "generic", "prompt": "¿Cuáles son los puntos de encuentro de evacuación disponibles en la planta?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["norte", "sur"], "difficulty": 1, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-004", "scope": "generic", "prompt": "¿Qué es el procedimiento LOTO y cuándo es obligatorio aplicarlo?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["Lockout", "Tagout", "energía"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-005", "scope": "generic", "prompt": "¿Cuánto tiempo máximo hay para notificar un incidente en la planta y qué formulario se usa?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["24 horas", "SI-001"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-006", "scope": "generic", "prompt": "¿Qué tipo de extintor se debe usar para un incendio en un cuadro eléctrico?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["CO2"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-007", "scope": "generic", "prompt": "¿Cuál es el número de extensión del Responsable de Seguridad (PRL) en la planta?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["100"], "difficulty": 1, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-008", "scope": "generic", "prompt": "¿Qué permiso de trabajo hay que tramitar para realizar trabajos de soldadura?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["PT-03"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-009", "scope": "generic", "prompt": "¿Qué protocolo hay que seguir ante un derrame de producto químico superior a 5 litros?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["evacuar", "10 metros", "alarma"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-010", "scope": "generic", "prompt": "¿Con qué frecuencia se realizan los simulacros de evacuación en la planta?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["semestral"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-011", "scope": "generic", "prompt": "¿Cuántos pasos tiene el procedimiento LOTO y qué se verifica en el último paso?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["8", "energía"], "difficulty": 3, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-012", "scope": "generic", "prompt": "¿Quién debe autorizar los trabajos eléctricos en instalaciones de alta tensión (> 1000V)?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["dirección", "responsable eléctrico"], "difficulty": 3, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-013", "scope": "generic", "prompt": "¿Con qué protección auditiva deben equiparse los trabajadores en zonas con más de 85 dB?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["SNR", "28"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-014", "scope": "generic", "prompt": "¿Cada cuánto tiempo se hace la inspección semanal de zona de trabajo y quién es el responsable?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["lunes", "jefe de equipo"], "difficulty": 2, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
            {"id": "SEG-015", "scope": "generic", "prompt": "¿Cuánta capacidad tiene el punto de encuentro de evacuación principal (punto A)?", "expected_agents": ["rag_knowledge"], "expected_answer_contains": ["350"], "difficulty": 3, "doc": "Procedimientos_Seguridad_Planta_Industrial.docx"},
        ],
    },
}

ALL_CATEGORIES = {**TEST_QUERIES, **RAG_TEST_QUERIES}

_AGENT_NAME_MAP = {
    "orion": "orion_ld", "orion_ld": "orion_ld",
    "ql": "quantumleap", "quantumleap": "quantumleap",
    "rag": "rag_knowledge", "rag_knowledge": "rag_knowledge",
}

# Scopes que se excluyen según el tenant activo
_SCOPE_EXCLUDE = {
    "ibermot": {"metapan"},
    "metapan": {"ibermot"},
    "generic": {"ibermot", "metapan"},  # solo genéricas
}


# ══════════════════════════════════════════════════════════════════════════════
# CLASE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class DataSpaceBenchmark:

    def __init__(self, categories=None, queries_per_category=10, config_path="config/config.local.yaml",
                 levels=None, agents=None, max_queries=None, model_label=None,
                 tenant=None, scope_filter=None):
        self.categories           = categories
        self.queries_per_category = queries_per_category
        self.config_path          = config_path
        self.levels               = set(levels) if levels else None
        self.agents               = [a.lower() for a in agents] if agents else None
        self.max_queries          = max_queries
        self.model_label          = model_label or "default"
        self.tenant               = tenant        # ibermot | metapan | None
        self.scope_filter         = scope_filter  # generic | ibermot | metapan | all | None
        self.results: List[Dict]  = []
        self.client: Optional[MCPChatClient] = None
        self.tracer = TraceCapture()
        self.tracer.setLevel(logging.DEBUG)
        for lg_name in ("mcp.agent", "mcp.tools"):
            lg = logging.getLogger(lg_name)
            lg.addHandler(self.tracer)
            lg.setLevel(logging.DEBUG)

    def _scope_ok(self, q: Dict) -> bool:
        """Devuelve True si la query pasa el filtro de scope."""
        q_scope = q.get("scope", "generic")
        sf = self.scope_filter
        if sf and sf != "all":
            return q_scope == sf or q_scope == "generic"
        # Sin scope_filter: excluir el tenant contrario
        if self.tenant and self.tenant in _SCOPE_EXCLUDE:
            excluded = _SCOPE_EXCLUDE.get(self.tenant, set())
            return q_scope not in excluded
        return True

    def _collect_filtered_queries(self) -> List[Dict]:
        all_queries = []
        for cat_name, cat_data in ALL_CATEGORIES.items():
            for q in cat_data["queries"]:
                all_queries.append({**q, "_category": cat_name})

        # Filtro de scope / tenant
        all_queries = [q for q in all_queries if self._scope_ok(q)]

        if self.levels:
            all_queries = [q for q in all_queries if q.get("difficulty", 0) in self.levels]

        if self.agents and "all" not in self.agents and "orchestrator" not in self.agents:
            target = {_AGENT_NAME_MAP[a] for a in self.agents if a in _AGENT_NAME_MAP}
            if target:
                all_queries = [
                    q for q in all_queries
                    if any(a in q.get("expected_agents", []) for a in target)
                ]

        all_queries.sort(key=lambda q: (q.get("difficulty", 0), q.get("_category", "")))

        if self.max_queries:
            all_queries = all_queries[:self.max_queries]

        return all_queries

    async def setup(self):
        print(f"\n{'='*80}\n🚀  BENCHMARK DATA SPACE MCP\n{'='*80}")
        print(f"   Modelo:  {self.model_label}")
        print(f"   Tenant:  {self.tenant or 'config default'}")
        print(f"   Scope:   {self.scope_filter or 'auto'}")
        if self.categories:
            print(f"   Modo:    categorías {self.categories}")
        else:
            level_s = f"niveles {sorted(self.levels)}" if self.levels else "todos los niveles"
            agent_s = f"agentes {self.agents}" if self.agents else "todos los agentes"
            print(f"   Modo:    por nivel · {level_s} · {agent_s}")
        self.client = MCPChatClient(config_path=self.config_path)
        if not await self.client.conectar():
            raise RuntimeError("No se pudo conectar a los servidores MCP")
        # Si se pasa tenant explícito, sobreescribir el default del cliente
        if self.tenant:
            self.client.default_tenant = self.tenant
        await self.client.inicializar_agente()
        print("✅  Sistema inicializado\n")

    async def teardown(self):
        if self.client:
            try:
                await self.client.cerrar()
            except Exception:
                pass

    async def run_query(self, query_data: Dict, category: str, iteration: int) -> Dict:
        prompt  = query_data["prompt"]
        qid     = query_data.get("id", f"{category}-{iteration}")
        session = f"bench_{category}"
        self.tracer.reset()
        start = time.time()
        try:
            result = await self.client.procesar_peticion_api({
                "request_id": f"bench_{qid}_{int(start*1000)}",
                "session_id": session,
                "input_text": prompt,
                "modality":   "text",
                "_context":   {"ngsild_tenant": self.client.default_tenant} if self.client.default_tenant else {},
            })
            elapsed     = time.time() - start
            metrics     = result.get("metrics", {})
            tokens_data = metrics.get("tokens", {})
            response    = result.get("response", {}).get("text", "")
            trace         = self.tracer.get_trace()
            agents_called = self.tracer.get_agents_called()
            tools_called  = self.tracer.get_tools_called()

            auto_valid = AutoValidator.run_all(
                response=response, tool_calls=trace["tool_calls"],
                expected_agents=query_data.get("expected_agents", []),
                actual_agents=agents_called,
            )
            expected_contains = query_data.get("expected_answer_contains", [])
            if expected_contains:
                resp_lower = response.lower()
                missing = [kw for kw in expected_contains if kw.lower() not in resp_lower]
                answer_check = (
                    {"passed": False, "detail": f"No encontrado: {missing}", "missing": missing}
                    if missing else {"passed": True, "detail": "ok", "missing": []}
                )
                auto_valid["answer_contains"] = answer_check
                ok_n, total_n = map(int, auto_valid["_score"].split("/"))
                auto_valid["_all_passed"] = auto_valid["_all_passed"] and answer_check["passed"]
                auto_valid["_score"] = f"{ok_n + (1 if answer_check['passed'] else 0)}/{total_n+1}"

            return {
                "model":       self.model_label,
                "tenant":      self.client.default_tenant or "",
                "scope":       query_data.get("scope", "generic"),
                "query_id":    qid,
                "category":    category,
                "difficulty":  query_data.get("difficulty", 0),
                "prompt":      prompt,
                "notes":       query_data.get("notes", ""),
                "doc":         query_data.get("doc", ""),
                "expected_answer_contains": expected_contains,
                "success":     result.get("status") == "success",
                "error":       result.get("error_message", ""),
                "error_code":  result.get("error_code", ""),
                "timestamp":   datetime.now().isoformat(),
                "total_time":  round(elapsed, 3),
                "llm_time":    round(metrics.get("llm_time", 0), 3),
                "tokens_prompt":     tokens_data.get("prompt", 0),
                "tokens_completion": tokens_data.get("completion", 0),
                "tokens_total":      tokens_data.get("total", 0),
                "llm_calls":   metrics.get("llm_calls", 0),
                "cost_usd":    metrics.get("cost_usd", 0),
                "response":    response,
                "response_len": len(response),
                "agents_called": agents_called,
                "tools_called":  tools_called,
                "trace_delegations": trace["delegations"],
                "trace_tool_calls":  trace["tool_calls"],
                "num_delegations":   len(trace["delegations"]),
                "num_tool_calls":    len(trace["tool_calls"]),
                "auto_valid":  auto_valid,
                "auto_passed": auto_valid["_all_passed"],
                "auto_score":  auto_valid["_score"],
                "expected_agents": query_data.get("expected_agents", []),
                "expected_tools":  query_data.get("expected_tools", []),
                "quality_score": None,
                "quality_notes": "",
            }
        except Exception as e:
            return {
                "model": self.model_label, "tenant": self.client.default_tenant or "",
                "scope": query_data.get("scope", "generic"),
                "query_id": qid, "category": category,
                "difficulty": query_data.get("difficulty", 0), "prompt": prompt,
                "doc": query_data.get("doc", ""), "success": False, "error": str(e),
                "error_code": "EXCEPTION", "total_time": round(time.time() - start, 3),
                "response": "", "agents_called": [], "tools_called": [],
                "trace_delegations": [], "trace_tool_calls": [],
                "num_delegations": 0, "num_tool_calls": 0,
                "auto_passed": False, "auto_score": "0/6", "auto_valid": {},
                "expected_agents": query_data.get("expected_agents", []),
                "expected_answer_contains": query_data.get("expected_answer_contains", []),
                "quality_score": None, "quality_notes": "",
                "timestamp": datetime.now().isoformat(),
            }

    async def run(self):
        print(f"\n{'='*80}\n🏁  EJECUTANDO — modelo: {self.model_label}  tenant: {self.tenant or 'default'}\n{'='*80}\n")
        use_level_mode = (self.levels is not None or self.agents is not None) and not self.categories
        if use_level_mode:
            await self._run_by_level()
        else:
            await self._run_by_category()
        self._print_summary()
        self._save_results()

    async def _run_by_level(self):
        queries = self._collect_filtered_queries()
        if not queries:
            print("⚠️  Sin queries tras aplicar los filtros.")
            return
        level_label = f"niveles {sorted(self.levels)}" if self.levels else "todos los niveles"
        agent_label = f"agentes {self.agents}" if self.agents and "all" not in self.agents else "todos"
        print(f"   Filtro: {level_label}  ·  {agent_label}  ·  {len(queries)} queries\n")
        current_level = None
        for i, qdata in enumerate(queries, 1):
            lvl = qdata.get("difficulty", 0)
            if lvl != current_level:
                current_level = lvl
                print(f"\n── NIVEL {lvl} {'\u2605'*lvl}{'\u2606'*(5-lvl)} {'─'*55}")
            cat = qdata.get("_category", "")
            scope_tag = f"[{qdata.get('scope','?')}] "
            preview = qdata["prompt"][:60] + ("…" if len(qdata["prompt"]) > 60 else "")
            print(f"  [{i}/{len(queries)}] [{qdata['id']}] [{cat}] {scope_tag}{preview}")
            result = await self.run_query(qdata, cat, i)
            self.results.append(result)
            self._print_query_result(result)
            await asyncio.sleep(0.3)

    async def _run_by_category(self):
        cats = self.categories if self.categories else list(TEST_QUERIES.keys())
        if cats == ["all"]:
            cats = list(TEST_QUERIES.keys())
        for category in cats:
            if category not in ALL_CATEGORIES:
                print(f"⚠️  Categoría '{category}' desconocida.")
                continue
            cat_data = ALL_CATEGORIES[category]
            queries = [q for q in cat_data["queries"] if self._scope_ok(q)]
            n = min(len(queries), self.queries_per_category)
            print(f"\n📊 {category.upper()} — {cat_data['description']}")
            print(f"   Complejidad: {'\u2605'*cat_data['complexity']}{'\u2606'*(5-cat_data['complexity'])}  |  {n} queries")
            print(f"{'─'*80}")
            for i in range(n):
                qdata = queries[i]
                scope_tag = f"[{qdata.get('scope','?')}] "
                preview = qdata["prompt"][:60] + ("…" if len(qdata["prompt"]) > 60 else "")
                print(f"  [{i+1}/{n}] [{qdata['id']}] (★{qdata.get('difficulty','?')}) {scope_tag}{preview}")
                result = await self.run_query(qdata, category, i + 1)
                self.results.append(result)
                self._print_query_result(result)
                await asyncio.sleep(0.3)

    def _print_query_result(self, result: Dict):
        status   = "✅" if result["success"] else "❌"
        auto_sym = "🟢" if result.get("auto_passed") else "🟡"
        agents_s = ", ".join(result["agents_called"]) or "—"
        print(f"      {status} {result['total_time']:.2f}s | "
              f"tok {result.get('tokens_prompt',0)}→{result.get('tokens_completion',0)} | "
              f"${result.get('cost_usd',0):.6f} | {auto_sym} {result.get('auto_score','?')}")
        print(f"         agents: {agents_s}")
        if result["response"]:
            r = result["response"]
            print(f"         resp:   {r[:110]}…" if len(r) > 110 else f"         resp:   {r}")

    def _print_summary(self):
        print(f"\n{'='*80}\n📈  RESUMEN — {self.model_label} · tenant:{self.tenant or 'default'}\n{'='*80}")
        total = len(self.results)
        if total == 0:
            print("  Sin resultados.")
            return
        success = [r for r in self.results if r["success"]]
        auto_ok = [r for r in self.results if r.get("auto_passed")]
        print(f"  Total: {total} | API OK: {len(success)} ({len(success)/total*100:.1f}%) | "
              f"Auto OK: {len(auto_ok)} ({len(auto_ok)/total*100:.1f}%)")
        if success:
            times   = [r["total_time"] for r in success]
            costs   = [r.get("cost_usd", 0) for r in success]
            tok_in  = [r.get("tokens_prompt", 0) for r in success]
            tok_out = [r.get("tokens_completion", 0) for r in success]
            print(f"  Latencia: media {statistics.mean(times):.2f}s  "
                  f"p50 {statistics.median(times):.2f}s  "
                  f"p95 {self._p95(times):.2f}s  max {max(times):.2f}s")
            print(f"  Tokens:   {sum(tok_in):,} IN / {sum(tok_out):,} OUT")
            print(f"  Coste:    ${sum(costs):.6f} total  ${statistics.mean(costs):.6f} avg/query")
        print(f"\n  Por nivel de dificultad:")
        for lvl in sorted({r.get("difficulty", 0) for r in self.results}):
            lr = [r for r in success if r.get("difficulty") == lvl]
            if lr:
                auto_n = sum(1 for r in lr if r.get("auto_passed"))
                tl = [r["total_time"] for r in lr]
                print(f"    Nivel {lvl} {'\u2605'*lvl}{'\u2606'*(5-lvl)}: {len(lr)} queries  "
                      f"media {statistics.mean(tl):.2f}s  p95 {self._p95(tl):.2f}s  "
                      f"auto {auto_n}/{len(lr)}  ${sum(r.get('cost_usd',0) for r in lr):.6f}")
        scopes_seen = sorted({r.get("scope","generic") for r in self.results})
        if len(scopes_seen) > 1:
            print(f"\n  Por scope:")
            for sc in scopes_seen:
                sr = [r for r in success if r.get("scope") == sc]
                if sr:
                    auto_n = sum(1 for r in sr if r.get("auto_passed"))
                    print(f"    {sc:<12}: {len(sr)} queries  {statistics.mean([r['total_time'] for r in sr]):.2f}s avg  auto {auto_n}/{len(sr)}")
        cats_seen = sorted({r.get("category","") for r in self.results})
        if len(cats_seen) > 1:
            print(f"\n  Por categoría:")
            for cat in cats_seen:
                cr = [r for r in success if r["category"] == cat]
                if cr:
                    auto_n = sum(1 for r in cr if r.get("auto_passed"))
                    print(f"    {cat:<22}: {len(cr)} queries  {statistics.mean([r['total_time'] for r in cr]):.2f}s avg  auto {auto_n}/{len(cr)}")
        fail_counts: Dict[str, int] = {}
        for r in self.results:
            for check, val in r.get("auto_valid", {}).items():
                if check.startswith("_"): continue
                if not val.get("passed", True):
                    fail_counts[check] = fail_counts.get(check, 0) + 1
        if fail_counts:
            print(f"\n  ⚠️  Validaciones fallidas:")
            for check, n in sorted(fail_counts.items(), key=lambda x: -x[1]):
                print(f"    {check:<28}: {n}x")
        print(f"{'='*80}")

    def _save_results(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_safe  = re.sub(r'[^\w\-]', '_', self.model_label)[:20]
        tenant_safe = self.tenant or "default"
        if self.categories:
            tag = f"{model_safe}_{tenant_safe}_cat_{'_'.join((self.categories or [])[:3])}"
        else:
            lvl_tag   = "L" + "".join(str(l) for l in sorted(self.levels)) if self.levels else "Lall"
            agent_tag = "_".join(sorted(self.agents or ["all"]))[:15]
            tag       = f"{model_safe}_{tenant_safe}_{lvl_tag}_{agent_tag}"
        out = Path(__file__).resolve().parent.parent / "var" / "results"
        out.mkdir(exist_ok=True)
        json_path = out / f"bench_{tag}_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"timestamp": ts, "model": self.model_label, "tenant": tenant_safe,
                       "tag": tag, "results": self.results},
                      f, indent=2, ensure_ascii=False, default=str)
        print(f"\n💾 JSON: {json_path}")
        if EXCEL_AVAILABLE:
            xl_path = out / f"bench_{tag}_{ts}.xlsx"
            if self._save_excel(xl_path):
                print(f"📊 Excel: {xl_path}")
        else:
            csv_path = out / f"bench_{tag}_{ts}.csv"
            self._save_csv(csv_path)
            print(f"📊 CSV: {csv_path}")

    def _p95(self, data):
        if not data: return 0.0
        s = sorted(data)
        return s[min(int(len(s)*0.95), len(s)-1)]

    def _save_excel(self, path: Path) -> bool:
        try:
            wb = openpyxl.Workbook()
            wb.remove(wb.active)
            BLUE="1F497D"; GREEN="C6EFCE"; RED="FFC7CE"; YELLOW="FFEB9C"
            def hdr(ws, headers, row=1):
                for c, h in enumerate(headers, 1):
                    cell = ws.cell(row, c, h)
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill(start_color=BLUE, end_color=BLUE, fill_type="solid")
                    cell.alignment = Alignment(horizontal="center", wrap_text=True)
            def cc(ws, ri, ci, val, ok):
                c = ws.cell(ri, ci, val)
                c.fill = PatternFill(start_color=GREEN if ok else RED, end_color=GREEN if ok else RED, fill_type="solid")
            ws1 = wb.create_sheet("Results")
            hdr(ws1, ["Modelo","Tenant","Scope","ID","Categ.","Nivel","Doc","Prompt",
                      "API\u2705","Auto\u2705","Score","Tiempo(s)","Tok IN","Tok OUT","Coste$",
                      "Tools","Delegs","Agentes","Respuesta completa","\u2b50Calidad","\U0001f4ddNotas"])
            for ri, r in enumerate(self.results, 2):
                def w(c, v): ws1.cell(ri, c, _xl(v))
                w(1,r.get("model","")); w(2,r.get("tenant","")); w(3,r.get("scope",""))
                w(4,r.get("query_id","")); w(5,r.get("category","")); ws1.cell(ri,6,r.get("difficulty",0))
                w(7,r.get("doc","")); w(8,r.get("prompt",""))
                cc(ws1,ri,9,"\u2713" if r["success"] else "\u2717",r["success"])
                cc(ws1,ri,10,"\u2713" if r.get("auto_passed") else "\u2717",r.get("auto_passed"))
                w(11,r.get("auto_score",""))
                ws1.cell(ri,12,r.get("total_time",0)); ws1.cell(ri,13,r.get("tokens_prompt",0))
                ws1.cell(ri,14,r.get("tokens_completion",0)); ws1.cell(ri,15,round(r.get("cost_usd",0),6))
                ws1.cell(ri,16,r.get("num_tool_calls",0)); ws1.cell(ri,17,r.get("num_delegations",0))
                w(18,", ".join(r.get("agents_called",[]))); w(19,r.get("response",""))
                for col in [20,21]:
                    ws1.cell(ri,col).fill = PatternFill(start_color="FFF2CC",end_color="FFF2CC",fill_type="solid")
            ws1.column_dimensions["H"].width=60; ws1.column_dimensions["R"].width=30; ws1.column_dimensions["S"].width=80
            ws2 = wb.create_sheet("Validaciones")
            checks=["not_empty","terse_mode","no_prefix","no_json_pollution","anti_hallucination","no_dodge","routing","answer_contains"]
            hdr(ws2,["Modelo","Tenant","Scope","ID","Cat.","Nivel","Auto OK","Keywords"]+checks)
            for ri,r in enumerate(self.results,2):
                for ci,v in enumerate([r.get("model",""),r.get("tenant",""),r.get("scope",""),
                                        r.get("query_id",""),r.get("category","")],1):
                    ws2.cell(ri,ci,_xl(v))
                ws2.cell(ri,6,r.get("difficulty",0))
                ao=r.get("auto_passed",False)
                c=ws2.cell(ri,7,"\u2713" if ao else "\u2717")
                c.fill=PatternFill(start_color=GREEN if ao else YELLOW,end_color=GREEN if ao else YELLOW,fill_type="solid")
                ws2.cell(ri,8,_xl(str(r.get("expected_answer_contains",""))))
                av=r.get("auto_valid",{})
                for ci2,check in enumerate(checks,9):
                    info=av.get(check,{})
                    if not info: continue
                    passed=info.get("passed",True)
                    cell=ws2.cell(ri,ci2,"\u2713" if passed else _xl(f"\u2717 {info.get('detail','')}"))
                    cell.fill=PatternFill(start_color=GREEN if passed else RED,end_color=GREEN if passed else RED,fill_type="solid")
            ws3=wb.create_sheet("Trazas")
            hdr(ws3,["Modelo","Tenant","ID","Doc","Tipo","Agente","Tool","Dir.","Contenido","ms","Timestamp"])
            row3=2
            for r in self.results:
                for d in r.get("trace_delegations",[]):
                    for ci,v in enumerate([r.get("model",""),r.get("tenant",""),r.get("query_id",""),
                                            r.get("doc",""),"delegacion",d.get("agent","")],1):
                        ws3.cell(row3,ci,_xl(v))
                    ws3.cell(row3,8,_xl(d.get("direction","")))
                    ws3.cell(row3,9,_xl(d.get("instruction","") or d.get("result_preview","")))
                    ws3.cell(row3,10,d.get("duration_ms",""))
                    ts_val=d.get("timestamp")
                    if ts_val: ws3.cell(row3,11,datetime.fromtimestamp(ts_val).strftime("%H:%M:%S.%f")[:12])
                    row3+=1
                for t in r.get("trace_tool_calls",[]):
                    for ci,v in enumerate([r.get("model",""),r.get("tenant",""),r.get("query_id",""),
                                            r.get("doc",""),"tool_call",t.get("server",""),t.get("tool","")],1):
                        ws3.cell(row3,ci,_xl(v))
                    ws3.cell(row3,9,_xl(f"ARGS:\n{t.get('args_preview','')}\n\nRESULT:\n{t.get('result_preview','')}"))
                    ws3.cell(row3,10,round(t.get("duration_ms",0),1))
                    ts_val=t.get("timestamp")
                    if ts_val: ws3.cell(row3,11,datetime.fromtimestamp(ts_val).strftime("%H:%M:%S.%f")[:12])
                    row3+=1
            ws3.column_dimensions["I"].width=120
            wb.save(path)
            return True
        except Exception as e:
            print(f"\u26a0\ufe0f  Error Excel: {e}")
            return False

    def _save_csv(self, path: Path):
        import csv
        fields=["model","tenant","scope","query_id","category","difficulty","doc","prompt","success",
                "error_code","total_time","tokens_prompt","tokens_completion","cost_usd",
                "num_tool_calls","num_delegations","agents_called","tools_called",
                "auto_passed","auto_score","response","quality_score","quality_notes","timestamp"]
        with open(path,"w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
            w.writeheader()
            for r in self.results:
                row=dict(r)
                row["agents_called"]=", ".join(r.get("agents_called",[]))
                row["tools_called"]=", ".join(r.get("tools_called",[]))
                w.writerow(row)

    def export_finetuning_jsonl(self,output_path:str,only_passed:bool=True,system_prompt:str="")->int:
        rows=[r for r in self.results if(not only_passed or r.get("auto_passed"))]
        written=0
        Path(output_path).parent.mkdir(parents=True,exist_ok=True)
        with open(output_path,"w",encoding="utf-8") as f:
            for r in rows:
                messages=[]
                if system_prompt: messages.append({"role":"system","content":system_prompt})
                messages.append({"role":"user","content":r["prompt"]})
                delegations=r.get("trace_delegations",[])
                reqs=[d for d in delegations if d["direction"]=="request"]
                resps=[d for d in delegations if d["direction"]=="response"]
                for req,resp in zip(reqs,resps):
                    call_id=f"call_{req['agent']}_{written:04d}"
                    messages.append({"role":"assistant","content":None,"tool_calls":[{"id":call_id,"type":"function","function":{"name":f"Agente_{req['agent']}","arguments":json.dumps({"instruccion":req["instruction"]},ensure_ascii=False)}}]})
                    messages.append({"role":"tool","content":resp.get("result_preview",""),"tool_call_id":call_id})
                messages.append({"role":"assistant","content":r["response"]})
                if reqs:
                    f.write(json.dumps({"messages":messages},ensure_ascii=False)+"\n")
                    written+=1
        print(f"\u2705 {written} ejemplos exportados \u2192 {output_path}")
        return written


async def main():
    available_agents=["orion","ql","rag","orchestrator","all"]
    available_cats=list(ALL_CATEGORIES.keys())
    available_scopes=["generic","ibermot","metapan","all"]
    parser=argparse.ArgumentParser(
        description="Benchmark Data Space MCP — Multi-tenant industrial",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
MODO NIVEL/AGENTE:
  --level 1 2 3  --agent orion ql  --max-queries N

TENANT Y SCOPE:
  --tenant ibermot   activa IBERMOT (incluye preguntas ibermot_specific)
  --tenant metapan   activa METAPAN (incluye preguntas metapan_specific)
  --scope generic    solo preguntas gen\u00e9ricas
  --scope all        todas las preguntas

MODELO:
  --model mistral-large-3   etiqueta el resultado

Categor\u00edas: {", ".join(available_cats)}

Ejemplos:
  python benchmark.py --config config.local.yaml --scope generic --agent orion ql
  python benchmark.py --config config.local.yaml --tenant ibermot --level 1 2 3 --agent orion ql
  python benchmark.py --config config.local.yaml --tenant metapan --category discovery metapan_specific
  python benchmark.py --config config.local.yaml --tenant ibermot --model gpt4o-mini --agent orion ql
  python benchmark.py --config config.local.yaml --tenant ibermot --agent orion ql --export-ft training_data/ft_v1.jsonl
        """
    )
    parser.add_argument("--config",default="config/config.local.yaml")
    parser.add_argument("--model",default=None)
    parser.add_argument("--tenant",default=None,choices=["ibermot","metapan"])
    parser.add_argument("--scope",default=None,choices=available_scopes)
    parser.add_argument("--level",nargs="+",type=int)
    parser.add_argument("--agent",nargs="+",choices=available_agents)
    parser.add_argument("--max-queries",type=int,default=None)
    parser.add_argument("--category",nargs="+")
    parser.add_argument("--queries",type=int,default=10)
    parser.add_argument("--export-ft",type=str,default=None)
    args=parser.parse_args()
    use_level_mode=(args.level is not None or args.agent is not None) and not args.category
    if use_level_mode:
        bench=DataSpaceBenchmark(config_path=args.config,levels=args.level,agents=args.agent,
            max_queries=args.max_queries,model_label=args.model,
            tenant=args.tenant,scope_filter=args.scope)
    else:
        cats=args.category or list(TEST_QUERIES.keys())
        if cats==["all"]: cats=list(TEST_QUERIES.keys())
        qpc=args.queries
        if "rag-test" in cats and qpc==10: qpc=60
        bench=DataSpaceBenchmark(categories=cats,queries_per_category=qpc,config_path=args.config,
            model_label=args.model,tenant=args.tenant,scope_filter=args.scope)
    try:
        await bench.setup()
        await bench.run()
        if args.export_ft:
            bench.export_finetuning_jsonl(args.export_ft,only_passed=True)
    finally:
        await bench.teardown()


if __name__=="__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n\U0001f44b Benchmark interrumpido.")