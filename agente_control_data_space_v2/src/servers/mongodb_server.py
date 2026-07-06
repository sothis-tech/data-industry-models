# servers/mongodb_server.py

import argparse
import json
import os
import re
import sys
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Union
from mcp.server.fastmcp import FastMCP

try:
    from pymongo import MongoClient
    from pymongo.errors import ConnectionFailure, OperationFailure, DuplicateKeyError
    from bson import ObjectId
    from bson.errors import InvalidId
    from bson.json_util import dumps as bson_dumps, RELAXED_JSON_OPTIONS, CANONICAL_JSON_OPTIONS
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False

mcp = FastMCP('mongodb-server')

# Configuración de MongoDB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DEFAULT_DATABASE = "demo"

# Cliente MongoDB global
mongo_client = None
current_db = None

# =======================
# Helpers genéricos
# =======================

def _log(msg: str):
    """Escribe logs en stderr para no romper el protocolo STDIO JSON-RPC."""
    print(f"[MongoDB] {msg}", file=sys.stderr)

def _maybe_parse_json(value: Any) -> Any:
    if isinstance(value, str):
        s = value.strip()
        try:
            return json.loads(s)
        except Exception:
            return value
    return value

def _normalize_sort(sort_obj: Any) -> Optional[List[Tuple[str, int]]]:
    sort_obj = _maybe_parse_json(sort_obj)
    if not sort_obj:
        return None
    if isinstance(sort_obj, list):
        out = []
        for item in sort_obj:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                k, v = item
                vv = int(v) if isinstance(v, str) and v in ("1", "-1") else (1 if v == 1 else -1)
                out.append((k, vv))
        return out or None
    if isinstance(sort_obj, dict):
        out = []
        for k, v in sort_obj.items():
            if isinstance(v, str):
                v = int(v) if v in ("1", "-1") else v
            vv = 1 if v == 1 else -1
            out.append((k, vv))
        return out or None
    return None

_OID_CALL_RE = re.compile(r'ObjectId\(\s*"[0-9a-fA-F]{24}"\s*\)')

def _replace_objectid_calls(s: str) -> str:
    def _to_ejson(m):
        hexid = re.search(r'"([0-9a-fA-F]{24})"', m.group(0)).group(1)
        return f'{{"$oid":"{hexid}"}}'
    return _OID_CALL_RE.sub(_to_ejson, s)

def _normalize_stage_key(stage: dict) -> dict:
    if not isinstance(stage, dict) or len(stage) != 1:
        return stage
    k, v = next(iter(stage.items()))
    if not k.startswith("$") and k.lower() in {"match","group","sort","project","lookup","unwind","limit"}:
        return {f"${k.lower()}": v}
    return stage

def _ensure_list_pipeline(pipeline: Any) -> List[Dict]:
    parsed = _maybe_parse_json(pipeline)
    if isinstance(pipeline, str) and isinstance(parsed, str):
        fixed = _replace_objectid_calls(pipeline)
        try:
            parsed = json.loads(fixed)
        except Exception:
            raise ValueError(
                "El 'pipeline' recibido es una cadena no parseable. "
                "Envía JSON válido (sin JSON embebido en strings) y con etapas tipo $match/$group/etc."
            )
    
    if isinstance(parsed, dict):
        pipe = [parsed]
    elif isinstance(parsed, list):
        for i, stage in enumerate(parsed):
            if not isinstance(stage, dict):
                raise ValueError(f"Cada etapa del pipeline debe ser un objeto JSON. Etapa {i} es de tipo {type(stage).__name__}.")
        pipe = parsed
    else:
        raise ValueError(f"'pipeline' debe ser lista o dict (o string JSON). Recibido tipo: {type(parsed).__name__}.")
    
    pipe = [_normalize_stage_key(st) for st in pipe]
    
    for stage in pipe:
        if "$group" in stage and isinstance(stage["$group"], dict):
            grp = stage["$group"]
            for k, v in list(grp.items()):
                if k == "_id":
                    continue
                if isinstance(v, list) and len(v) == 1 and isinstance(v[0], dict) and "$push" in v[0]:
                    grp[k] = v[0]
                    stage.setdefault("__fixes_applied__", []).append("group_push_array_unwrapped")
    return pipe

