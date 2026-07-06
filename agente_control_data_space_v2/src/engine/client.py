# src/engine/client.py
"""
Cliente MCP con arquitectura Multi-Agente (Gestor + Especialistas).

Cambios v2.7
------------
- Fix definitivo de _extract_tool_text: tool.acall() de LlamaIndex devuelve
  un ToolOutput que ENVUELVE el CallToolResult original en .raw_output.
  La v2.6 buscaba structuredContent y content directamente en el ToolOutput
  (que no los tiene en el formato esperado), caía al fallback str(raw_output)
  y devolvía la repr del CallToolResult — con el texto duplicado y los \\n
  escapados. Consecuencias visibles que confirmaban el bug:
    * Schema cacheado con doble longitud (12787 chars en vez de 6276).
    * "Orion: ok (0 tipos, 830 entidades)" — 0 porque count("\\nTYPE ")
      no matchea con \\n escapado; 830 = 2 × 415 porque el regex de
      entities matchea en content y en structuredContent.
    * RAG/QL = error porque el JSON con backslashes no parsea.
  El helper ahora inspecciona PRIMERO result.raw_output y DESPUÉS result,
  buscando en cada uno structuredContent → content (lista) → content (str).
  También se usa en _execute_direct_tool, que tenía el mismo bug.

Cambios v2.6
------------
- Fix de extracción de texto en /api/connect: el helper _extract_tool_text
  lee structuredContent['result'] o content[0].text en vez de str(result),
  que devolvía la repr completa del objeto MCP con todo duplicado y los
  '\\n' escapados. Esto causaba que /api/connect mostrase:
    * 0 tipos (count('\\nTYPE ') no matcheaba porque los newlines eran
      literal '\\n')
    * total_entities duplicado (8 tipos × 2 sitios = 16 matches,
      416 × 2 = 832)
    * "RAG: error" y "QuantumLeap: error" (json.loads fallaba siempre).
  La caché interna del schema NO estaba corrupta — solo el conteo que
  devuelve /api/connect.
- Idempotencia confirmada: _build_schema_for_tenant ya tenía el check
  "if tenant in self._tenant_schemas: return" + lock con double-check.
  No reconstruye el schema si ya está cargado el mismo tenant.

Cambios v2.5
------------
- Validación adicional para Orion-LD list_entities y count_entities:
  rechaza llamadas con `q` que no contienen operadores NGSI-LD válidos
  (==, !=, >, <, >=, <=, ~=). Esto evita el error clásico del LLM de
  usar q='AGV' o q='prensa-001' como fragmento de id (que devuelve []
  siempre porque q filtra ATRIBUTOS, no ids). El LLM recibe un error
  claro indicando que use resolve_entity_ids.

Cambios v2.4
------------
- Validación de precondiciones genérica en _wrap_tools_with_logging.
  Las tools de quantumleap que reciben entity_id rechazan la llamada si
  el entity_id no es una URN NGSI-LD canónica (no empieza por
  'urn:ngsi-ld:<Type>:'). El LLM recibe el motivo como tool error y debe
  corregir el flujo pasando primero por Agente_orion_ld. Esto impide
  alucinaciones tipo entity_id='urn:ngsi-ld:AGV:002' o entity_id='prensa-001'
  SIN depender del prompt y SIN hardcodear nada del dominio del tenant.
- attr_name con guión (p.ej. 'fuerza-meas') también se rechaza: es un
  fragmento de id, no un nombre de atributo SmartDataModels.

Cambios v2.3
------------
- precargar_tenant(tenant): método público llamado por /api/connect.
  Construye el schema de Orion una sola vez por tenant y lo guarda en
  self._tenant_schemas (cache GLOBAL del proceso, no per-petición).
- _inject_schema_into_orion_specialist ahora consume self._tenant_schemas.
  No reconstruye el schema en cada petición; solo lo inyecta en el prompt
  del especialista si el tenant cambió desde la inyección anterior.
- get_preloaded_tenants(): expone la lista de tenants ya precargados.

Soporte multi-tenant por petición
-----------------------------------
data["_context"] viaja desde api_server.py al ContextVar _request_context,
y _wrap_tools_with_logging inyecta el tenant en cada tool call con SIEMPRE
sobrescritura (el LLM nunca puede elegir el tenant).
"""

import sys, os
from pathlib import Path as _Path

# src/engine/client.py:
#   _SRC_DIR      = .../<root>/src           (raíz de los paquetes importables)
#   _PROJECT_ROOT = .../<root>               (donde viven config/ y var/)
_SRC_DIR = _Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import sys as _sys
import asyncio as _asyncio
if _sys.platform.startswith("win"):
    try:
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

import re
import asyncio
import json
import yaml
import time
from typing import Optional, Dict, Any, List
from contextlib import AsyncExitStack
from contextvars import ContextVar
from pathlib import Path

try:
    from dotenv import load_dotenv
    # El .env vive en config/ (raíz del proyecto, un nivel por encima de src/).
    _ENV_PATH = _PROJECT_ROOT / "config" / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
    else:
        load_dotenv()  # fallback: busca en el cwd
except ImportError:
    pass

from mcp import StdioServerParameters, ClientSession
from mcp.client.stdio import stdio_client

from llama_index.core import Settings
from llama_index.tools.mcp import BasicMCPClient, McpToolSpec
from llama_index.core.agent.workflow import FunctionAgent
from llama_index.core.workflow import Context
from llama_index.core.tools import FunctionTool

from engine.response_processing import _to_text, build_response_payload

