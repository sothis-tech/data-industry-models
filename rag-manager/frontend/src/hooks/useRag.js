import { useState, useEffect, useCallback } from "react";

const BASE = "/api";

async function req(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res  = await fetch(BASE + path, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || `Error ${res.status}`);
  return data;
}

export function useRag() {
  const [tenants,  setTenants]  = useState([]);
  const [tenant,   setTenant]   = useState("default_tenant");
  const [docs,     setDocs]     = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState(null);

  const loadTenants = useCallback(async () => {
    try {
      const d = await req("GET", "/tenants");
      setTenants(d.tenants || []);
    } catch (e) { setError(e.message); }
  }, []);

  const loadDocs = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const d = await req("GET", `/tenants/${tenant}/documents`);
      setDocs(d);
    } catch (e) { setError(e.message); }
    finally { setLoading(false); }
  }, [tenant]);

  useEffect(() => { loadTenants(); }, [loadTenants]);
  useEffect(() => { loadDocs(); },   [loadDocs]);

  const selectTenant = useCallback((name) => { setTenant(name); setDocs(null); }, []);

  const createTenant = useCallback(async (name) => {
    try {
      const d = await req("POST", "/tenants", { name });
      await loadTenants();
      selectTenant(d.tenant);
      return { ok: true, tenant: d.tenant };
    } catch (e) { setError(e.message); return { ok: false }; }
  }, [loadTenants, selectTenant]);

  const uploadPdf = useCallback(async (file) => {
    try {
      const fd = new FormData();
      fd.append("file", file);
      await req("POST", `/tenants/${tenant}/upload`, fd);
      await loadDocs();
      return { ok: true };
    } catch (e) { setError(e.message); return { ok: false }; }
  }, [tenant, loadDocs]);

  const vectorize = useCallback(async (filenames = null) => {
    setLoading(true);
    try {
      const d = await req("POST", `/tenants/${tenant}/vectorize`, { filenames });
      await loadDocs();
      return { ok: true, ...d };
    } catch (e) { setError(e.message); return { ok: false }; }
    finally { setLoading(false); }
  }, [tenant, loadDocs]);

  const deleteFromIndex = useCallback(async (filename) => {
    try {
      await req("DELETE", `/tenants/${tenant}/documents/${encodeURIComponent(filename)}?delete_file=false`);
      await loadDocs();
      return { ok: true };
    } catch (e) { setError(e.message); return { ok: false }; }
  }, [tenant, loadDocs]);

  const deleteAll = useCallback(async (filename) => {
    try {
      await req("DELETE", `/tenants/${tenant}/documents/${encodeURIComponent(filename)}?delete_file=true`);
      await loadDocs();
      return { ok: true };
    } catch (e) { setError(e.message); return { ok: false }; }
  }, [tenant, loadDocs]);

  const deleteTenant = useCallback(async (name) => {
    try {
      await req("DELETE", `/tenants/${encodeURIComponent(name)}`);
      await loadTenants();
      if (tenant === name) selectTenant("default_tenant");
      return { ok: true };
    } catch (e) { setError(e.message); return { ok: false }; }
  }, [tenant, req, loadTenants, selectTenant]);

  const clearIndex = useCallback(async () => {
    setLoading(true);
    try {
      await req("DELETE", `/tenants/${tenant}/clear`);
      await loadDocs();
      return { ok: true };
    } catch (e) { setError(e.message); return { ok: false }; }
    finally { setLoading(false); }
  }, [tenant, loadDocs]);

  return {
    tenants, tenant, docs, loading, error,
    selectTenant, createTenant, uploadPdf,
    vectorize, deleteFromIndex, deleteAll, deleteTenant, clearIndex,
    refresh: loadDocs,
  };
}