def _is_24hex(s: Any) -> bool:
    if isinstance(s, str) and len(s) == 24:
        try:
            int(s, 16)
            return True
        except Exception:
            return False
    return False

def _convert_ids_in_query(q: Any) -> Any:
    if isinstance(q, dict):
        out = {}
        for k, v in q.items():
            if isinstance(v, (dict, list)):
                out[k] = _convert_ids_in_query(v)
            else:
                if (k == "_id" or k.endswith("_id")) and _is_24hex(v):
                    try:
                        out[k] = ObjectId(v)
                    except Exception:
                        out[k] = v
                else:
                    out[k] = v
        return out
    elif isinstance(q, list):
        return [_convert_ids_in_query(x) for x in q]
    return q

def get_mongo_client():
    global mongo_client, current_db
    if not PYMONGO_AVAILABLE:
        raise Exception("PyMongo no está instalado. Ejecuta: pip install pymongo")
    if mongo_client is None:
        try:
            mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            mongo_client.admin.command('ping')
            current_db = mongo_client[DEFAULT_DATABASE]
            _log(f"✅ Conectado a MongoDB: {MONGO_URI}")
            _log(f"📊 Base de datos actual: {DEFAULT_DATABASE}")
        except ConnectionFailure as e:
            raise Exception(f"No se pudo conectar a MongoDB: {e}")
    return mongo_client, current_db

def serialize_doc(doc):
    if isinstance(doc, dict):
        return {k: serialize_doc(v) for k, v in doc.items()}
    elif isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    elif isinstance(doc, ObjectId):
        return str(doc)
    elif isinstance(doc, datetime):
        return doc.isoformat()
    else:
        return doc

# =======================
# HERRAMIENTAS EXPUESTAS
# =======================

@mcp.tool(
    name="list_databases",
    description="Lista todas las bases de datos disponibles en MongoDB."
)
def list_databases() -> str:
    try:
        client, _ = get_mongo_client()
        databases = client.list_database_names()
        db_info = []
        for db_name in databases:
            if db_name not in ['admin', 'local', 'config']:
                db_info.append(db_name)
        return json.dumps({
            "databases": db_info,
            "total_databases": len(db_info),
            "current_database": DEFAULT_DATABASE
        }, ensure_ascii=False)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(
    name="list_collections",
    description="Lista todas las colecciones en la base de datos actual o especificada."
)
def list_collections(database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]
        collections = db.list_collection_names()
        collection_info = []
        for coll_name in collections:
            count = db[coll_name].count_documents({})
            collection_info.append({
                "name": coll_name,
                "document_count": count,
            })
        return json.dumps({
            "database": database or DEFAULT_DATABASE,
            "collections": collection_info,
            "total_collections": len(collections)
        }, ensure_ascii=False)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(
    name="collection_schema",
    description="Infer collection schema by sampling documents. Use to understand structure before querying."
)
def collection_schema(collection: str, sample_size: int = 20, database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]
        coll = db[collection]
        pipeline = [{"$sample": {"size": sample_size}}]
        cursor = coll.aggregate(pipeline)
        acc: Dict[str, set] = {}
        count = 0
        for doc in cursor:
            count += 1
            _flatten_types(doc, "", acc)
        schema = {k: sorted(list(v)) for k, v in sorted(acc.items())}
        return json.dumps({
            "database": db.name,
            "collection": collection,
            "sampled_docs": count,
            "schema_fields": schema
        }, ensure_ascii=False)
    except Exception as e:
        return f"ERROR: {e}"

def _flatten_types(value: Any, prefix: str, acc: Dict[str, set]):
    import datetime as _dt
    def _typename(v):
        if isinstance(v, bool): return "bool"
        if isinstance(v, int): return "int"
        if isinstance(v, float): return "float"
        if isinstance(v, str): return "string"
        if isinstance(v, ObjectId): return "ObjectId"
        if isinstance(v, _dt.datetime): return "datetime"
        if v is None: return "null"
        if isinstance(v, dict): return "object"
        if isinstance(v, list): return "array"
        return type(v).__name__

    if isinstance(value, dict):
        for k, v in value.items():
            path = f"{prefix}.{k}" if prefix else k
            _flatten_types(v, path, acc)
    elif isinstance(value, list):
        acc.setdefault(prefix, set()).add("array")
        for el in value[:5]:
            t = _typename(el)
            acc.setdefault(prefix + "[]", set()).add(t)
            if isinstance(el, dict):
                _flatten_types(el, prefix + "[]", acc)
    else:
        acc.setdefault(prefix, set()).add(_typename(value))