# REGLA DE ORO: el motor NO importa nada de `project/`. Obtiene prompts,
# validadores y comportamientos a través del registro genérico de
# `engine.validators`. Si `project/` no se ha importado, estos hooks
# devuelven valores por defecto y el motor arranca igual (modo básico).
from engine.validators import (
    get_system_prompt,
    should_retry_for_dodge,
    get_dodge_retry_suffix,
    reconcile_metrics,
    should_redirect_routing,
    get_routing_redirect_msg,
    notify_schema_loaded,
)

from engine.logging_setup import (
    setup_logging, get_logger,
    set_log_context, clear_log_context,
    log_conversation, log_metrics, log_agent_flow,
)

setup_logging()
logger = get_logger("mcp.client")

from engine.metrics import (
    metrics_collector, RequestMetrics, calculate_cost, token_tracker
)

# Módulos del motor extraídos de este fichero (responsabilidad única):
from engine.llm_providers import build_llm
from engine.token_tracking import (
    install_token_interceptor, install_llamaindex_token_handler,
)
from engine.tool_wrapper import (
    reset_tool_counters, get_tool_counters, get_tool_call_count,
    set_request_context, extract_tool_text, wrap_tools_with_logging,
    get_tenant_param,
    reset_specialist_outputs, record_specialist_output, get_specialist_outputs,
)
from engine.rendering import render_payload
from engine.mcp_transport import StdioMCPClient

# ─── Cliente principal ────────────────────────────────────────────────────────

