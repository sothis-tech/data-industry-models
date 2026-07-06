# servers/rag_server.py
# ─────────────────────────────────────────────────────────────────────────────
# Servidor MCP RAG — búsqueda híbrida con soporte multi-tenant.
#
# v1.4 — Cambios:
#   - FIX ChromaDB ≥0.6: quitada la palabra "ids" de los parámetros `include=`
#     de col.get(). Las versiones nuevas devuelven los ids automáticamente y
#     ponerlo en include lanza error.
#   - Resto del fichero igual que v1.3.
# ─────────────────────────────────────────────────────────────────────────────

import os
import sys
import io
import re
import json
import argparse
import contextlib
from collections import defaultdict
from mcp.server.fastmcp import FastMCP

try:
    from llama_index.core import VectorStoreIndex, StorageContext, Settings
    from llama_index.vector_stores.chroma import ChromaVectorStore
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.core.postprocessor import SentenceTransformerRerank
    import chromadb
    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    LLAMA_INDEX_AVAILABLE = False

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False


def _log(msg: str):
    print(f"[RAG-Server] {msg}", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

EMBED_MODEL_NAME  = "intfloat/multilingual-e5-small"
RERANK_MODEL_NAME = "BAAI/bge-reranker-v2-m3"

RETRIEVER_TOP_K        = int(os.getenv("RAG_TOP_K",    "30"))
RERANKER_TOP_N         = int(os.getenv("RAG_TOP_N",    "8"))
MAX_CHARS_PER_FRAGMENT = int(os.getenv("RAG_MAX_CHARS", "700"))
RRF_K                  = 60

CHROMA_HOST       = os.getenv("CHROMA_HOST", "")
CHROMA_PORT       = int(os.getenv("CHROMA_PORT", "8000"))
DB_PATH           = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME   = os.getenv("CHROMA_COLLECTION", "manuales_tecnicos")
COLLECTION_PREFIX = os.getenv("RAG_COLLECTION_PREFIX", "")


# ══════════════════════════════════════════════════════════════════════════════
# RESOLUCIÓN DE COLECCIÓN SEGÚN TENANT
# ══════════════════════════════════════════════════════════════════════════════

def _get_collection_name(tenant: str | None = None) -> str:
    if not tenant:
        return COLLECTION_NAME
    if COLLECTION_PREFIX:
        return f"{COLLECTION_PREFIX}{tenant}"
    return COLLECTION_NAME


# ══════════════════════════════════════════════════════════════════════════════
# DICCIONARIO ES→EN PARA EXPANSIÓN DE QUERY
# ══════════════════════════════════════════════════════════════════════════════

_ES_EN: dict = {
    "frecuencia": "frequency", "cada": "every", "cuanto": "how often",
    "cuándo": "when", "diario": "daily", "diaria": "daily",
    "semanal": "weekly", "mensual": "monthly", "anual": "annual",
    "anualmente": "annually", "veces": "times",
    "mantenimiento": "maintenance", "limpieza": "cleaning", "limpiar": "clean",
    "limpiado": "cleaning", "lavado": "washing", "engrase": "lubrication",
    "ajuste": "adjustment", "revisión": "inspection", "calibración": "calibration",
    "reparación": "repair", "sustitución": "replacement", "cambio": "change",
    "inspección": "inspection", "operación": "operation",
    "procedimiento": "procedure", "instrucciones": "instructions",
    "instalación": "installation", "puesta en marcha": "startup",
    "arranque": "startup", "parada": "shutdown",
    "horno": "oven chamber", "cámara": "chamber", "máquina": "machine",
    "equipo": "equipment", "planta": "plant", "sensor": "sensor",
    "válvula": "valve", "motor": "motor", "bomba": "pump",
    "ventilador": "fan", "filtro": "filter", "tubería": "pipe",
    "cable": "cable", "fusible": "fuse", "panel": "panel",
    "pantalla": "display", "humo": "smoke", "vapor": "steam",
    "agua": "water", "aire": "air", "gas": "gas", "combustible": "fuel",
    "temperatura": "temperature", "presión": "pressure", "humedad": "humidity",
    "velocidad": "speed", "tiempo": "time", "duración": "duration",
    "caudal": "flow", "nivel": "level", "consumo": "consumption",
    "energía": "energy", "potencia": "power", "voltaje": "voltage",
    "corriente": "current", "resistencia": "resistance",
    "seguridad": "safety", "peligro": "danger", "advertencia": "warning",
    "precaución": "caution", "ingesta": "ingestion", "ingestión": "ingestion",
    "contacto": "contact", "piel": "skin", "ojos": "eyes",
    "primeros auxilios": "first aid", "emergencia": "emergency",
    "protección": "protection", "guantes": "gloves", "mascarilla": "mask",
    "especificación": "specification", "ficha técnica": "datasheet",
    "manual": "manual", "guía": "guide", "rango": "range",
    "máximo": "maximum", "mínimo": "minimum", "valor": "value",
    "ajustes": "settings", "configuración": "configuration",
    "parámetro": "parameter", "parámetros": "parameters",
    "cocción": "cooking", "ahumado": "smoking", "secado": "drying",
    "enfriamiento": "cooling", "calentamiento": "heating",
    "ducha": "shower", "rociado": "shower spray", "vaporizado": "steaming",
    "ciclo": "cycle", "proceso": "process", "programa": "program",
    "paso": "step", "fase": "phase", "etapa": "stage",
}

_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "que", "qué",
    "en", "y", "o", "a", "al", "por", "para", "se", "sobre", "como",
    "es", "son", "está", "están", "hay", "tiene", "tienen", "me",
    "te", "le", "nos", "lo", "esta", "este", "esto", "ese", "esa",
    "the", "a", "an", "of", "to", "in", "and", "or", "is", "are",
}