@mcp.tool(
    name="find_documents",
    description="Find documents with filtering, sorting, and limiting. Use for simple queries. For GROUP BY or JOINs, use aggregate_documents instead."
)
def find_documents(collection: str,
                   query: Optional[Union[Dict, str]] = None,
                   limit: Optional[int] = None,
                   skip: Optional[int] = None,
                   sort: Optional[Union[Dict, str, List]] = None,
                   projection: Optional[Union[Dict, str]] = None,
                   coerce_object_ids: bool = False,
                   database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]

        coll = db[collection]
        parsed_query = _maybe_parse_json(query) or {}
        original_query_str = json.dumps(parsed_query) if isinstance(parsed_query, dict) else str(query)

        if coerce_object_ids:
            parsed_query = _convert_ids_in_query(parsed_query)

        def process_dates_in_query(q):
            if isinstance(q, dict):
                for key, value in q.items():
                    if isinstance(value, str):
                        if 'T' in value and ('Z' in value or '+' in value):
                            parent_has_operators = any(op in str(q) for op in ['$gte', '$lte', '$gt', '$lt', '$eq', '$ne'])
                            if not parent_has_operators:
                                try:
                                    if '+00:00' in value: date_obj = datetime.fromisoformat(value)
                                    elif 'Z' in value: date_obj = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                    else: date_obj = datetime.fromisoformat(value)
                                    q[key] = date_obj
                                except Exception: pass
                    elif isinstance(value, (dict, list)):
                        process_dates_in_query(value)
            elif isinstance(q, list):
                for item in q:
                    process_dates_in_query(item)
            return q

        parsed_query = process_dates_in_query(parsed_query)
        
        proj = _maybe_parse_json(projection) if projection is not None else None
        sort_list = _normalize_sort(sort)
        
        cursor = coll.find(parsed_query, projection=proj)
        
        if sort_list:
            cursor = cursor.sort(sort_list)
        if skip is not None and skip > 0:
            cursor = cursor.skip(skip)
        
        safe_limit = 10
        if limit is not None and limit > 0:
            safe_limit = limit
        
        cursor = cursor.limit(safe_limit)
        
        documents = list(cursor)
        total_count = coll.count_documents(parsed_query)
        serialized_docs = [serialize_doc(doc) for doc in documents]

        json_output = json.dumps({
            "database": db.name,
            "collection": collection,
            "query_used": original_query_str,
            "total_matched_by_query": total_count,
            "documents_returned": len(serialized_docs),
            "limit_applied": safe_limit,
            "documents": serialized_docs
        }, ensure_ascii=False, default=str)

        MAX_CHARS = 15000 
        if len(json_output) > MAX_CHARS:
            return json.dumps({
                "status": "WARNING_DATA_TRUNCATED",
                "message": (
                    f"La consulta devolvió {len(serialized_docs)} documentos, pero el volumen de datos es "
                    f"demasiado grande ({len(json_output)} caracteres) para mostrarlo en el chat."
                ),
                "instruction_for_agent": (
                    "IMPORTANTE: El resultado es demasiado extenso. Por favor, reintenta la consulta "
                    "usando el parámetro 'projection' para traer SOLO los campos necesarios o reduce el 'limit'."
                ),
                "sample_preview": serialized_docs[:2] 
            }, ensure_ascii=False)

        return json_output

    except Exception as e:
        return f"ERROR en find_documents: {str(e)}"

@mcp.tool(
    name="count_documents",
    description="Cuenta documentos que coincidan con un filtro. Simple counting only."
)
def count_documents(collection: str, query: Optional[Union[Dict, str]] = None, coerce_object_ids: bool = False, database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]
        coll = db[collection]
        q = _maybe_parse_json(query) or {}
        if coerce_object_ids:
            q = _convert_ids_in_query(q)
        cnt = coll.count_documents(q)
        return json.dumps({
            "collection": collection,
            "database": db.name,
            "count": cnt,
            "query_used": q
        }, ensure_ascii=False, default=str)
    except Exception as e:
        return f"ERROR: {e}"