class MCPChatClient:
    """Cliente MCP con arquitectura Multi-Agente (Gestor + Especialistas)."""

    def __init__(self, config_path: str = "config.yaml"):
        self.config = self._load_config(config_path)

        agent_config        = self.config.get("agent", {})
        self.default_tenant = agent_config.get("default_tenant", "")
        self.model_name     = agent_config.get("default_model", "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4")
        self.timeout        = float(agent_config.get("request_timeout", 240.0))
        self.max_tool_calls = int(agent_config.get("max_tool_calls", 6))
        self.provider       = agent_config.get("provider", "local")

        # Modo agéntico: "multi" (Gestor + un especialista por MCP) o "single"
        # (un único agente con TODAS las tools). Se lee de config; default multi.
        raw_mode        = str(agent_config.get("agent_mode", "multi")).strip().lower()
        self.agent_mode = raw_mode if raw_mode in ("multi", "single") else "multi"
        if raw_mode and raw_mode != self.agent_mode:
            logger.warning("agent_mode '%s' no válido; usando 'multi'", raw_mode)

        # Activar los prompts del modo elegido (registra el proveedor en el
        # motor). Si el paquete `prompts` no está, el motor usa el genérico.
        try:
            import prompts as _prompts
            self.agent_mode = _prompts.activate(self.agent_mode)
        except Exception as e:
            logger.warning("No se pudo activar prompts del modo '%s': %s", self.agent_mode, e)

        # Construir el LLM según el proveedor (factory en engine.llm_providers).
        self.llm, self._cost_model_name = build_llm(agent_config)
        Settings.llm = self.llm

        install_token_interceptor(self.llm)
        self._token_counter = install_llamaindex_token_handler()

        if self.default_tenant:
            logger.info("Tenant por defecto cargado desde config │ %s", self.default_tenant)

        self.specs_by_server:   Dict[str, List[Any]]     = {}
        self.specialist_agents: Dict[str, FunctionAgent] = {}
        self.aggregator_agent:  Optional[FunctionAgent]  = None
        self.session_contexts:  Dict[str, Context]       = {}
        self._session_locks:    Dict[str, asyncio.Lock]  = {}
        self._init_done         = False
        self._active_clients:   List[Any]                = []

        # ── Cache GLOBAL del proceso de schemas por tenant ─────────────
        # Se rellena en precargar_tenant() o de forma lazy en la primera
        # petición que llegue con un tenant nuevo. Una sola construcción
        # por tenant, vida del proceso.
        self._tenant_schemas:        Dict[str, str] = {}
        # Indica qué tenant tiene actualmente inyectado el schema. En multi se
        # inyecta en el especialista de Orion; en single, en el agente único.
        self._schema_current_tenant: Optional[str]  = None
        self._schema_load_lock = asyncio.Lock()

    def _load_config(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            provider      = config.get("agent", {}).get("provider", "local")
            provider_path = os.path.join(
                os.path.dirname(os.path.abspath(path)), "providers", f"{provider}.yaml"
            )
            if os.path.exists(provider_path):
                with open(provider_path, encoding="utf-8") as f:
                    provider_cfg = yaml.safe_load(f) or {}
                config["agent"].update(provider_cfg)
            else:
                get_logger("mcp.client").warning(
                    "Fichero de proveedor no encontrado: %s", provider_path
                )
            return config
        except Exception as e:
            get_logger("mcp.client").error("Error cargando config: %s", e, exc_info=True)
            return {}

    async def conectar(self) -> bool:
        servers_conf = self.config.get("servers", {})
        if not servers_conf:
            logger.warning("No hay servidores definidos en config.yaml")
            return False

        connected_count = 0
        for name, conf in servers_conf.items():
            if not conf.get("enabled", False):
                continue
            try:
                client_obj = None
                if conf.get("type") == "stdio":
                    cmd      = conf.get("command", "uv")
                    args     = conf.get("args", [])
                    env_vars = os.environ.copy()
                    if "env" in conf:
                        env_vars.update(conf["env"])
                    server_params = StdioServerParameters(command=cmd, args=args, env=env_vars)
                    try:
                        client_obj = BasicMCPClient(transport_params=server_params)
                    except TypeError:
                        client_obj = StdioMCPClient(server_params)
                        await client_obj.connect()
                else:
                    port       = conf.get("port", 8000)
                    url        = f"http://127.0.0.1:{port}/sse"
                    client_obj = BasicMCPClient(url=url)

                tool_spec = McpToolSpec(client=client_obj)
                self._active_clients.append(client_obj)
                tools = await tool_spec.to_tool_list_async()

                if tools:
                    tools = wrap_tools_with_logging(tools, name)
                    self.specs_by_server[name] = tools
                    connected_count += 1
                    logger.info(
                        "Servidor MCP conectado │ %s │ %d herramientas │ tenant-aware=%s",
                        name, len(tools), get_tenant_param(name) is not None,
                    )
                else:
                    logger.warning("Servidor MCP sin herramientas │ %s", name)

            except (Exception, asyncio.CancelledError, BaseException) as e:
                logger.error(
                    "Fallo conectando servidor MCP │ %s │ %s: %s",
                    name, type(e).__name__, e, exc_info=True,
                )

        if connected_count == 0:
            logger.critical("No se pudo conectar a ningún servidor MCP")

        return connected_count > 0

    async def inicializar_agente(self):
        if self._init_done:
            return

        if self.agent_mode == "single":
            await self._inicializar_single()
        else:
            await self._inicializar_multi()

        self._init_done = True

    async def _inicializar_multi(self):
        """Gestor + un especialista (sub-agente) por cada MCP conectado."""
        aggregator_tools = []
        for name, tools in self.specs_by_server.items():
            specialist  = self._crear_agente_especialista(name, tools)
            self.specialist_agents[name] = specialist
            desc        = self._generar_descripcion_especialista(name)
            agent_tool  = self._crear_herramienta_de_agente(name, specialist, desc)
            aggregator_tools.append(agent_tool)

        self.aggregator_agent = FunctionAgent(
            name="AgenteGestor",
            description="Orquestador del sistema industrial MCP",
            system_prompt=get_system_prompt("aggregator"),
            tools=aggregator_tools,
            llm=self.llm,
            max_tool_calls=self.max_tool_calls,
            allow_parallel_tool_calls=True,
        )
        logger.info(
            "Sistema Multi-Agente operativo │ %d especialistas registrados",
            len(aggregator_tools),
        )

    async def _inicializar_single(self):
        """UN único agente con TODAS las tools de todos los MCP conectados."""
        all_tools: List[Any] = []
        for name, tools in self.specs_by_server.items():
            all_tools.extend(tools)

        self.aggregator_agent = FunctionAgent(
            name="AgenteUnico",
            description="Agente único del sistema industrial MCP",
            system_prompt=get_system_prompt("single"),
            tools=all_tools,
            llm=self.llm,
            # En single no hay delegación: el presupuesto de tool calls es el
            # del Gestor (más holgado) porque resuelve todo en un mismo agente.
            max_tool_calls=self.max_tool_calls,
            allow_parallel_tool_calls=True,
        )
        logger.info(
            "Sistema de Agente Único operativo │ %d tools de %d servidores",
            len(all_tools), len(self.specs_by_server),
        )

    def _crear_agente_especialista(self, server_name: str, tools: List[Any]) -> FunctionAgent:
        return FunctionAgent(
            name=f"Especialista_{server_name}",
            description=f"Experto en {server_name}",
            system_prompt=get_system_prompt(server_name),
            tools=tools,
            llm=self.llm,
            max_tool_calls=5,
        )

    # ══════════════════════════════════════════════════════════════════════
    # PRE-CARGA DE TENANT  (NUEVO — lo llama POST /api/connect)
    # ══════════════════════════════════════════════════════════════════════

    async def precargar_tenant(self, tenant: str) -> dict:
        """
        Precarga el contexto para un tenant: schema de Orion + verificación
        de RAG y QL. Idempotente: si el schema ya está cacheado para este
        tenant, no lo reconstruye, solo verifica RAG y QL otra vez.

        Devuelve un dict con el estado por servidor para que la UI lo muestre:
          {
            "orion":       {"status": "ok"|"empty"|"error", "types": N, "total_entities": M},
            "rag":         {"status": "ok"|"empty"|"error", "documents": K, "total_chunks": T},
            "quantumleap": {"status": "ok"|"degraded"|"error"}
          }
        """
        info = {
            "orion":       {"status": "unknown"},
            "rag":         {"status": "unknown"},
            "quantumleap": {"status": "unknown"},
        }

        # Setear el tenant en el contexto de petición para que la inyección
        # automática de tenant funcione durante esta precarga (viene de
        # /api/connect, sin el flujo normal de procesar_peticion_api).
        set_request_context({"ngsild_tenant": tenant})

        try:
            # ── 1. Orion: construir schema (cache hit si ya estaba) ──────
            info["orion"] = await self._preload_orion(tenant)

            # ── 2. RAG: listar documentos ────────────────────────────────
            info["rag"] = await self._preload_rag(tenant)

            # ── 3. QuantumLeap: ping con tenant ──────────────────────────
            info["quantumleap"] = await self._preload_ql(tenant)
        finally:
            set_request_context({})

        return info

    async def _preload_orion(self, tenant: str) -> dict:
        try:
            schema_text = await self._build_schema_for_tenant(tenant)
            if not schema_text or "DATA SPACE SCHEMA" not in schema_text:
                return {"status": "empty", "detail": "broker vacío o tenant sin datos"}

            # Parseo rápido de contadores desde el texto del schema.
            types_count = schema_text.count("\nTYPE ")
            total = 0
            for m in re.finditer(r"\((\d+) entities\)", schema_text):
                try:
                    total += int(m.group(1))
                except ValueError:
                    pass

            return {
                "status":         "ok",
                "types":          types_count,
                "total_entities": total,
            }
        except Exception as e:
            logger.warning("Preload Orion failed │ tenant=%s │ %s", tenant, e)
            return {"status": "error", "detail": str(e)}

    async def _preload_rag(self, tenant: str) -> dict:
        try:
            rag_tools = self.specs_by_server.get("rag_knowledge", [])
            list_tool = next(
                (t for t in rag_tools if t.metadata.name == "listar_documentos_vectorizados"),
                None,
            )
            if not list_tool:
                return {"status": "unavailable"}

            result = await list_tool.acall()
            raw = extract_tool_text(result)
            try:
                parsed = json.loads(raw)
            except Exception:
                return {"status": "error", "detail": "respuesta RAG no parseable"}

            if parsed.get("error"):
                return {"status": "error", "detail": parsed["error"]}

            total_chunks = parsed.get("total_chunks", 0) or 0
            documentos   = parsed.get("documentos", []) or []
            return {
                "status":       "ok" if total_chunks > 0 else "empty",
                "documents":    len(documentos),
                "total_chunks": total_chunks,
            }
        except Exception as e:
            logger.warning("Preload RAG failed │ tenant=%s │ %s", tenant, e)
            return {"status": "error", "detail": str(e)}

    async def _preload_ql(self, tenant: str) -> dict:
        try:
            ql_tools = self.specs_by_server.get("quantumleap", [])
            health_tool = next(
                (t for t in ql_tools if t.metadata.name == "ql_health"),
                None,
            )
            if not health_tool:
                return {"status": "unavailable"}

            result = await health_tool.acall()
            raw = extract_tool_text(result)
            try:
                parsed = json.loads(raw)
                return {"status": parsed.get("status", "unknown")}
            except Exception:
                return {"status": "error", "detail": "respuesta QL no parseable"}
        except Exception as e:
            logger.warning("Preload QL failed │ tenant=%s │ %s", tenant, e)
            return {"status": "error", "detail": str(e)}

    async def _build_schema_for_tenant(self, tenant: str) -> str:
        """
        Construye y cachea el schema de Orion para `tenant`. Si ya está en
        self._tenant_schemas, lo devuelve sin reconstruir. Pensado para que
        haya UNA sola construcción por tenant durante la vida del proceso.
        """
        if tenant in self._tenant_schemas:
            return self._tenant_schemas[tenant]

        async with self._schema_load_lock:
            # Doble check tras adquirir lock (otra petición podría haber
            # rellenado el cache mientras esperábamos).
            if tenant in self._tenant_schemas:
                return self._tenant_schemas[tenant]

            orion_tools = self.specs_by_server.get("orion_ld", [])
            schema_tool = next(
                (t for t in orion_tools if t.metadata.name == "get_schema_summary"),
                None,
            )
            if not schema_tool:
                logger.warning("get_schema_summary tool no encontrada")
                return ""

            try:
                result = await schema_tool.acall()
                schema_text = extract_tool_text(result)
            except Exception as e:
                logger.warning("Schema fetch failed │ tenant=%s │ %s", tenant, e)
                return ""

            if "DATA SPACE SCHEMA" in schema_text and "TYPE " in schema_text:
                self._tenant_schemas[tenant] = schema_text
                logger.info(
                    "Schema cacheado en proceso │ tenant=%s │ %d chars",
                    tenant, len(schema_text),
                )
                
                # Notificar a los observadores (el proyecto extrae keywords
                # estructurales del data space para la guarda de enrutamiento).
                notify_schema_loaded(tenant, schema_text)

            else:
                logger.warning(
                    "Schema vacío o malformado │ tenant=%s │ no se cachea", tenant
                )
                schema_text = ""

            return schema_text

    def get_preloaded_tenants(self) -> list[str]:
        """Tenants cuyo schema está ya en cache (para /health o debug)."""
        return sorted(self._tenant_schemas.keys())

    # ══════════════════════════════════════════════════════════════════════
    # INYECCIÓN DE SCHEMA EN EL SPECIALIST  (rápido, sin re-construir)
    # ══════════════════════════════════════════════════════════════════════

    async def _ensure_schema_in_specialist(self, tenant: str) -> None:
        """
        Inyecta el schema del tenant en el agente que ejecuta las tools de
        Orion. En modo multi es el especialista de Orion; en modo single es
        el agente único. NO reconstruye si el schema ya está en cache y NO
        re-inyecta si ese agente ya apunta al mismo tenant.
        """
        if not tenant:
            return

        # 1. Garantizar que el schema esté en cache (build si falta).
        schema_text = await self._build_schema_for_tenant(tenant)
        if not schema_text:
            return

        # 2. Si ya está inyectado este mismo tenant, salir.
        if self._schema_current_tenant == tenant:
            return

        # 3. Elegir el agente diana y su prompt base según el modo.
        if self.agent_mode == "single":
            target_agent = self.aggregator_agent
            base_prompt  = get_system_prompt("single")
            label        = "agente único"
        else:
            target_agent = self.specialist_agents.get("orion_ld")
            base_prompt  = get_system_prompt("orion_ld")
            label        = "specialist orion_ld"

        if not target_agent:
            return

        schema_header = "\n\n## PRE-LOADED SCHEMA\n\n"
        id_hint = (
            "\n\n## ID LOOKUP SHORTCUT\n"
            "DeviceMeasurement IDs follow this tenant's id convention "
            "(see sample ids in the schema above). Use get_entity() directly "
            "when the URN is inferable from the schema. NEVER fetch 50 "
            "entities to find one.\n"
        )
        target_agent.system_prompt = base_prompt + schema_header + schema_text + id_hint
        self._schema_current_tenant = tenant
        logger.info(
            "Schema inyectado en %s │ tenant=%s │ %d chars",
            label, tenant, len(schema_text),
        )

    def _generar_descripcion_especialista(self, name: str) -> str:
        n = name.lower()
        if "quantum"  in n:
            return (
                "QuantumLeap — almacén de SERIES TEMPORALES HISTÓRICAS. "
                "USAR SOLO si la pregunta menciona explícitamente: histórico, "
                "evolución, tendencia, media, promedio, máximo, mínimo, "
                "agregado, últimas N horas/días/semanas, ayer, anteayer, "
                "entre fechas, desde tal hora. "
                "NO USAR para el valor actual/ahora/última lectura — eso vive "
                "en Orion (numValue de la DeviceMeasurement, actualizado en "
                "tiempo real por cada PATCH). "
                "REQUIERE entity_id canónico (urn:ngsi-ld:...) y attr_name "
                "resueltos previamente por Agente_orion_ld."
            )
        if "mongo"    in n: return "Base de Datos Documental (MongoDB). Logs e historial."
        if "spark"    in n: return "Industrial IoT (Sparkplug). Sensores y datos en tiempo real."
        if "rag"      in n:
            return (
                "Manuales y documentación técnica indexada (PDFs). "
                "USAR SOLO para procedimientos, especificaciones del manual, "
                "normas, EPI, intervalos de mantenimiento. "
                "NO USAR para valores numéricos de entidades concretas — "
                "eso son sensores en vivo, no documentación."
            )
        if "orion"    in n:
            return (
                "Context Broker NGSI-LD (Orion). MANTIENE EL ESTADO ACTUAL de "
                "todas las entidades del data space. USAR PARA: "
                "(a) VALOR ACTUAL de cualquier propiedad de una entidad — "
                "Orion guarda el último numValue + observedAt + unitText "
                "recibido para cada DeviceMeasurement, actualizado en tiempo "
                "real, así que 'cuál es la temperatura/batería/presión/peso "
                "de X ahora' SE RESPONDE AQUÍ con get_entity sobre la medida; "
                "(b) ESTRUCTURA: qué entidades existen, qué componentes tiene "
                "una máquina, a qué nave pertenece, IDs exactos, relaciones; "
                "(c) RESOLUCIÓN de URN canónico para luego pasar a QuantumLeap "
                "(solo en caso histórico). "
                "NO USAR para histórico, medias o tendencias — eso es QuantumLeap."
            )
        if "file"     in n: return "Sistema de Archivos Local."
        if "sql"      in n: return "Base de Datos SQL."
        if "chart"    in n or "engine" in n:
            return (
                "Motor de gráficos temporales. Genera gráficas de series históricas "
                "y devuelve una URL donde el cliente puede descargar el template. "
                "Usar SIEMPRE para: graficar, visualizar, plotear, evolución, tendencia."
            )
        return f"Herramientas de {name}."

    def _crear_herramienta_de_agente(
        self, name: str, agent: FunctionAgent, description: str
    ) -> FunctionTool:
        async def call_specialist_agent(instruccion: str) -> str:
            t_start = time.time()
            log_agent_flow("request", name, instruccion)

            # GUARDA DE ENRUTAMIENTO (determinista): si esta delegación va a
            # documentación (RAG) pero la instrucción es estructural (datos en
            # vivo), no la ejecutamos: devolvemos al Gestor un mensaje que le
            # obliga a re-delegar en el especialista de datos.
            if should_redirect_routing(name, instruccion):
                logger.info(
                    "Routing corregido │ %s ← instrucción estructural mal "
                    "enrutada a documentación │ redirigiendo a datos en vivo",
                    name,
                )
                log_agent_flow(
                    "response", name, "[routing redirect]",
                    duration_ms=(time.time() - t_start) * 1000,
                    metadata={"redirected": True},
                )
                return get_routing_redirect_msg()

            try:
                ctx      = Context(workflow=agent)
                response = await agent.run(instruccion, ctx=ctx)
                result   = _to_text(response)
                record_specialist_output(name, instruccion, result)   # ← NUEVO
                log_agent_flow(
                    "response", name, result,
                    duration_ms=(time.time() - t_start) * 1000,
                    metadata={"chars": len(result)},
                )
                return result
            except Exception as e:
                duration_ms = (time.time() - t_start) * 1000
                err_msg     = str(e)
                if "Max iterations" in err_msg or "max_iterations" in err_msg:
                    short_msg = f"Límite de iteraciones alcanzado en {name}"
                    logger.error(
                        "Especialista %s │ MAX_ITERATIONS │ %.0fms │ %s",
                        name, duration_ms, short_msg,
                    )
                    logger.debug("Detalle traceback", exc_info=True)
                    return (
                        f"[{name}] {short_msg}. "
                        "El agente intentó demasiados pasos sin converger."
                    )
                logger.error(
                    "Especialista %s │ %s │ %.0fms │ %s",
                    name, type(e).__name__, duration_ms, err_msg, exc_info=True,
                )
                return f"Error en {name}: {type(e).__name__}: {err_msg}"

        return FunctionTool.from_defaults(
            fn=call_specialist_agent,
            name=f"Agente_{name}",
            description=description,
        )

    def _obtener_contexto_sesion(self, session_id: str) -> Context:
        if session_id not in self.session_contexts:
            logger.debug("Nueva sesión creada │ %s", session_id)
            self.session_contexts[session_id] = Context(workflow=self.aggregator_agent)
        return self.session_contexts[session_id]

    def _obtener_lock_sesion(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        return self._session_locks[session_id]

    async def procesar_peticion_api(self, data: dict) -> dict:
        request_id = data.get("request_id", f"req_{int(time.time() * 1000)}")
        session_id = data.get("session_id", "default_session")
        user_id    = data.get("user_id",    "-")
        client_id  = data.get("client_id",  "-")

        set_log_context(
            request_id=request_id, session_id=session_id,
            user_id=user_id, client_id=client_id,
        )
        reset_tool_counters()
        reset_specialist_outputs() 

        context = data.get("_context", {})
        # Inyectar tenant por defecto cuando la petición no trae ninguno
        # (terminal, benchmark). En producción siempre llega via headers HTTP.
        if not context.get("ngsild_tenant") and not context.get("x_modelador_tenant"):
            if self.default_tenant:
                context = {**context, "ngsild_tenant": self.default_tenant}
        set_request_context(context)

        input_text = str(
            data.get("input_text") or data.get("message") or data.get("query", "")
        ).strip()
        modality = data.get("modality", "text")

        logger.info("Petición recibida │ modality=%s │ len=%d │ tenant=%s",
                    modality, len(input_text), context.get("ngsild_tenant") or "default")
        logger.debug("Petición input: %s", input_text)

        metrics = RequestMetrics(
            request_id=request_id,
            session_id=session_id,
            provider=self.provider,
            model=self._cost_model_name,
        )
        start_time = time.time()

        try:
            if not self.aggregator_agent:
                metrics.error = "Sistema no inicializado"
                await metrics_collector.record_request(metrics)
                log_conversation(input_text, "", status="error",
                                 error_code="INIT_ERR", modality=modality)
                return self._formatear_error(request_id, "Sistema no inicializado.", "INIT_ERR")

            if not input_text.strip():
                metrics.error = "Mensaje vacío"
                await metrics_collector.record_request(metrics)
                log_conversation(input_text, "", status="error",
                                 error_code="EMPTY_INPUT", modality=modality)
                return self._formatear_error(request_id, "Mensaje vacío.", "EMPTY_INPUT")

            ctx          = self._obtener_contexto_sesion(session_id)
            session_lock = self._obtener_lock_sesion(session_id)

            async with session_lock:
                token_tracker.reset()
                if self._token_counter is not None:
                    try:
                        self._token_counter.reset_counts()
                    except Exception:
                        pass

                # Asegurar schema inyectado SOLO si el tenant cambió o no se
                # ha precargado. Cache hit = rápido, sin log de inyección.
                # En multi inyecta en el especialista de Orion; en single, en
                # el agente único. Esto YA fija el system_prompt correcto
                # (base del modo + schema), por lo que NO lo reseteamos aparte.
                tenant = context.get("ngsild_tenant") or context.get("x_modelador_tenant")
                schema_injected = False
                if tenant and (self.agent_mode == "single" or "orion_ld" in self.specialist_agents):
                    await self._ensure_schema_in_specialist(tenant)
                    schema_injected = (self._schema_current_tenant == tenant)

                # Si no se inyectó schema (sin tenant, o build falló), fijar al
                # menos el prompt base del modo para esta petición.
                if not schema_injected:
                    role = "single" if self.agent_mode == "single" else "aggregator"
                    self.aggregator_agent.system_prompt = get_system_prompt(role, modality=modality)

                try:
                    llm_start = time.time()
                    response  = await self.aggregator_agent.run(input_text, ctx=ctx)
                    metrics.llm_time = time.time() - llm_start

                    raw_text         = _to_text(response)
                    if not raw_text.strip():
                        logger.warning("El agente devolvió respuesta vacía")
                        raw_text = ""

                    # ── ANTI-EVASIÓN ────────────────────────────────────
                    # Si el modelo ofrece/pregunta en vez de actuar y no usó
                    # ninguna herramienta (tools=0), reintentamos UNA sola vez
                    # añadiendo un sufijo imperativo que le obliga a ejecutar.
                    # El detector y el sufijo los aporta el proyecto
                    # (project.behavior_guards); si no hay proyecto cargado,
                    # should_retry_for_dodge devuelve False y esto no se activa.
                    tools_called_so_far = get_tool_call_count()
                    if should_retry_for_dodge(raw_text, tools_called_so_far):
                        logger.warning(
                            "Evasión detectada │ tools=%d │ reintento imperativo único",
                            tools_called_so_far,
                        )
                        retry_input = input_text + get_dodge_retry_suffix()
                        retry_start = time.time()
                        response = await self.aggregator_agent.run(retry_input, ctx=ctx)
                        metrics.llm_time += time.time() - retry_start
                        retry_text = _to_text(response)
                        if retry_text.strip():
                            raw_text = retry_text

                    # antes: build_response_payload(raw_text, modality=modality)
                    response_payload = await render_payload(
                        input_text, get_specialist_outputs(), raw_text, modality, self.llm
                    )
                    final_text   = response_payload["text"]
                    final_speech = response_payload["speech"]
                    final_data   = response_payload["data"]

                    # ── RECONCILIACIÓN DE TOKENS ────────────────────────
                    # El token_tracker directo puede no ver los sub-agentes;
                    # el TokenCountingHandler de LlamaIndex sí. reconcile_metrics
                    # (aportada por el proyecto) toma el máximo por campo. Sin
                    # proyecto cargado, devuelve los totales directos tal cual.
                    token_totals = reconcile_metrics(
                        token_tracker.get_totals(), self._token_counter
                    )
                    metrics.tokens_prompt     = token_totals["prompt_tokens"]
                    metrics.tokens_completion = token_totals["completion_tokens"]
                    metrics.tokens_total      = token_totals["total_tokens"]
                    metrics.num_llm_calls     = token_totals["num_llm_calls"]

                    if metrics.tokens_total == 0 and self._token_counter is not None:
                        try:
                            metrics.tokens_prompt     = self._token_counter.prompt_llm_token_count
                            metrics.tokens_completion = self._token_counter.completion_llm_token_count
                            metrics.tokens_total      = int(metrics.tokens_prompt + metrics.tokens_completion)
                        except Exception:
                            pass

                    if metrics.tokens_total == 0:
                        metrics.tokens_prompt     = int(len(input_text.split()) * 1.3)
                        metrics.tokens_completion = int(len(final_text.split())  * 1.3)
                        metrics.tokens_total      = int(metrics.tokens_prompt + metrics.tokens_completion)
                        logger.debug("Usando estimación de tokens (interceptor sin datos)")

                    metrics.total_time     = time.time() - start_time
                    metrics.estimated_cost = calculate_cost(
                        int(metrics.tokens_prompt),
                        int(metrics.tokens_completion),
                        self.provider,
                        self._cost_model_name,
                    )

                    tool_counters = get_tool_counters()
                    await metrics_collector.record_request(metrics)

                    logger.info(
                        "Petición OK │ %.2fs (LLM %.2fs) │ tokens=%d/%d=%d │ "
                        "calls=%d │ tools=%d(err=%d) │ $%.6f",
                        metrics.total_time, metrics.llm_time,
                        int(metrics.tokens_prompt), int(metrics.tokens_completion),
                        metrics.tokens_total, metrics.num_llm_calls,
                        tool_counters["tools_called"], tool_counters["tools_errors"],
                        metrics.estimated_cost,
                    )

                    log_conversation(
                        question=input_text, answer=final_text,
                        status="success", error_code="", modality=modality,
                        metadata={"llm_calls": metrics.num_llm_calls, **tool_counters},
                    )
                    log_metrics({
                        "request_id":        request_id,
                        "session_id":        session_id,
                        "provider":          self.provider,
                        "model":             self._cost_model_name,
                        "total_time":        round(metrics.total_time, 3),
                        "llm_time":          round(metrics.llm_time, 3),
                        "tokens_prompt":     int(metrics.tokens_prompt),
                        "tokens_completion": int(metrics.tokens_completion),
                        "tokens_total":      metrics.tokens_total,
                        "llm_calls":         metrics.num_llm_calls,
                        "tools_called":      tool_counters["tools_called"],
                        "tools_errors":      tool_counters["tools_errors"],
                        "cost_usd":          round(metrics.estimated_cost, 6),
                        "status":            "success",
                        "tenant":            context.get("ngsild_tenant") or "default",
                    })

                    return {
                        "request_id":    request_id,
                        "status":        "success",
                        "error_code":    "",
                        "error_message": "",
                        "response": {
                            "text":   final_text,
                            "speech": final_speech,
                            "data":   final_data,
                        },
                        "metrics": {
                            "total_time": round(metrics.total_time, 3),
                            "llm_time":   round(metrics.llm_time, 3),
                            "tokens": {
                                "prompt":     int(metrics.tokens_prompt),
                                "completion": int(metrics.tokens_completion),
                                "total":      metrics.tokens_total,
                            },
                            "llm_calls":    metrics.num_llm_calls,
                            "tools_called": tool_counters["tools_called"],
                            "tools_errors": tool_counters["tools_errors"],
                            "cost_usd":     round(metrics.estimated_cost, 6),
                        },
                    }

                except Exception as e:
                    error_str  = str(e)
                    error_type = type(e).__name__
                    metrics.error      = error_str
                    metrics.total_time = time.time() - start_time

                    token_totals = token_tracker.get_totals()
                    metrics.tokens_prompt     = token_totals["prompt_tokens"]
                    metrics.tokens_completion = token_totals["completion_tokens"]
                    metrics.tokens_total      = token_totals["total_tokens"]
                    metrics.num_llm_calls     = token_totals["num_llm_calls"]
                    if metrics.tokens_total > 0:
                        metrics.estimated_cost = calculate_cost(
                            int(metrics.tokens_prompt),
                            int(metrics.tokens_completion),
                            self.provider,
                            self._cost_model_name,
                        )

                    tool_counters = get_tool_counters()
                    await metrics_collector.record_request(metrics)

                    if any(k in error_str.lower() for k in ("content_filter", "content_management_policy")):
                        filter_detail = "contenido filtrado por políticas de seguridad"
                        for keyword, label in (
                            ("self_harm",  "posible autolesión"),
                            ("violence",   "violencia"),
                            ("hate",       "discurso de odio"),
                            ("sexual",     "contenido sexual"),
                        ):
                            if keyword in error_str:
                                filter_detail = f"contenido clasificado como {label} por Azure"
                                break

                        logger.warning("Content filter activado │ %s", filter_detail)
                        log_conversation(
                            question=input_text, answer="", status="error",
                            error_code="CONTENT_FILTER", modality=modality,
                            metadata={"filter_detail": filter_detail, **tool_counters},
                        )
                        return {
                            "request_id": request_id,
                            "status":     "error",
                            "error_code": "CONTENT_FILTER",
                            "error_message": f"Azure Content Filter: {filter_detail}",
                            "response": {
                                "text": (
                                    f"⚠️ **Filtro de Contenido Azure**\n\n"
                                    f"La solicitud fue bloqueada: {filter_detail}.\n\n"
                                    "Prueba a reformular la pregunta o contacta al administrador."
                                ),
                                "speech": f"La solicitud fue bloqueada por el filtro de contenido de Azure: {filter_detail}.",
                                "data":   {"filter_triggered": True},
                            },
                            "metrics": {
                                "total_time": round(metrics.total_time, 3),
                                "llm_time":   round(metrics.llm_time, 3),
                                "tokens": {
                                    "prompt":     int(metrics.tokens_prompt),
                                    "completion": int(metrics.tokens_completion),
                                    "total":      metrics.tokens_total,
                                },
                                "llm_calls":    metrics.num_llm_calls,
                                "tools_called": tool_counters["tools_called"],
                                "tools_errors": tool_counters["tools_errors"],
                                "cost_usd":     round(metrics.estimated_cost, 6),
                            },
                        }

                    if "Max iterations" in error_str or "max_iterations" in error_str:
                        logger.error(
                            "Agente agotó iteraciones │ %.2fs │ tools=%d",
                            metrics.total_time, tool_counters["tools_called"],
                        )
                        logger.debug("Traceback max_iterations", exc_info=True)
                        log_conversation(
                            question=input_text, answer="", status="error",
                            error_code="MAX_ITERATIONS", modality=modality,
                            metadata={"error": "agente no convergió", **tool_counters},
                        )
                        return self._formatear_error(
                            request_id,
                            "El agente agotó el límite de iteraciones sin encontrar respuesta. "
                            "Prueba a reformular la pregunta con más contexto.",
                            "MAX_ITERATIONS",
                        )

                    logger.error(
                        "Error en agente │ %s │ %.2fs │ tools=%d │ %s",
                        error_type, metrics.total_time,
                        tool_counters["tools_called"], error_str, exc_info=True,
                    )
                    log_conversation(
                        question=input_text, answer="", status="error",
                        error_code="AGENT_EXEC_ERR", modality=modality,
                        metadata={"error": error_str, "error_type": error_type, **tool_counters},
                    )
                    return self._formatear_error(request_id, error_str, "AGENT_EXEC_ERR")

        finally:
            clear_log_context()

    def _formatear_error(self, rid: str, msg: str, code: str = "ERROR") -> dict:
        return {
            "request_id":    rid,
            "status":        "error",
            "error_code":    code,
            "error_message": msg,
            "response": {
                "speech": "Ha ocurrido un error técnico.",
                "text":   msg,
                "data":   {},
            },
        }

    async def stream_respuesta_generador(
        self,
        mensaje:    str,
        session_id: str         = "streamlit_default",
        context:    dict | None = None,
    ):
        """
        Genera la respuesta como SSE.

        NOTA sobre el streaming: el agente (FunctionAgent.run) devuelve la
        respuesta COMPLETA antes de que podamos emitir nada, así que esto es
        troceado a posteriori, no streaming token-a-token real. Se trocea para
        que el cliente pueda renderom progresivamente, pero el tiempo hasta el
        primer chunk es el de la respuesta completa. Para streaming real habría
        que consumir handler.stream_events() / AgentStream de LlamaIndex y
        emitir cada delta; queda pendiente como mejora futura.
        """
        request_id = f"stream_{int(time.time()*1000)}"
        set_log_context(session_id=session_id, request_id=request_id)
        reset_tool_counters()
        reset_specialist_outputs() 

        # Inyectar tenant por defecto si la petición no trae ninguno.
        ctx = dict(context or {})
        if not ctx.get("ngsild_tenant") and not ctx.get("x_modelador_tenant"):
            if self.default_tenant:
                ctx["ngsild_tenant"] = self.default_tenant
        set_request_context(ctx)

        tenant = ctx.get("ngsild_tenant") or ctx.get("x_modelador_tenant")
        if tenant and (self.agent_mode == "single" or "orion_ld" in self.specialist_agents):
            await self._ensure_schema_in_specialist(tenant)

        logger.info("Stream iniciado │ len=%d │ tenant=%s",
                    len(mensaje), tenant or "default")
        try:
            run_ctx      = self._obtener_contexto_sesion(session_id)
            session_lock = self._obtener_lock_sesion(session_id)
            async with session_lock:
                try:
                    response    = await self.aggregator_agent.run(mensaje, ctx=run_ctx)
                    texto_final = _to_text(response)

                    # Render por modalidad (texto = Markdown) desde las salidas
                    # FIELES de los especialistas, para no servir el resumen
                    # colapsado del Gestor. Su propio try: si el render falla,
                    # seguimos con texto_final y el stream no se rompe.
                    try:
                        rendered = await render_payload(
                            mensaje, get_specialist_outputs(), texto_final, "text", self.llm
                        )
                        texto_final = rendered.get("text") or texto_final
                    except Exception as e_render:
                        logger.warning("Render en stream falló (ignorado): %s", e_render)

                    log_conversation(
                        question=mensaje, answer=texto_final,
                        status="success", modality="stream",
                        metadata=get_tool_counters(),
                    )
                except Exception as e:
                    texto_final = f"❌ Error: {str(e)}"
                    logger.error(
                        "Error en stream │ %s: %s", type(e).__name__, e, exc_info=True
                    )
                    log_conversation(
                        question=mensaje, answer="", status="error",
                        error_code="STREAM_ERR", modality="stream",
                        metadata={"error": str(e), **get_tool_counters()},
                    )

            chunk_size = 80
            for i in range(0, len(texto_final), chunk_size):
                yield f"data: {json.dumps({'text': texto_final[i:i+chunk_size]})}\n\n"
                await asyncio.sleep(0.005)
            yield f"data: {json.dumps({'text': '', 'done': True})}\n\n"
        finally:
            clear_log_context()


    async def get_metrics_stats(self) -> dict:
        return await metrics_collector.get_stats()

    async def get_session_metrics(self, session_id: str) -> dict:
        return await metrics_collector.get_session_stats(session_id)

    async def cerrar(self):
        for client in self._active_clients:
            if hasattr(client, "aclose"):
                try:
                    await asyncio.wait_for(client.aclose(), timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError, Exception) as e:
                    logger.debug("Cierre cliente (ignorado): %s", e)
        self._active_clients.clear()
        logger.info("Todas las conexiones MCP cerradas")

