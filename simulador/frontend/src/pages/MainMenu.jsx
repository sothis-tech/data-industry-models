import React, { useState, useEffect, useCallback } from "react";
import { getDevices, uploadYaml } from "../api/simulatorService";
import YamlUploader from "../components/YamlUploader";
import DeviceCard from "../components/DeviceCard";
import FiwareLinker from "../components/FiwareLinker";
import IoTAgentManager from "../components/IoTAgentManager";

export default function MainMenu({ onSelectDevice, onNavigate }) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  
  // Pestaña principal de navegación
  const [currentTab, setCurrentTab] = useState("assets");

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
    if (currentTab === "assets") {
      fetchDevices();
    }
  }, [currentTab, fetchDevices]);

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

  if (loading && currentTab === "assets")
    return (
      <div className="p-8 text-slate-500 dark:text-slate-400">
        Conectando con el servidor...
      </div>
    );

  const tabButtonClass = (tabId) => `pb-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
    currentTab === tabId 
      ? "border-blue-600 text-blue-600 dark:text-blue-400" 
      : "border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
  }`;

  return (
    <div className="w-full max-w-[1920px] mx-auto p-6 md:p-8 lg:p-10 flex flex-col min-h-screen">
      
      {/* CABECERA PRINCIPAL CON NAVEGACIÓN GLOBAL */}
      <header className="mb-8 flex flex-col border-b border-slate-200 dark:border-slate-700 pt-2 bg-white dark:bg-slate-900 sticky top-0 z-10 transition-colors gap-5">
        <div className="flex flex-col md:flex-row md:justify-between md:items-end gap-4">
          <div>
            <h1 className="text-2xl md:text-3xl font-bold text-slate-900 dark:text-slate-100 tracking-tight">
              Plataforma de Simulación & Gestión Industrial IIoT
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
              Consola unificada para servidores OPC UA locales, externos y aprovisionamiento FIWARE.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-medium text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-3 py-1.5 rounded border border-slate-200 dark:border-slate-700 shadow-sm self-start md:self-auto transition-colors">
            <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
            Simulador Local: Puerto 5679
          </div>
        </div>

        {/* Pestañas de Navegación de Nivel Superior */}
        <div className="flex gap-6 overflow-x-auto custom-scrollbar">
          <button onClick={() => setCurrentTab("assets")} className={tabButtonClass("assets")}>
            Servidores OPC UA (Simulación)
          </button>
          <button onClick={() => setCurrentTab("fiware_linker")} className={tabButtonClass("fiware_linker")}>
            Vinculación FIWARE
          </button>
          <button onClick={() => setCurrentTab("iota_provisioning")} className={tabButtonClass("iota_provisioning")}>
            Provisioning IoT Agent
          </button>
        </div>
      </header>

      {/* RENDERIZADO DINÁMICO DE CONTENIDO SEGÚN LA PESTAÑA */}
      <div className="flex-1">
        
        {/* TAB 1: ACTIVOS LOCALES (Distribución original del MainMenu) */}
        {currentTab === "assets" && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 md:gap-8">
            <aside className="lg:col-span-1">
              <YamlUploader onUpload={handleYamlUpload} isUploading={uploading} />
              <button
                onClick={() => onNavigate("create")}
                className="w-full bg-slate-800 dark:bg-slate-700 hover:bg-slate-700 dark:hover:bg-slate-600 text-white font-medium py-2.5 rounded-lg border border-slate-700 dark:border-slate-600 shadow-sm transition-all text-sm flex items-center justify-center gap-2 cursor-pointer"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
                Crear Dispositivo desde 0
              </button>
            </aside>

            <main className="lg:col-span-3">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">
                  Activos Disponibles en Servidor Local
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
                    Servidor limpio. Sube un archivo de configuración para simular maquinaria.
                  </p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
                  {devices.map((dev, index) => (
                    <DeviceCard
                      key={index}
                      name={dev}
                      onClick={() => onSelectDevice(dev)} // Mantiene el salto a DeviceDashboard
                    />
                  ))}
                </div>
              )}
            </main>
          </div>
        )}

        {/* TAB 2: VINCULACIÓN FIWARE GLOBAL */}
        {currentTab === "fiware_linker" && (
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm">
            <FiwareLinker deviceName={null} /> 
          </div>
        )}

        {/* TAB 3: PROVISIONING IOT AGENT GLOBAL */}
        {currentTab === "iota_provisioning" && (
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm p-6">
            <IoTAgentManager />
          </div>
        )}

      </div>
    </div>
  );
}