@mcp.tool(
    name="lookup_join",
    description="DEPRECATED: Use aggregate_documents with $lookup for better control. Simple JOIN between two collections."
)
def lookup_join(local_collection: str,
                from_collection: str,
                local_field: str,
                foreign_field: str,
                as_field: str = "joined_docs",
                match_local: Optional[Union[Dict, str]] = None,
                sort_local: Optional[Union[Dict, str]] = None,
                limit_local: Optional[int] = None,
                unwind: bool = False,
                database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]

        if not local_collection or not from_collection or not local_field or not foreign_field:
            return "ERROR: 'local_collection', 'from_collection', 'local_field' y 'foreign_field' son obligatorios."

        pipe: List[Dict[str, Any]] = []

        if match_local:
            match_obj = _maybe_parse_json(match_local)
            if match_obj and isinstance(match_obj, dict):
                pipe.append({"$match": match_obj})

        if sort_local:
            sort_list = _normalize_sort(sort_local)
            if sort_list:
                pipe.append({"$sort": dict(sort_list)})
        
        if limit_local is not None and limit_local > 0:
             pipe.append({"$limit": int(limit_local)})

        lookup_stage = {
            "$lookup": {
                "from": from_collection,
                "localField": local_field,
                "foreignField": foreign_field,
                "as": as_field
            }
        }
        pipe.append(lookup_stage)

        if unwind:
            pipe.append({"$unwind": {"path": f"${as_field}", "preserveNullAndEmptyArrays": True}})

        results = list(db[local_collection].aggregate(pipe))
        serialized_results = [serialize_doc(doc) for doc in results]

        return json.dumps({
            "database": db.name,
            "local_collection": local_collection,
            "pipeline_used": pipe,
            "count": len(serialized_results),
            "results": serialized_results
        }, ensure_ascii=False)

    except Exception as e:
        return f"ERROR en lookup_join: {str(e)}"

@mcp.tool(
    name="aggregate_documents",
    description="MOST POWERFUL: Execute MongoDB aggregation for GROUP BY, JOINs, statistics. Use $group for counting/summing, $lookup for joins with users/assets, $match for filtering. See system prompt for detailed examples and patterns."
)
def aggregate_documents(collection: str, pipeline: Union[List[Dict], Dict, str], database: Optional[str] = None) -> str:
    try:
        client, db = get_mongo_client()
        if database:
            db = client[database]
        coll = db[collection]
        try:
            pipe = _ensure_list_pipeline(pipeline)
        except ValueError as ve:
            return f"ERROR: {str(ve)}"
        
        results = list(coll.aggregate(pipe))
        serialized_results = [serialize_doc(doc) for doc in results]
        
        fixes = []
        for st in pipe:
            if "__fixes_applied__" in st:
                fixes.extend(st["__fixes_applied__"])

        return json.dumps({
            "collection": collection,
            "database": database or DEFAULT_DATABASE,
            "pipeline": pipe,
            "results": serialized_results,
            "count": len(serialized_results),
            "fixes_applied": list(sorted(set(fixes))) if fixes else []
        }, ensure_ascii=False)
    except Exception as e:
        return f"ERROR: {e}"

# =======================
# MAIN
# =======================

if __name__ == "__main__":
    import argparse
    
    _log("🚀 Iniciando servidor MCP MongoDB...")
    
    if not PYMONGO_AVAILABLE:
        _log("❌ ERROR: PyMongo no está instalado")
        sys.exit(1)
    
    try:
        get_mongo_client()
    except Exception as e:
        _log(f"❌ ERROR CRÍTICO CONEXIÓN: {e}")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", type=str, default="stdio", choices=["sse", "stdio"])
    parser.add_argument("--port", type=int, default=8000, help="Puerto (solo para modo sse)")
    args = parser.parse_args()
    
    if args.server_type == "stdio":
        try:
            mcp.run(transport="stdio")
        except Exception as e:
            _log(f"❌ Error fatal en MCP STDIO: {e}")
            sys.exit(1)
    else:
        _log(f"📡 Arrancando modo SSE en puerto {args.port}...")
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
            _log("❌ Error: Para usar SSE necesitas 'uvicorn' instalado.")
            sys.exit(1)