def _expand_query(q: str) -> list[str]:
    q = q.strip()
    if not q:
        return []
    variants = [q]
    tokens = re.findall(r"\w+|[^\w\s]", q, flags=re.UNICODE)
    translated_tokens: list[str] = []
    key_terms_en:      list[str] = []
    found_translations = 0
    for tok in tokens:
        low = tok.lower()
        if low in _ES_EN:
            en = _ES_EN[low]
            translated_tokens.append(en)
            key_terms_en.append(en)
            found_translations += 1
        else:
            translated_tokens.append(tok)
            if low not in _STOPWORDS and tok.isalpha() and len(tok) > 2:
                key_terms_en.append(tok)
    if found_translations > 0:
        translated = " ".join(translated_tokens).strip()
        if translated and translated.lower() != q.lower():
            variants.append(translated)
        if key_terms_en:
            concentrated = " ".join(key_terms_en).strip()
            if concentrated.lower() not in [v.lower() for v in variants]:
                variants.append(concentrated)
    seen, out = set(), []
    for v in variants:
        k = v.lower()
        if k not in seen:
            seen.add(k)
            out.append(v)
    return out[:3]


# ══════════════════════════════════════════════════════════════════════════════
# MODELOS (cargados una sola vez al arranque)
# ══════════════════════════════════════════════════════════════════════════════

if LLAMA_INDEX_AVAILABLE:
    _log(f"Cargando embedder: {EMBED_MODEL_NAME}")
    try:
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=EMBED_MODEL_NAME,
            query_instruction="query: ",
            text_instruction="passage: ",
        )
    except Exception as e:
        _log(f"Error cargando embedder: {e}")

    with contextlib.redirect_stdout(io.StringIO()):
        Settings.llm = None

    _log(f"Cargando reranker: {RERANK_MODEL_NAME}")
    try:
        reranker = SentenceTransformerRerank(
            model=RERANK_MODEL_NAME,
            top_n=RERANKER_TOP_N,
        )
    except Exception as e:
        _log(f"Error cargando reranker: {e}")
        reranker = None
else:
    reranker = None

mcp = FastMCP("rag-server")


# ══════════════════════════════════════════════════════════════════════════════
# CLIENTE CHROMADB
# ══════════════════════════════════════════════════════════════════════════════

CHROMA_DATABASE = "default_database"

def _get_chroma_client(tenant: str | None = None):
    if CHROMA_HOST:
        if tenant:
            return chromadb.HttpClient(
                host=CHROMA_HOST,
                port=CHROMA_PORT,
                tenant=tenant,
                database=CHROMA_DATABASE,
                settings=chromadb.Settings(anonymized_telemetry=False),
            )
        return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return chromadb.PersistentClient(path=DB_PATH)


def _get_index(tenant: str | None = None):
    if not LLAMA_INDEX_AVAILABLE:
        raise ImportError("LlamaIndex no está instalado.")
    collection_name = _get_collection_name(tenant)
    db              = _get_chroma_client(tenant)
    col             = db.get_or_create_collection(collection_name)
    vector_store    = ChromaVectorStore(chroma_collection=col)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index           = VectorStoreIndex.from_vector_store(
        vector_store, storage_context=storage_context
    )
    return index, collection_name


