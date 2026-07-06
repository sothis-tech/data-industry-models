# servers/sparkplug_server.py
# -*- coding: utf-8 -*-

import argparse
import json
import os
import sys  # <--- CRÍTICO para logs en stderr
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP

# Este servidor necesita la librería 'requests'
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

mcp = FastMCP('sparkplug-server')

# =======================
# Configuración del Servidor
# =======================

# URL base de la API REST (Soporta variable de entorno para flexibilidad)
API_BASE_URL = os.getenv("SPARKPLUG_API_URL", "http://localhost:5000/api")
DEFAULT_TIMEOUT = 10.0
BROWSE_TIMEOUT = 30.0  # Explorar puede ser más lento
JSON_HEADERS = {"Content-Type": "application/json"}

# =======================
# Helpers
# =======================

def _log(msg: str):
    """Escribe logs en stderr para no romper el protocolo STDIO JSON-RPC."""
    print(f"[Sparkplug-Server] {msg}", file=sys.stderr)

def _check_deps():
    if not REQUESTS_AVAILABLE:
        raise Exception("Dependencia faltante: 'requests'. Por favor, instálala (ej: pip install requests)")

def _handle_request_exception(e: requests.RequestException, url: str) -> str:
    """Helper para formatear errores de requests."""
    if e.response is not None:
        try:
            api_error = e.response.json()
            return f"ERROR: La API devolvió un error {e.response.status_code}: {json.dumps(api_error)}"
        except json.JSONDecodeError:
            return f"ERROR: La API devolvió un error {e.response.status_code}: {e.response.text}"
    elif isinstance(e, requests.exceptions.ConnectionError):
        return f"ERROR: No se pudo conectar a la API del middleware en {url}. ¿Está el contenedor Docker corriendo?"
    elif isinstance(e, requests.exceptions.Timeout):
        return f"ERROR: Timeout esperando respuesta de la API en {url}."
    else:
        return f"ERROR: Fallo en la solicitud a la API. Detalle: {str(e)}"

# =======================
# Herramientas (Tools)
# =======================

