import React, { useState, useEffect, useCallback } from "react";
import { getDevices, uploadYaml } from "../api/simulatorService";
import YamlUploader from "../components/YamlUploader";
import DeviceCard from "../components/DeviceCard";

export default function MainMenu({ onSelectDevice, onNavigate }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);

  const fetchDevices = useCallback(async () => {
    try {
      const data = await getDevices();
      setDevices(data.devices || []);
    } catch (error) {
      console.error("Error al conectar:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDevices();
  }, [fetchDevices]);

  const handleYamlUpload = async (file) => {
    setUploading(true);
    try {
      await uploadYaml(file);
      await fetchDevices();
    } catch (error) {
      alert("Error al cargar la planta.");
    } finally {
      setUploading(false);
    }
  };

  if (loading)
    return (
      <div className="p-8 text-slate-500 dark:text-slate-400">
        Conectando con el servidor...
      </div>
    );

  return (
    <div className="w-full max-w-[1920px] mx-auto p-6 md:p-8 lg:p-10">
      {/* CABECERA (Arreglado el color de textos y etiqueta) */}
      <header className="mb-8 flex flex-col md:flex-row md:justify-between md:items-end border-b border-slate-200 dark:border-slate-700 pb-5 gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
            Monitorización General
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Selecciona un activo para ver sus métricas en tiempo real
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300 bg-white dark:bg-slate-800 px-3 py-1.5 rounded border border-slate-200 dark:border-slate-700 shadow-sm self-start md:self-auto transition-colors">
          <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
          Puerto OPC UA: 5679
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 md:gap-8">
        {/* PANEL IZQUIERDO */}
        <aside className="lg:col-span-1">
          <YamlUploader onUpload={handleYamlUpload} isUploading={uploading} />
          <button
            onClick={() => onNavigate("create")}
            className="w-full bg-slate-800 dark:bg-slate-700 hover:bg-slate-700 dark:hover:bg-slate-600 text-white font-medium py-2.5 rounded-lg border border-slate-700 dark:border-slate-600 shadow-sm transition-all text-sm flex items-center justify-center gap-2 cursor-pointer"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 4v16m8-8H4"
              />
            </svg>
            Crear Dispositivo desde 0
          </button>
        </aside>

        {/* PANEL DERECHO (Arreglado el título de activos y el texto de sincronizar) */}
        <main className="lg:col-span-3">
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
              Activos Disponibles
            </h2>
            <button
              onClick={fetchDevices}
              className="text-xs font-medium text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 flex items-center gap-1 transition-colors"
            >
              Sincronizar
            </button>
          </div>

          {devices.length === 0 ? (
            <div className="bg-white dark:bg-slate-800 border-2 border-dashed border-slate-200 dark:border-slate-700 rounded-lg p-8 text-center transition-colors">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                Servidor limpio. Sube un archivo de configuración.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
              {devices.map((dev, index) => (
                <DeviceCard
                  key={index}
                  name={dev}
                  onClick={() => onSelectDevice(dev)}
                />
              ))}
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