# ══════════════════════════════════════════════════════════════════════════════
# BM25 — índice cacheado por colección
# ══════════════════════════════════════════════════════════════════════════════

_BM25_CACHE: dict = {}


def _build_bm25(col, collection_name: str) -> tuple:
    cache_key = f"{CHROMA_HOST}:{CHROMA_PORT}/{collection_name}"
    count     = col.count()

    if cache_key in _BM25_CACHE:
        cached_count, bm25, texts, metadatas, ids = _BM25_CACHE[cache_key]
        if cached_count == count:
            return bm25, texts, metadatas, ids

    result    = col.get(include=["documents", "metadatas"])
    texts     = result.get("documents", []) or []
    metadatas = result.get("metadatas",  []) or []
    ids       = result.get("ids",        []) or []   # ids vienen por defecto

    tokenized = [t.lower().split() for t in texts]
    bm25      = BM25Okapi(tokenized)
    _BM25_CACHE[cache_key] = (count, bm25, texts, metadatas, ids)
    return bm25, texts, metadatas, ids


def _bm25_search(col, collection_name: str, query: str, top_k: int) -> list[tuple[str, float]]:
    bm25, _, _, ids = _build_bm25(col, collection_name)
    tokens  = query.lower().split()
    scores  = bm25.get_scores(tokens)
    ranked  = sorted(
        ((ids[i], float(scores[i])) for i in range(len(ids)) if scores[i] > 0),
        key=lambda x: x[1], reverse=True,
    )
    return ranked[:top_k]


def _rrf_fusion(vector_nodes: list, bm25_ranked: list[tuple[str, float]]) -> list:
    from collections import defaultdict
    rrf_scores: dict = defaultdict(float)
    node_map:   dict = {}

    for rank, node in enumerate(vector_nodes):
        rrf_scores[node.node_id] += 1.0 / (RRF_K + rank + 1)
        node_map[node.node_id]    = node

    for rank, (doc_id, _) in enumerate(bm25_ranked):
        rrf_scores[doc_id] += 1.0 / (RRF_K + rank + 1)

    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    return [node_map[id_] for id_ in sorted_ids if id_ in node_map]


# ══════════════════════════════════════════════════════════════════════════════
# HERRAMIENTAS MCP
# ══════════════════════════════════════════════════════════════════════════════