@mcp.tool(name="sparkplug_list_active_servers")
def sparkplug_list_active_servers() -> str:
    """Lista los servidores OPC UA monitoreados activamente."""
    _check_deps()
    try:
        url = f"{API_BASE_URL}/servers"
        r = requests.get(url, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_connect_server")
def sparkplug_connect_server(url: str) -> str:
    """Añade y conecta un nuevo servidor OPC UA."""
    _check_deps()
    if not url or not url.startswith("opc.tcp://"):
        return "ERROR: 'url' es obligatoria y debe empezar con 'opc.tcp://'"
    try:
        api_url = f"{API_BASE_URL}/servers"
        payload = {"url": url}
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_disconnect_server")
def sparkplug_disconnect_server(url: str) -> str:
    """Desconecta y elimina un servidor OPC UA."""
    _check_deps()
    if not url or not url.startswith("opc.tcp://"):
        return "ERROR: 'url' es obligatoria y debe empezar con 'opc.tcp://'"
    try:
        api_url = f"{API_BASE_URL}/servers"
        payload = {"url": url}
        r = requests.delete(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_browse_opcua_server")
def sparkplug_browse_opcua_server(url: str, max_depth: int = 2) -> str:
    """Explora estructura general (Top Level)."""
    _check_deps()
    if not url or not url.startswith("opc.tcp://"):
        return "ERROR: 'url' debe empezar con 'opc.tcp://'"
    try:
        api_url = f"{API_BASE_URL}/browse" 
        payload = {"url": url, "maxDepth": int(max_depth)}
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=BROWSE_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_discover_node_children")
def sparkplug_discover_node_children(url: str, node_id: str = "root", include_value: bool = False, limit: int = 100) -> str:
    """Descubre hijos de un nodo específico (Drill-down)."""
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/discover"
        params = {
            "url": url,
            "nodeId": node_id,
            "value": "1" if include_value else "0",
            "limit": limit
        }
        r = requests.get(api_url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_subscribe_to_nodes")
def sparkplug_subscribe_to_nodes(url: str, node_ids: List[str]) -> str:
    """Suscribirse a nodos."""
    _check_deps()
    if not url or not node_ids or not isinstance(node_ids, list):
        return "ERROR: Se requiere 'url' y 'node_ids' (lista)."
    try:
        api_url = f"{API_BASE_URL}/subscribe"
        payload = {"url": url, "nodeIds": node_ids}
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_unsubscribe_from_nodes")
def sparkplug_unsubscribe_from_nodes(url: str, node_ids: List[str]) -> str:
    """Des-suscribirse de nodos."""
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/unsubscribe"
        payload = {"url": url, "nodeIds": node_ids}
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_write_variable")
def sparkplug_write_variable(url: str, node_id: str, value: Any, dtype: Optional[str] = None) -> str:
    """Escribir valor único."""
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/write"
        payload = {"url": url, "nodeId": node_id, "value": value}
        if dtype: payload["type"] = dtype
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_write_batch")
def sparkplug_write_batch(url: str, writes: List[Dict[str, Any]]) -> str:
    """Escritura en lote."""
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/write-batch"
        payload = {"url": url, "writes": writes}
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

# ═══════════════════════════════════════════════════════════════════════════════
# NUEVAS HERRAMIENTAS - Real-time & Hierarchy
# ═══════════════════════════════════════════════════════════════════════════════

@mcp.tool(name="sparkplug_get_hierarchy")
def sparkplug_get_hierarchy() -> str:
    """
    Obtiene la jerarquía de Sparkplug B (groups/edges/devices).
    Retorna la estructura completa de datos en tiempo real.
    Útil para descubrir qué grupos, edges y devices están disponibles.
    """
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/hierarchy"
        r = requests.get(api_url, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_get_last_values")
def sparkplug_get_last_values(group: str = "", edge: str = "", device: str = "") -> str:
    """
    Obtiene los últimos valores de métricas (cache en memoria).
    Parámetros opcionales para filtrar:
    - group: Filtrar por grupo Sparkplug
    - edge: Filtrar por edge node
    - device: Filtrar por device específico
    
    Si no se especifican filtros, retorna todos los valores disponibles.
    Este método es MUY RÁPIDO (usa cache) - preferible a drill-down cuando
    solo necesitas valores actuales.
    """
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/last"
        params = {}
        if group:
            params["group"] = group
        if edge:
            params["edge"] = edge
        if device:
            params["device"] = device
        
        r = requests.get(api_url, params=params if params else None, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(name="sparkplug_rebirth")
def sparkplug_rebirth(group: str, edge: str, device: str = "") -> str:
    """
    Solicita un REBIRTH (NCMD/DCMD) para refrescar el estado completo.
    
    REBIRTH es un comando Sparkplug B que fuerza al edge/device a reenviar
    su estado completo (NBIRTH/DBIRTH), útil cuando:
    - Se perdieron mensajes y el estado está desincronizado
    - Se necesita verificar la estructura completa de métricas
    - Debugging o troubleshooting
    
    Comportamiento:
    - Si device está vacío: REBIRTH de Edge (NCMD) - refrescar todo el edge
    - Si device está especificado: REBIRTH de Device (DCMD) - solo ese device
    
    Parámetros:
    - group: Grupo Sparkplug B (ej: "AUTO", "Production")
    - edge: Identificador del edge node
    - device: (Opcional) Identificador del device específico
    """
    _check_deps()
    try:
        api_url = f"{API_BASE_URL}/rebirth"
        payload = {"group": group, "edge": edge}
        if device:
            payload["device"] = device
        
        r = requests.post(api_url, json=payload, headers=JSON_HEADERS, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        return json.dumps(r.json(), ensure_ascii=False)
    except requests.RequestException as e:
        return _handle_request_exception(e, api_url)
    except Exception as e:
        return f"ERROR: {e}"

# =======================
# MAIN (Dual Mode)
# =======================

if __name__ == "__main__":
    import argparse
    
    # Logs a STDERR
    _log("🚀 Iniciando servidor MCP Sparkplug...")
    
    if not REQUESTS_AVAILABLE:
        _log("❌ ERROR CRÍTICO: Librería 'requests' no encontrada.")
        sys.exit(1)
    
    # Test de conexión al Middleware (API)
    # Lo hacemos informativo, no bloqueante (por si el docker levanta lento)
    try:
        requests.get(f"{API_BASE_URL}/servers", timeout=2.0)
        _log(f"✅ Middleware detectado en {API_BASE_URL}")
    except Exception as e:
        _log(f"⚠️ AVISO: No se detecta el middleware en {API_BASE_URL}. ¿Docker corriendo? ({e})")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", type=str, default="stdio", choices=["sse", "stdio"])
    parser.add_argument("--port", type=int, default=8000, help="Puerto del servidor (solo SSE)")
    args = parser.parse_args()
    
    if args.server_type == "stdio":
        # --- MODO STDIO (Producción) ---
        try:
            mcp.run(transport="stdio")
        except Exception as e:
            _log(f"❌ Error fatal en MCP STDIO: {e}")
            sys.exit(1)
            
    else:
        # --- MODO SSE (Debug) ---
        _log(f"📡 Arrancando modo DEBUG SSE en puerto {args.port}...")
        try:
            import uvicorn
            original_config_init = uvicorn.Config.__init__
            def patched_config_init(self, *u_args, **u_kwargs):
                _log(f"🔒 BLOQUEO SSE: Forzando puerto {args.port}")
                u_kwargs["port"] = args.port
                u_kwargs["host"] = "0.0.0.0"
                original_config_init(self, *u_args, **u_kwargs)
            uvicorn.Config.__init__ = patched_config_init
            
            mcp.run(transport="sse")
        except ImportError:
            _log("❌ Error: Para modo SSE necesitas 'uvicorn'.")
            sys.exit(1)