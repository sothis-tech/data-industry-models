// rag-manager/frontend/src/App.jsx
import { useState, useEffect, useRef, useCallback } from "react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8301";
const SUPPORTED_EXTS = [".pdf", ".docx", ".txt", ".md"];
const SUPPORTED_ACCEPT = SUPPORTED_EXTS.join(",");

function isSupportedFile(filename) {
  const lower = filename.toLowerCase();
  return SUPPORTED_EXTS.some((ext) => lower.endsWith(ext));
}

// ─── API helpers ────────────────────────────────────────────────────────────

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchDocs(tenant) {
  return apiFetch(`/tenants/${tenant}/documents`);
}

async function uploadFile(tenant, file) {
  const fd = new FormData();
  fd.append("file", file);
  return apiFetch(`/tenants/${tenant}/upload`, { method: "POST", body: fd });
}

async function vectorizeFiles(tenant, filenames = null) {
  return apiFetch(`/tenants/${tenant}/vectorize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filenames ? { filenames } : {}),
  });
}

async function deleteDocument(tenant, filename, deleteFile = false) {
  return apiFetch(
    `/tenants/${tenant}/documents/${encodeURIComponent(filename)}?delete_file=${deleteFile}`,
    { method: "DELETE" }
  );
}

async function fetchTenants() {
  return apiFetch("/tenants");
}

async function createTenant(name) {
  return apiFetch("/tenants", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
}

async function deleteTenant(name) {
  return apiFetch(`/tenants/${encodeURIComponent(name)}`, { method: "DELETE" });
}

// ─── UploadZone ──────────────────────────────────────────────────────────────

function UploadZone({ tenant, onDone, disabled }) {
  const ref = useRef();
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [results, setResults] = useState([]);

  const process = useCallback(
    async (files) => {
      const docs = Array.from(files).filter((f) => isSupportedFile(f.name));
      const skipped = Array.from(files).filter((f) => !isSupportedFile(f.name));
      if (!docs.length) {
        setResults([
          {
            name: "—",
            ok: false,
            msg: `Sin archivos compatibles. Soportados: ${SUPPORTED_EXTS.join(", ")}`,
          },
        ]);
        return;
      }
      setUploading(true);
      setResults([]);
      const out = [];
      for (const f of docs) {
        try {
          await uploadFile(tenant, f);
          out.push({ name: f.name, ok: true, msg: "Subido" });
        } catch (e) {
          out.push({ name: f.name, ok: false, msg: e.message });
        }
      }
      if (skipped.length) {
        out.push({
          name: `${skipped.length} archivo(s)`,
          ok: false,
          msg: `Formato no soportado, ignorados.`,
        });
      }
      setResults(out);
      setUploading(false);
      onDone();
    },
    [tenant, onDone]
  );

  const onDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    if (!disabled) process(e.dataTransfer.files);
  };

  return (
    <div style={{ marginBottom: 16 }}>
      <div
        onClick={() => !disabled && ref.current?.click()}
        onDragOver={(e) => { e.preventDefault(); if (!disabled) setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        style={{
          border: `2px dashed ${dragging ? "#0070f3" : "#ccc"}`,
          borderRadius: 8,
          padding: "24px 16px",
          textAlign: "center",
          cursor: disabled ? "not-allowed" : "pointer",
          background: dragging ? "#e8f4ff" : "#fafafa",
          color: disabled ? "#aaa" : "#555",
          transition: "all 0.15s",
          userSelect: "none",
        }}
      >
        {uploading ? (
          "Subiendo…"
        ) : (
          <>
            Arrastra archivos aquí o{" "}
            <span style={{ color: "#0070f3", textDecoration: "underline" }}>
              selecciona
            </span>
            <br />
            <small style={{ color: "#999" }}>
              {SUPPORTED_EXTS.join(" · ")}
            </small>
          </>
        )}
      </div>
      <input
        ref={ref}
        type="file"
        accept={SUPPORTED_ACCEPT}
        multiple
        style={{ display: "none" }}
        onChange={(e) => { process(e.target.files); e.target.value = ""; }}
      />
      {results.length > 0 && (
        <ul style={{ margin: "8px 0 0", padding: 0, listStyle: "none", fontSize: 13 }}>
          {results.map((r, i) => (
            <li key={i} style={{ color: r.ok ? "#16a34a" : "#dc2626" }}>
              {r.ok ? "✓" : "✗"} {r.name} — {r.msg}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ─── DocRow ──────────────────────────────────────────────────────────────────

function DocRow({ tenant, filename, indexed, globalBusy, onRefresh }) {
  const [busyV, setBusyV] = useState(false);
  const [busyD, setBusyD] = useState(false);
  const [error, setError]   = useState("");

  const handleVectorize = async () => {
    setBusyV(true);
    setError("");
    try {
      await vectorizeFiles(tenant, [filename]);
      onRefresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyV(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`¿Eliminar "${filename}" del índice y disco?`)) return;
    setBusyD(true);
    setError("");
    try {
      await deleteDocument(tenant, filename, true);
      onRefresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyD(false);
    }
  };

  const ext = filename.split(".").pop().toUpperCase();
  const extColor = { PDF: "#dc2626", DOCX: "#2563eb", TXT: "#16a34a", MD: "#7c3aed" };
  const isAnyBusy = busyV || busyD || globalBusy;

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "8px 12px",
        borderRadius: 6,
        background: "#f9fafb",
        marginBottom: 6,
        border: "1px solid #e5e7eb",
      }}
    >
      {/* Badge extensión */}
      <span
        style={{
          fontSize: 10,
          fontWeight: 700,
          background: extColor[ext] ?? "#6b7280",
          color: "#fff",
          borderRadius: 4,
          padding: "2px 6px",
          minWidth: 34,
          textAlign: "center",
        }}
      >
        {ext}
      </span>

      {/* Nombre */}
      <span style={{ flex: 1, fontSize: 13, wordBreak: "break-all", color: "#111" }}>
        {filename}
      </span>

      {/* Estado */}
      {indexed ? (
        <span style={{ fontSize: 11, color: "#16a34a", whiteSpace: "nowrap" }}>
          ✓ {indexed.chunks} chunks · {indexed.pages}p
        </span>
      ) : (
        <span style={{ fontSize: 11, color: "#f59e0b", whiteSpace: "nowrap" }}>
          Sin indexar
        </span>
      )}

      {/* Acciones */}
      {!indexed && (
        <button
          onClick={handleVectorize}
          disabled={isAnyBusy}
          style={btnStyle(isAnyBusy, "#0070f3")}
        >
          {busyV ? "…" : "Vectorizar"}
        </button>
      )}
      <button
        onClick={handleDelete}
        disabled={isAnyBusy}
        style={btnStyle(isAnyBusy, "#dc2626")}
      >
        {busyD ? "…" : "Borrar"}
      </button>

      {error && (
        <span style={{ fontSize: 11, color: "#dc2626" }} title={error}>
          ⚠ error
        </span>
      )}
    </div>
  );
}

function btnStyle(disabled, color) {
  return {
    fontSize: 12,
    padding: "4px 10px",
    borderRadius: 5,
    border: `1px solid ${disabled ? "#ccc" : color}`,
    background: disabled ? "#f3f4f6" : "#fff",
    color: disabled ? "#aaa" : color,
    cursor: disabled ? "not-allowed" : "pointer",
    whiteSpace: "nowrap",
    transition: "all 0.1s",
  };
}

// ─── TenantPanel ─────────────────────────────────────────────────────────────

function TenantPanel({ tenant, active, onClick, onDelete }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "8px 12px",
        marginBottom: 4,
        borderRadius: 6,
        background: active ? "#0070f3" : "#f3f4f6",
        color: active ? "#fff" : "#111",
        cursor: "pointer",
        userSelect: "none",
        border: active ? "1px solid #0070f3" : "1px solid #e5e7eb",
      }}
    >
      <span style={{ fontSize: 13, fontWeight: active ? 600 : 400 }}>{tenant}</span>
      {tenant !== "default_tenant" && (
        <button
          onClick={(e) => { e.stopPropagation(); onDelete(tenant); }}
          style={{
            fontSize: 11,
            background: "transparent",
            border: "none",
            color: active ? "#cce" : "#9ca3af",
            cursor: "pointer",
            padding: "0 2px",
          }}
          title="Eliminar tenant"
        >
          ✕
        </button>
      )}
    </div>
  );
}

// ─── App ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [tenants, setTenants]       = useState([]);
  const [activeTenant, setActive]   = useState("default_tenant");
  const [newTenant, setNewTenant]   = useState("");
  const [rag, setRag]               = useState({ loading: false, data: null, error: "" });
  const [busyAll, setBusyAll]       = useState(false);
  const [vectorResult, setVectorResult] = useState(null);

  // ── Cargar tenants ──────────────────────────────────────────────────────
  const loadTenants = useCallback(async () => {
    try {
      const { tenants: list } = await fetchTenants();
      const all = list.includes("default_tenant")
        ? list
        : ["default_tenant", ...list];
      setTenants(all);
    } catch {
      setTenants(["default_tenant"]);
    }
  }, []);

  useEffect(() => { loadTenants(); }, [loadTenants]);

  // ── Cargar documentos del tenant activo ─────────────────────────────────
  const loadDocs = useCallback(async () => {
    setRag((r) => ({ ...r, loading: true, error: "" }));
    try {
      const data = await fetchDocs(activeTenant);
      setRag({ loading: false, data, error: "" });
    } catch (e) {
      setRag({ loading: false, data: null, error: e.message });
    }
  }, [activeTenant]);

  useEffect(() => { loadDocs(); }, [loadDocs]);

  // ── Crear tenant ─────────────────────────────────────────────────────────
  const handleCreateTenant = async () => {
    const name = newTenant.trim();
    if (!name) return;
    try {
      await createTenant(name);
      setNewTenant("");
      await loadTenants();
      setActive(name.toLowerCase().replace(/ /g, "_"));
    } catch (e) {
      alert(`Error creando tenant: ${e.message}`);
    }
  };

  // ── Borrar tenant ────────────────────────────────────────────────────────
  const handleDeleteTenant = async (name) => {
    if (!confirm(`¿Eliminar el tenant "${name}" y todos sus documentos?`)) return;
    try {
      await deleteTenant(name);
      await loadTenants();
      if (activeTenant === name) setActive("default_tenant");
    } catch (e) {
      alert(`Error eliminando tenant: ${e.message}`);
    }
  };

  // ── Vectorizar pendientes ────────────────────────────────────────────────
  const handleVectorizeAll = async () => {
    if (!rag.data?.not_indexed?.length) return;
    setBusyAll(true);
    setVectorResult(null);
    try {
      const res = await vectorizeFiles(activeTenant);
      setVectorResult(res);
      await loadDocs();
    } catch (e) {
      alert(`Error vectorizando: ${e.message}`);
    } finally {
      setBusyAll(false);
    }
  };

  // ── Datos derivados ──────────────────────────────────────────────────────
  const { data } = rag;
  const allFiles    = data?.disk_files ?? [];
  const indexed     = data?.indexed ?? {};
  const notIndexed  = data?.not_indexed ?? [];

  // Combinar: primero no indexados, luego indexados
  const sortedFiles = [
    ...notIndexed,
    ...allFiles.filter((f) => !notIndexed.includes(f)),
  ];

  const globalBusy = busyAll || rag.loading;

  return (
    <div
      style={{
        display: "flex",
        minHeight: "100vh",
        fontFamily: "'Inter', system-ui, sans-serif",
        background: "#f0f2f5",
      }}
    >
      {/* ── Sidebar ── */}
      <aside
        style={{
          width: 220,
          background: "#fff",
          borderRight: "1px solid #e5e7eb",
          padding: 16,
          flexShrink: 0,
        }}
      >
        <h2 style={{ margin: "0 0 16px", fontSize: 15, fontWeight: 700, color: "#111" }}>
          Tenants
        </h2>

        {tenants.map((t) => (
          <TenantPanel
            key={t}
            tenant={t}
            active={t === activeTenant}
            onClick={() => setActive(t)}
            onDelete={handleDeleteTenant}
          />
        ))}

        <div style={{ marginTop: 16 }}>
          <input
            value={newTenant}
            onChange={(e) => setNewTenant(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateTenant()}
            placeholder="Nuevo tenant…"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "6px 10px",
              fontSize: 12,
              border: "1px solid #d1d5db",
              borderRadius: 6,
              marginBottom: 6,
            }}
          />
          <button
            onClick={handleCreateTenant}
            disabled={!newTenant.trim()}
            style={{
              width: "100%",
              padding: "6px 0",
              fontSize: 12,
              borderRadius: 6,
              border: "1px solid #0070f3",
              background: newTenant.trim() ? "#0070f3" : "#e5e7eb",
              color: newTenant.trim() ? "#fff" : "#aaa",
              cursor: newTenant.trim() ? "pointer" : "not-allowed",
            }}
          >
            + Crear tenant
          </button>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{ flex: 1, padding: 24, maxWidth: 860 }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 20,
          }}
        >
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: "#111" }}>
              RAG Manager
            </h1>
            <p style={{ margin: "2px 0 0", fontSize: 13, color: "#6b7280" }}>
              Tenant: <strong>{activeTenant}</strong>
              {data && (
                <> · {data.total_chunks.toLocaleString()} chunks en índice</>
              )}
            </p>
          </div>

          {notIndexed.length > 0 && (
            <button
              onClick={handleVectorizeAll}
              disabled={globalBusy}
              style={{
                padding: "8px 16px",
                fontSize: 13,
                fontWeight: 600,
                borderRadius: 7,
                border: "none",
                background: globalBusy ? "#9ca3af" : "#0070f3",
                color: "#fff",
                cursor: globalBusy ? "not-allowed" : "pointer",
              }}
            >
              {busyAll
                ? "Vectorizando…"
                : `Vectorizar pendientes (${notIndexed.length})`}
            </button>
          )}
        </div>

        {/* Resultado de vectorización global */}
        {vectorResult && (
          <div
            style={{
              marginBottom: 16,
              padding: "10px 14px",
              background: "#f0fdf4",
              border: "1px solid #86efac",
              borderRadius: 7,
              fontSize: 13,
              color: "#15803d",
            }}
          >
            ✓ Vectorizados {vectorResult.processed} archivo(s) ·{" "}
            {vectorResult.chunks_total?.toLocaleString()} chunks totales
            {vectorResult.errors?.length > 0 && (
              <span style={{ color: "#dc2626" }}>
                {" "}· {vectorResult.errors.length} error(s)
              </span>
            )}
          </div>
        )}

        {/* Zona de carga */}
        <UploadZone
          tenant={activeTenant}
          onDone={loadDocs}
          disabled={globalBusy}
        />

        {/* Lista de documentos */}
        {rag.loading && (
          <p style={{ color: "#6b7280", fontSize: 13 }}>Cargando…</p>
        )}
        {rag.error && (
          <p style={{ color: "#dc2626", fontSize: 13 }}>Error: {rag.error}</p>
        )}

        {!rag.loading && !rag.error && sortedFiles.length === 0 && (
          <div
            style={{
              textAlign: "center",
              padding: "40px 20px",
              color: "#9ca3af",
              fontSize: 14,
              border: "1px dashed #e5e7eb",
              borderRadius: 8,
            }}
          >
            Sin documentos. Sube archivos para empezar.
          </div>
        )}

        {sortedFiles.map((fname) => (
          <DocRow
            key={fname}
            tenant={activeTenant}
            filename={fname}
            indexed={indexed[fname] ?? null}
            globalBusy={globalBusy}
            onRefresh={loadDocs}
          />
        ))}

        {/* Leyenda formatos */}
        {sortedFiles.length > 0 && (
          <p style={{ marginTop: 12, fontSize: 11, color: "#9ca3af" }}>
            Formatos soportados: {SUPPORTED_EXTS.join(" · ")}
          </p>
        )}
      </main>
    </div>
  );
}