@mcp.tool(
    name="consultar_base_conocimiento",
    description=(
        "Busca información en los manuales técnicos indexados usando búsqueda "
        "híbrida (semántica + BM25 + RRF + reranking). Usar para preguntas sobre "
        "procedimientos, especificaciones, mantenimiento, seguridad o cualquier "
        "contenido documental. Hace búsquedas multilingües internamente.\n\n"
        "Parámetros:\n"
        "- pregunta: la pregunta en lenguaje natural\n"
        "- tenant: (opcional) inyectado automáticamente por el cliente; no rellenar."
    ),
)
def consultar_base_conocimiento(
    pregunta: str,
    tenant:   str | None = None,
) -> str:
    if not LLAMA_INDEX_AVAILABLE:
        return "Error: Librerías de IA no instaladas."
    try:
        variants = _expand_query(pregunta)
        if not variants:
            return "Pregunta vacía."

        collection_name = _get_collection_name(tenant)

        index, _ = _get_index(tenant)
        retriever = index.as_retriever(similarity_top_k=RETRIEVER_TOP_K)

        all_nodes:  list = []
        nodes_seen: set  = set()
        for v in variants:
            try:
                nodes = retriever.retrieve(v)
            except Exception as e:
                _log(f"Vector retrieval falló para '{v}': {e}")
                continue
            for n in nodes:
                if n.node_id not in nodes_seen:
                    nodes_seen.add(n.node_id)
                    all_nodes.append(n)

        if not all_nodes:
            return (
                f"No se encontró información relevante para: '{pregunta}'.\n"
                f"Colección consultada: '{collection_name}'\n"
                f"Variantes probadas: {variants}"
            )

        if BM25_AVAILABLE:
            try:
                col = _get_chroma_client(tenant).get_or_create_collection(collection_name)
                bm25_all: dict = {}
                for v in variants:
                    for doc_id, score in _bm25_search(col, collection_name, v, RETRIEVER_TOP_K):
                        bm25_all[doc_id] = max(bm25_all.get(doc_id, 0), score)
                bm25_ranked = sorted(bm25_all.items(), key=lambda x: x[1], reverse=True)
                all_nodes   = _rrf_fusion(all_nodes, bm25_ranked)
            except Exception as e:
                _log(f"BM25/RRF falló (usando solo vectorial): {e}")
        else:
            _log("rank-bm25 no instalado — búsqueda solo vectorial.")

        if reranker:
            try:
                final_nodes = reranker.postprocess_nodes(all_nodes, query_str=pregunta)
            except Exception as e:
                _log(f"Reranker falló (usando orden RRF): {e}")
                final_nodes = all_nodes[:RERANKER_TOP_N]
        else:
            final_nodes = all_nodes[:RERANKER_TOP_N]

        fragments:    list = []
        seen_sources: set  = set()
        for node in final_nodes:
            meta      = node.metadata
            fname     = meta.get("file_name", "Archivo desconocido")
            page      = meta.get("page_label", "?")
            source_id = f"{fname} (Pág. {page})"
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            text = " ".join(node.text.replace("\n", " ").split())
            if len(text) > MAX_CHARS_PER_FRAGMENT:
                text = text[:MAX_CHARS_PER_FRAGMENT].rsplit(" ", 1)[0] + "..."
            fragments.append(f"FUENTE: {source_id}\nCONTENIDO: {text}")

        mode = "híbrida (semántica+BM25)" if BM25_AVAILABLE else "semántica"
        if len(variants) > 1:
            header = (
                f"Resultados [{mode}] en '{collection_name}' para '{pregunta}' "
                f"(también buscado como: {', '.join(repr(v) for v in variants[1:])}) "
                f"— {len(fragments)} fragmentos\n"
            )
        else:
            header = (
                f"Resultados [{mode}] en '{collection_name}' "
                f"para '{pregunta}' — {len(fragments)} fragmentos\n"
            )

        return header + "\n\n".join(fragments)

    except Exception as e:
        return f"Error consultando RAG: {e}"


@mcp.tool(
    name="obtener_paginas_con_contexto",
    description=(
        "Recupera el contenido COMPLETO de una página de un documento más las "
        "páginas adyacentes (anterior y siguiente). Usar cuando "
        "consultar_base_conocimiento devuelva un fragmento relevante pero "
        "incompleto o cortado.\n\n"
        "Parámetros:\n"
        "- file_name: nombre EXACTO del fichero (con extensión)\n"
        "- page_label: número de página\n"
        "- window: páginas a incluir antes y después (default 1)\n"
        "- tenant: inyectado automáticamente; no rellenar."
    ),
)
def obtener_paginas_con_contexto(
    file_name:  str,
    page_label: str,
    window:     int      = 1,
    tenant:     str | None = None,
) -> str:
    try:
        collection_name = _get_collection_name(tenant)
        db  = _get_chroma_client(tenant)
        col = db.get_or_create_collection(collection_name)

        try:
            target_page = int(page_label)
        except ValueError:
            return f"page_label debe ser un número entero, se recibió: '{page_label}'"

        pages_to_fetch = list(range(target_page - window, target_page + window + 1))
        pages_str      = {str(p) for p in pages_to_fetch if p > 0}

        # FIX ChromaDB ≥0.6: NO incluir "ids" en include
        result    = col.get(include=["documents", "metadatas"])
        fragments: list[tuple[int, str]] = []

        for doc, meta in zip(result.get("documents", []), result.get("metadatas", [])):
            fname  = meta.get("file_name") or meta.get("filename") or ""
            plabel = str(meta.get("page_label", ""))
            if fname == file_name and plabel in pages_str:
                try:
                    p_int = int(plabel)
                except ValueError:
                    p_int = 0
                fragments.append((p_int, doc))

        if not fragments:
            return (
                f"No se encontraron páginas para '{file_name}' "
                f"en la colección '{collection_name}' "
                f"rango {sorted(int(p) for p in pages_str)}."
            )

        fragments.sort(key=lambda x: x[0])
        p_min = min(p for p, _ in fragments)
        p_max = max(p for p, _ in fragments)

        output = (
            f"Contexto completo de '{file_name}' "
            f"(colección: '{collection_name}') "
            f"— páginas {p_min}–{p_max}:\n\n"
        )
        for page_num, text in fragments:
            clean   = " ".join(text.replace("\n", " ").split())
            output += f"--- PÁGINA {page_num} ---\n{clean}\n\n"

        return output.strip()

    except Exception as e:
        return f"Error recuperando contexto: {e}"


