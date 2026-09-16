from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import uvicorn
import yaml
import os
import requests
import re

# Importamos tu simulador y las utilidades de opcua
from opcua import ua
from opcua_sim import SpaceBuilder, Server, DATA_TYPE_MAP, NUMERIC_TYPES, Updater

# --- ESTADO EN MEMORIA Y PERSISTENCIA ---
STATE_FILE = "plant_state.yaml"

active_updaters = []
active_devices = []
current_state = {
    "server": {"namespace_uri": "urn:ConfigurablePlant:OPCUA"},
    "nodes": []
}

def save_state():
    """Vuelca el estado actual al archivo YAML."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        yaml.dump(current_state, f, allow_unicode=True, sort_keys=False)

def load_state():
    """Carga el estado desde el archivo YAML si existe."""
    global current_state
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            if loaded:
                current_state = loaded

# --- CONFIGURACIÓN DE FIWARE VIA VARIABLES DE ENTORNO ---
IOTA_BASE_URL = os.getenv("IOTA_URL", "http://iotagent-opcua:4041/iot")
DEFAULT_TENANT = os.getenv("FIWARE_TENANT", "ibermot")
FIWARE_SERVICEPATH = os.getenv("FIWARE_SERVICEPATH", "/")

def get_fiware_headers(tenant: str):
    """
    Genera dinámicamente las cabeceras requeridas por FIWARE.
    Encapsularlo aquí evita duplicar código y facilita añadir tokens de seguridad (OAuth2/Keyrock) en el futuro.
    """
    return {
        "fiware-service": tenant,
        "fiware-servicepath": FIWARE_SERVICEPATH,
        "Content-Type": "application/json"
    }

# --- MODELOS DE DATOS ---
class CreateDevicePayload(BaseModel):
    name: str

class AddVariablePayload(BaseModel):
    browse_name: str
    data_type: str
    initial_value: str
    simulation: Optional[Dict[str, Any]] = None

class OPCUAConnectPayload(BaseModel):
    url: str

class DeleteNodePayload(BaseModel):
    node_id: str

# --- MODELOS PARA FIWARE ---
class FiwareConfig(BaseModel):
    orion_url: str = "http://localhost:1026"
    iota_url: str = "http://localhost:4041"
    tenant: str = "ibermot"
    service_path: str = "/"
    apikey: str = "iot-ibermot"
    context_url: str = "http://context-provider/industrial-oven-context.jsonld"

class FiwareMappingPayload(BaseModel):
    config: FiwareConfig
    device_id: str          # Identificador interno para el IoT Agent
    entity_id: str          # urn:ngsi-ld:Device:001
    entity_type: str        # Device
    opcua_endpoint: str     # opc.tcp://<tu-ip>:5679
    opcua_node_id: str      # ns=2;s=Line1.Temperature
    attribute_name: str     # temperature
    attribute_type: str     # Number / Property

class FiwareEntityQuery(BaseModel):
    config: FiwareConfig
    entity_type: str = None

# --- CICLO DE VIDA DE LA APP ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Instanciamos el servidor base
    server = Server()
    server.set_endpoint("opc.tcp://0.0.0.0:5679")
    server.set_server_name("Mock OPC UA - Smart Machine")
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
    server.start()
    app.state.opc_server = server
    
    print("[API] Servidor OPC UA base iniciado en opc.tcp://0.0.0.0:5679")
    
    # 2. RECUPERACIÓN DE ESTADO (PERSISTENCIA)
    load_state()
    if current_state.get("nodes"):
        ns = current_state.get("server", {}).get("namespace_uri", "urn:ConfigurablePlant:OPCUA")
        server.register_namespace(ns)
        
        try:
            builder = SpaceBuilder(server, current_state)
            new_updaters = builder.build()
            
            for u in new_updaters:
                u.start()
                active_updaters.append(u)
                
            for node in current_state.get("nodes", []):
                active_devices.append(node.get("browse_name", "Desconocido"))
                
            print(f"[API] Estado recuperado de {STATE_FILE}. {len(active_devices)} nodos cargados.")
        except Exception as e:
            print(f"[API] Error recuperando el estado guardado: {e}")
            
    yield
    
    server.stop()
    print("[API] Servidor OPC UA detenido.")

app = FastAPI(title="OPC UA Simulator Manager", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ENDPOINTS ---

@app.get("/api/devices")
def get_devices():
    return {"status": "ok", "devices": active_devices}

@app.get("/api/devices/{device_name}/tree")
def get_device_tree(request: Request, device_name: str):
    """Explora recursivamente un nodo raíz y devuelve todo su árbol de variables."""
    server = getattr(request.app.state, "opc_server", None)
    if not server: raise HTTPException(status_code=500, detail="Servidor inactivo.")

    try:
        objects_node = server.get_objects_node()
        target_node = next((c for c in objects_node.get_children() if c.get_browse_name().Name == device_name), None)
        if not target_node: raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")

        def build_node_tree(node):
            node_class = node.get_node_class()
            result = {
                "name": node.get_browse_name().Name,
                "node_id": node.nodeid.to_string(),
                "class": node_class.name,
                "children": []
            }
            if node_class == ua.NodeClass.Variable:
                try:
                    val = node.get_value()
                    result["value"] = round(val, 4) if isinstance(val, float) else str(val)
                    result["type"] = node.get_data_type_as_variant_type().name
                except Exception:
                    result["value"] = "Error"
                    result["type"] = "Desconocido"

            for child in node.get_children():
                result["children"].append(build_node_tree(child))
            return result

        return {"status": "ok", "tree": build_node_tree(target_node)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload-yaml")
async def upload_yaml(request: Request, file: UploadFile = File(...)):
    server = getattr(request.app.state, "opc_server", None)
    if not server: raise HTTPException(status_code=500, detail="Servidor inactivo.")

    try:
        content = await file.read()
        yaml_config = yaml.safe_load(content)
        
        global current_state, active_updaters, active_devices

        # 1. Asegurarnos de que el nuevo YAML tiene la cabecera del server para que SpaceBuilder no falle
        if "server" not in yaml_config:
            ns = current_state.get("server", {}).get("namespace_uri", "urn:ConfigurablePlant:OPCUA")
            yaml_config["server"] = {"namespace_uri": ns}

        # 2. Inyectar en el servidor vivo SOLO los nodos del archivo recién subido
        server.register_namespace(yaml_config["server"]["namespace_uri"]) 
        builder = SpaceBuilder(server, yaml_config)
        new_updaters = builder.build()
        
        for u in new_updaters:
            u.start()
            active_updaters.append(u)
            
        # 3. PERSISTENCIA CORRECTA: Fusionar (Merge) los nuevos nodos en el estado global
        # Aseguramos que current_state tiene la lista de nodos inicializada
        current_state.setdefault("nodes", [])
        
        # Obtenemos los nombres de los dispositivos que ya existen para no duplicarlos en la lista
        existing_node_names = [n.get("browse_name") for n in current_state["nodes"]]

        for node in yaml_config.get("nodes", []):
            bname = node.get("browse_name")
            
            # Solo añadimos al estado si es un nodo raíz nuevo
            if bname not in existing_node_names:
                current_state["nodes"].append(node)
                
            # Lo añadimos a la lista de la interfaz de React si no estaba
            if bname not in active_devices:
                active_devices.append(bname)

        # 4. Guardar el estado acumulado
        save_state()
            
        return {"status": "success", "message": "Nodos inyectados y combinados correctamente en el estado global."}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))
    
@app.post("/api/devices")
def create_empty_device(request: Request, payload: CreateDevicePayload):
    server = getattr(request.app.state, "opc_server", None)
    if not server: raise HTTPException(status_code=500, detail="Servidor inactivo.")
    
    try:
        idx = server.register_namespace(current_state["server"]["namespace_uri"])
        objects_node = server.get_objects_node()
        
        if any(c.get_browse_name().Name == payload.name for c in objects_node.get_children()):
            raise HTTPException(status_code=400, detail="El dispositivo ya existe.")
        
        objects_node.add_object(idx, payload.name)
        active_devices.append(payload.name)
        
        # PERSISTENCIA: Añadimos el nuevo nodo vacío al estado
        current_state.setdefault("nodes", []).append({
            "kind": "Object",
            "browse_name": payload.name,
            "children": []
        })
        save_state()
        
        return {"status": "success", "message": "Dispositivo creado con éxito."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/devices/{device_name}/variables")
def add_variable_to_device(request: Request, device_name: str, payload: AddVariablePayload):
    server = getattr(request.app.state, "opc_server", None)
    if not server: raise HTTPException(status_code=500, detail="Servidor inactivo.")
        
    try:
        objects_node = server.get_objects_node()
        parent_node = next((c for c in objects_node.get_children() if c.get_browse_name().Name == device_name), None)
        if not parent_node: raise HTTPException(status_code=404, detail="Dispositivo no encontrado.")
            
        idx = parent_node.nodeid.NamespaceIndex
        dtype = DATA_TYPE_MAP.get(payload.data_type, DATA_TYPE_MAP["String"])
        
        raw_val = payload.initial_value
        if dtype in NUMERIC_TYPES:
            try:
                val = float(raw_val) if "Float" in payload.data_type or "Double" in payload.data_type else int(raw_val)
            except ValueError:
                val = 0.0 if "Float" in payload.data_type or "Double" in payload.data_type else 0
        elif payload.data_type == "Boolean":
            val = str(raw_val).lower() in ("true", "1", "yes")
        else:
            val = str(raw_val)
            
        val_variant = ua.Variant(val, dtype)
        new_var = parent_node.add_variable(idx, payload.browse_name, val_variant, dtype)
        new_var.set_writable(True)
        
        
        if payload.simulation and payload.simulation.get("mode") != "none":
            global active_updaters
            up = Updater(node=new_var, dtype=dtype, sim_cfg=payload.simulation, name=f"{payload.browse_name}-ManualUpdater")
            up.start()
            active_updaters.append(up)
            
        # PERSISTENCIA: Añadimos la variable a la configuración del dispositivo padre
        device_cfg = next((n for n in current_state.get("nodes", []) if n.get("browse_name") == device_name), None)
        if device_cfg is not None:
            new_var_cfg = {
                "kind": "Variable",
                "browse_name": payload.browse_name,
                "data_type": payload.data_type,
                "initial": raw_val,
            }
            if payload.simulation and payload.simulation.get("mode") != "none":
                new_var_cfg["simulation"] = payload.simulation
                
            device_cfg.setdefault("children", []).append(new_var_cfg)
            save_state()
        
        return {"status": "success", "message": "Variable añadida."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/opcua/node")
def delete_opcua_node(request: Request, payload: DeleteNodePayload):
    server = getattr(request.app.state, "opc_server", None)
    if not server: 
        raise HTTPException(status_code=500, detail="Servidor inactivo.")

    try:
        # SALVAVIDAS: Si el string viene sucio (ej: "NumericNodeId(ns=2;i=6)"), lo limpiamos
        clean_node_id = payload.node_id
        if clean_node_id.startswith(("NumericNodeId(", "StringNodeId(")):
            match = re.search(r'\((.*?)\)', clean_node_id)
            if match:
                clean_node_id = match.group(1)

        # Usamos el string limpio
        node_to_delete = server.get_node(clean_node_id)
        
        try:
            browse_name_to_remove = node_to_delete.get_browse_name().Name
        except Exception:
            browse_name_to_remove = None

        server.delete_nodes([node_to_delete])
        
        if browse_name_to_remove:
            state_changed = False
            for device in current_state.get("nodes", []):
                children = device.get("children", [])
                original_len = len(children)
                
                device["children"] = [c for c in children if c.get("browse_name") != browse_name_to_remove]
                
                if len(device["children"]) < original_len:
                    state_changed = True
            
            if state_changed:
                save_state()

        return {"status": "success", "message": f"Nodo {clean_node_id} eliminado correctamente del simulador."}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"No se pudo eliminar el nodo: {str(e)}")

# --- ENDPOINTS FIWARE (PROXY) ---

@app.post("/api/fiware/types")
def get_fiware_types(config: FiwareConfig):
    """Obtiene la lista de tipos disponibles en el Tenant actual de Orion-LD."""
    headers = {"Accept": "application/json"}
    if config.tenant: headers["NGSILD-Tenant"] = config.tenant
    if config.service_path: headers["NGSILD-Path"] = config.service_path
        
    try:
        r = requests.get(f"{config.orion_url}/ngsi-ld/v1/types", headers=headers, timeout=5)
        r.raise_for_status()
        data = r.json()
        # En NGSI-LD, la lista de tipos viene dentro de un array llamado "typeList"
        types = data.get("typeList", [])
        return {"status": "success", "types": types}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error obteniendo tipos: {str(e)}")

# --- OBTENER ENTIDADES POR TIPO ---
@app.post("/api/fiware/entities")
def get_fiware_entities(payload: FiwareEntityQuery):
    """Obtiene las entidades, filtrando por tipo si se especifica."""
    headers = {"Accept": "application/json"}
    if payload.config.tenant: headers["NGSILD-Tenant"] = payload.config.tenant
    if payload.config.service_path: headers["NGSILD-Path"] = payload.config.service_path
        
    # Subimos el límite al máximo permitido por FIWARE (1000)
    params = {"limit": 1000}
    
    if payload.entity_type:
        params["type"] = payload.entity_type
    else:
        params["idPattern"] = ".*" # Por si se llama a ciegas
        
    try:
        r = requests.get(f"{payload.config.orion_url}/ngsi-ld/v1/entities", params=params, headers=headers, timeout=10)
        r.raise_for_status()
        return {"status": "success", "entities": r.json()}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error en Orion-LD: {str(e)}")

@app.post("/api/fiware/provision")
def provision_iota_device(payload: FiwareMappingPayload):
    """Registra un dispositivo simulando la estructura estricta NGSI-LD del IoT Agent OPC UA."""
    
    # 1. Cabeceras estrictas NGSI-LD (Como en tu cURL)
    headers = {
        "fiware-service": payload.config.tenant,
        "fiware-servicepath": payload.config.service_path,
        "Content-Type": "application/ld+json",
        "Link": f'<{payload.config.context_url}>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'
    }
    
    # 2. Recrear el payload exacto para el IOTA OPC-UA
    iota_payload = {
        "devices": [
            {
                "device_id": payload.device_id,
                "entity_name": payload.entity_id,
                "entity_type": payload.entity_type,
                "apikey": payload.config.apikey,
                "service": payload.config.tenant,
                "subservice": payload.config.service_path,
                "@context": [
                    payload.config.context_url
                ],
                "attributes": [
                    {
                        "name": payload.attribute_name,
                        "type": "Property" # En NGSI-LD suele ser Property
                    }
                ],
                "internal_attributes": {
                    "contexts": [
                        {
                            "id": payload.device_id,
                            "type": payload.entity_type,
                            "mappings": [
                                {
                                    "ocb_id": payload.attribute_name,
                                    "opcua_id": payload.opcua_node_id,
                                    "object_id": payload.attribute_name,
                                    "inputArguments": []
                                }
                            ]
                        }
                    ]
                },
                "endpoint": payload.opcua_endpoint
            }
        ]
    }
    
    try:
        r = requests.post(f"{payload.config.iota_url}/iot/devices", json=iota_payload, headers=headers, timeout=5)
        r.raise_for_status()
        return {"status": "success", "message": "Vinculación creada en el IoT Agent."}
    except requests.exceptions.HTTPError as e:
        error_msg = e.response.text if e.response else "Sin detalles"
        print(f"Error IOTA: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Error en IoT Agent: {error_msg}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error conectando a IoT Agent: {str(e)}")
        
@app.post("/api/fiware/entities/{entity_id}")
def get_fiware_entity_details(entity_id: str, config: FiwareConfig):
    """Obtiene los detalles (atributos) de una entidad específica de Orion-LD."""
    headers = {"Accept": "application/json"}
    if config.tenant: headers["NGSILD-Tenant"] = config.tenant
    if config.service_path: headers["NGSILD-Path"] = config.service_path
        
    try:
        r = requests.get(f"{config.orion_url}/ngsi-ld/v1/entities/{entity_id}", headers=headers, timeout=5)
        r.raise_for_status()
        return {"status": "success", "entity": r.json()}
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Error Orion-LD: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/opcua/explore")
def explore_external_opcua(payload: OPCUAConnectPayload):
    """Se conecta a cualquier servidor OPC UA por IP y extrae su árbol."""
    from opcua import Client, ua
    client = Client(payload.url)
    try:
        client.connect()
        objects = client.get_objects_node()

        def build_tree(node, depth=0):
            if depth > 4: 
                return None
                
            node_class = node.get_node_class()
            res = {
                "name": node.get_browse_name().Name,
                "node_id": node.nodeid.to_string(), 
                "class": node_class.name,
                "children": []
            }
            
            if node_class in (ua.NodeClass.Object, ua.NodeClass.Variable):
                try:
                    for child in node.get_children():
                        child_tree = build_tree(child, depth + 1)
                        if child_tree:
                            res["children"].append(child_tree)
                except Exception:
                    pass
            return res

        tree = build_tree(objects)
        return {"status": "success", "tree": tree}
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error conectando a {payload.url}: {str(e)}")
    finally:
        try:
            client.disconnect()
        except:
            pass
# --- ENDPOINTS DE GESTIÓN DEL IOT AGENT ---

@app.get("/api/iotagent/devices")
def get_iotagent_devices(tenant: str = DEFAULT_TENANT):
    """
    Obtiene la lista de dispositivos provisionados filtrando por el tenant 
    recibido como Query Parameter (?tenant=nombre_tenant).
    """
    try:
        response = requests.get(
            f"{IOTA_BASE_URL}/devices", 
            headers=get_fiware_headers(tenant), 
            timeout=5.0
        )
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"IoT Agent respondió con error {response.status_code} para el tenant '{tenant}'."
            )
        
        data = response.json()
        return data.get("devices", [])
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"No se pudo establecer comunicación con el IoT Agent en {IOTA_BASE_URL}: {e}"
        )


@app.delete("/api/iotagent/devices/{device_id}")
def delete_iotagent_device(device_id: str, tenant: str = DEFAULT_TENANT):
    """
    Elimina un dispositivo específico del IoT Agent en el tenant indicado.
    """
    try:
        response = requests.delete(
            f"{IOTA_BASE_URL}/devices/{device_id}", 
            headers=get_fiware_headers(tenant), 
            timeout=5.0
        )
        
        if response.status_code not in (200, 204):
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"El IoT Agent rechazó la eliminación del dispositivo {device_id} en el tenant '{tenant}'."
            )
            
        return {
            "status": "success", 
            "message": f"Dispositivo {device_id} eliminado correctamente del tenant '{tenant}'."
        }
        
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=503, 
            detail=f"Error de red al intentar borrar el dispositivo: {e}"
        )
        
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)