// Main view composing the machinery monitoring dashboard.
import React, { useState, useEffect, useCallback } from 'react';
import { getDevices, uploadYaml } from '../api/simulatorService';
import YamlUploader from '../components/YamlUploader';
import DeviceCard from '../components/DeviceCard';

export default function Dashboard() {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchDevices = useCallback(async () => {
    try {
      const data = await getDevices();
      setDevices(data.devices || []);
    } catch (error) {
      console.error("Error connecting to OPC UA simulator:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleYamlUpload = async (file) => {
    if (!file.name.endsWith('.yaml') && !file.name.endsWith('.yml')) {
      alert('Por favor, selecciona un archivo YAML válido.');
      return;
    }

    setUploading(true);
    try {
      await uploadYaml(file);
      await fetchDevices();
    } catch (error) {
      console.error("Error uploading YAML:", error);
      alert('Error al cargar la planta. Revisa la consola.');
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-slate-500 font-medium flex items-center gap-2">
          <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          Conectando con el servidor OPC UA...
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto p-8">
      <header className="mb-8 flex justify-between items-end border-b border-slate-200 pb-5">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Monitorización de Planta</h1>
          <p className="text-slate-500 mt-1">Gestión de activos industriales y simulador OPC UA</p>
        </div>
        <div className="flex items-center gap-2 text-sm font-medium text-slate-500 bg-white px-3 py-1.5 rounded-md border border-slate-200 shadow-sm">
          <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
          Puerto 5679 Abierto
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
        <aside className="lg:col-span-1 flex flex-col gap-6">
          <YamlUploader onUpload={handleYamlUpload} isUploading={uploading} />
        </aside>

        <main className="lg:col-span-3">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-xl font-semibold text-slate-800">Activos en línea</h2>
            <button 
              onClick={fetchDevices}
              className="text-sm font-medium text-blue-600 hover:text-blue-700 transition-colors flex items-center gap-1"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Sincronizar
            </button>
          </div>

          {devices.length === 0 ? (
            <div className="bg-white border-2 border-dashed border-slate-200 rounded-xl p-12 text-center">
              <svg className="mx-auto h-12 w-12 text-slate-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
              <h3 className="text-sm font-semibold text-slate-900">Ningún activo detectado</h3>
              <p className="mt-1 text-sm text-slate-500">El servidor está limpio. Sube un archivo de configuración para generar la jerarquía.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
              {devices.map((dev, index) => (
                <DeviceCard key={index} name={dev} />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}