@mcp.tool(
    name="consultar_documento_concreto",
    description=(
        "Busca información en UN ÚNICO documento específico de la colección. "
        "Usar cuando el usuario nombre un documento concreto o cuando se necesite "
        "evitar mezcla de resultados de varios documentos.\n\n"
        "Parámetros:\n"
        "- file_name: nombre EXACTO del fichero (con extensión .pdf)\n"
        "- pregunta: pregunta en lenguaje natural\n"
        "- tenant: inyectado automáticamente; no rellenar."
    ),
)
def consultar_documento_concreto(
    file_name: str,
    pregunta:  str,
    tenant:    str | None = None,
) -> str:
    if not LLAMA_INDEX_AVAILABLE:
        return "Error: Librerías de IA no instaladas."
    try:
        collection_name = _get_collection_name(tenant)
        db  = _get_chroma_client(tenant)
        col = db.get_or_create_collection(collection_name)

        # FIX ChromaDB ≥0.6: NO incluir "ids" en include — vienen por defecto
        all_result = col.get(include=["documents", "metadatas"])
        all_names  = list({
            (m.get("file_name") or m.get("filename") or "")
            for m in all_result.get("metadatas", [])
        })

        # ids siempre vienen — los leemos del resultado directamente
        doc_ids, doc_texts = [], []
        result_ids = all_result.get("ids", []) or []
        for i, meta in enumerate(all_result.get("metadatas", [])):
            fname = meta.get("file_name") or meta.get("filename") or ""
            if fname == file_name:
                if i < len(result_ids):
                    doc_ids.append(result_ids[i])
                doc_texts.append(all_result["documents"][i])

        if not doc_ids:
            # Intento de matching laxo (sin extensión, case-insensitive)
            target_lower = file_name.lower().strip()
            matches = [
                n for n in all_names
                if target_lower in n.lower() or target_lower.replace(".pdf", "") in n.lower()
            ]
            if matches:
                return (
                    f"Documento '{file_name}' no encontrado en '{collection_name}'. "
                    f"¿Quisiste decir: {matches}?"
                )
            return (
                f"Documento '{file_name}' no encontrado en '{collection_name}'. "
                f"Disponibles: {sorted(all_names)}"
            )

        variants = _expand_query(pregunta)
        index, _ = _get_index(tenant)

        try:
            from llama_index.core.vector_stores import MetadataFilters, ExactMatchFilter
            filters   = MetadataFilters(filters=[
                ExactMatchFilter(key="file_name", value=file_name)
            ])
            retriever = index.as_retriever(
                similarity_top_k=RETRIEVER_TOP_K,
                filters=filters,
            )
        except Exception:
            retriever = index.as_retriever(similarity_top_k=RETRIEVER_TOP_K * 4)

        all_nodes, nodes_seen = [], set()
        for v in variants:
            try:
                nodes = retriever.retrieve(v)
            except Exception as e:
                _log(f"Retrieval falló '{v}': {e}")
                continue
            for n in nodes:
                fname_n = n.metadata.get("file_name") or n.metadata.get("filename") or ""
                if fname_n == file_name and n.node_id not in nodes_seen:
                    nodes_seen.add(n.node_id)
                    all_nodes.append(n)

        if not all_nodes:
            return f"No se encontró información sobre '{pregunta}' en '{file_name}'."

        if BM25_AVAILABLE and doc_texts:
            try:
                tokenized = [t.lower().split() for t in doc_texts]
                bm25_doc  = BM25Okapi(tokenized)
                bm25_all: dict = {}
                for v in variants:
                    scores = bm25_doc.get_scores(v.lower().split())
                    for i, score in enumerate(scores):
                        if score > 0 and i < len(doc_ids):
                            did = doc_ids[i]
                            bm25_all[did] = max(bm25_all.get(did, 0), score)
                bm25_ranked = sorted(bm25_all.items(), key=lambda x: x[1], reverse=True)
                all_nodes   = _rrf_fusion(all_nodes, bm25_ranked)
            except Exception as e:
                _log(f"BM25 doc-específico falló: {e}")

        if reranker and all_nodes:
            try:
                final_nodes = reranker.postprocess_nodes(all_nodes, query_str=pregunta)
            except Exception:
                final_nodes = all_nodes[:RERANKER_TOP_N]
        else:
            final_nodes = all_nodes[:RERANKER_TOP_N]

        fragments, seen_sources = [], set()
        for node in final_nodes:
            page      = node.metadata.get("page_label", "?")
            source_id = f"{file_name} (Pág. {page})"
            if source_id in seen_sources:
                continue
            seen_sources.add(source_id)
            text = " ".join(node.text.replace("\n", " ").split())
            if len(text) > MAX_CHARS_PER_FRAGMENT:
                text = text[:MAX_CHARS_PER_FRAGMENT].rsplit(" ", 1)[0] + "..."
            fragments.append(f"FUENTE: {source_id}\nCONTENIDO: {text}")

        if not fragments:
            return f"No se encontró información sobre '{pregunta}' en '{file_name}'."

        header = (
            f"Búsqueda en '{file_name}' (colección: '{collection_name}') "
            f"para '{pregunta}' — {len(fragments)} fragmentos\n"
        )
        return header + "\n\n".join(fragments)

    except Exception as e:
        return f"Error consultando documento: {e}"


@mcp.tool(
    name="listar_documentos_vectorizados",
    description=(
        "Lista los documentos disponibles en la base de conocimiento. "
        "Útil para saber qué hay indexado antes de consultar.\n\n"
        "Parámetros:\n"
        "- tenant: inyectado automáticamente por el cliente; no rellenar."
    ),
)
def listar_documentos_vectorizados(
    tenant: str | None = None,
) -> str:
    try:
        collection_name = _get_collection_name(tenant)
        db  = _get_chroma_client(tenant)
        col = db.get_or_create_collection(collection_name)
        total = col.count()

        if total == 0:
            return json.dumps({
                "collection": collection_name,
                "total_chunks": 0,
                "documentos": [],
            })

        result = col.get(include=["metadatas"])
        docs: dict = defaultdict(lambda: {"chunks": 0, "pages": set(), "source_type": "?"})
        for meta in result["metadatas"]:
            name = meta.get("file_name") or meta.get("filename") or "sin_nombre"
            docs[name]["chunks"] += 1
            docs[name]["pages"].add(str(meta.get("page_label", "?")))
            docs[name]["source_type"] = meta.get("source_type", "?")

        return json.dumps({
            "collection": collection_name,
            "total_chunks": total,
            "documentos": [
                {
                    "file_name":   n,
                    "chunks":      d["chunks"],
                    "num_pages":   len(d["pages"]),
                    "source_type": d["source_type"],
                }
                for n, d in sorted(docs.items())
            ],
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"error": str(e)})


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _log(f"Iniciando servidor MCP RAG v1.4 (multi-tenant + híbrida, ChromaDB ≥0.6)")
    if CHROMA_HOST:
        _log(f"  ChromaDB:    remoto {CHROMA_HOST}:{CHROMA_PORT}")
    else:
        _log(f"  ChromaDB:    local {DB_PATH}")
    _log(f"  Colección default: {COLLECTION_NAME}")
    _log(f"  Prefijo de colección: '{COLLECTION_PREFIX}' {'(sin prefijo)' if not COLLECTION_PREFIX else ''}")
    _log(f"  Embedder:    {EMBED_MODEL_NAME}")
    _log(f"  Reranker:    {RERANK_MODEL_NAME}")
    _log(f"  BM25:        {'disponible' if BM25_AVAILABLE else 'NO disponible — uv add rank-bm25'}")
    _log(f"  Retrieval:   top_k={RETRIEVER_TOP_K} → RRF → reranker top_n={RERANKER_TOP_N}")

    if not LLAMA_INDEX_AVAILABLE:
        _log("ERROR: LlamaIndex o ChromaDB no instalados.")
        sys.exit(1)

    parser = argparse.ArgumentParser()
    parser.add_argument("--server_type", default="stdio", choices=["sse", "stdio"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.server_type == "stdio":
        try:
            mcp.run(transport="stdio")
        except Exception as e:
            _log(f"Error fatal: {e}")
            sys.exit(1)
    else:
        _log(f"Modo SSE en puerto {args.port}")
        try:
            import uvicorn
            orig = uvicorn.Config.__init__
            def patched(self, *a, **kw):
                kw["port"] = args.port
                kw["host"] = "0.0.0.0"
                orig(self, *a, **kw)
            uvicorn.Config.__init__ = patched
            mcp.run(transport="sse")
        except ImportError:
            _log("uvicorn no instalado.")
            sys.exit(1)