import React, { useState, useEffect } from 'react';
import { getIoTAgentDevices, deleteIoTAgentDevice } from '../api/simulatorService';

export default function IoTAgentManager() {
  // Estado para el tenant con valor por defecto "ibermot"
  const [tenant, setTenant] = useState('ibermot');
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDevices = async (targetTenant) => {
    if (!targetTenant.trim()) return;
    try {
      setLoading(true);
      setError(null);
      const data = await getIoTAgentDevices(targetTenant.trim());
      setDevices(data);
    } catch (err) {
      setDevices([]);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Carga inicial usando el tenant por defecto
  useEffect(() => {
    fetchDevices(tenant);
  }, []);

  const handleRefresh = (e) => {
    e.preventDefault();
    fetchDevices(tenant);
  };

  const handleDelete = async (deviceId) => {
    // Alerta explícita que recuerda el Tenant en el que se está operando
    const confirmDelete = window.confirm(
      `¡ATENCIÓN!\n\n¿Confirmas la eliminación del dispositivo [${deviceId}] en el IoT Agent?\n` +
      `Tenant actual de la operación: "${tenant}"\n\nEsta acción es irreversible.`
    );
    
    if (!confirmDelete) return;

    try {
      await deleteIoTAgentDevice(deviceId, tenant);
      // Actualización optimista de la UI
      setDevices(devices.filter(d => d.device_id !== deviceId));
    } catch (err) {
      alert(`Error al eliminar: ${err.message}`);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Selector de Tenant Dinámico */}
      <div className="bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-700/60 rounded-xl p-4 mb-4 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="flex-1 max-w-sm">
          <label className="block text-[11px] font-bold text-slate-500 dark:text-slate-400 mb-1.5 uppercase tracking-wider">
            FIWARE Tenant (Service)
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              placeholder="ej. ibermot"
              className="w-full text-xs bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:border-blue-500 font-mono font-bold"
            />
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-xs font-semibold px-4 py-2 rounded shadow transition-colors cursor-pointer whitespace-nowrap"
            >
              {loading ? 'Consultando...' : 'Consultar'}
            </button>
          </div>
        </div>
        
        <div className="text-right hidden md:block">
          <span className="text-[10px] uppercase font-bold bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300 px-2 py-1 rounded">
            Modo: Multi-Tenant
          </span>
        </div>
      </div>

      {/* Cabecera de resultados */}
      <div className="flex justify-between items-center mb-3 border-b border-slate-100 dark:border-slate-800 pb-2">
        <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
          Dispositivos en tenant: <span className="font-mono text-blue-600 dark:text-blue-400">{tenant || 'vacio'}</span>
        </h2>
      </div>

      {/* Contenedor de la Tabla */}
      <div className="overflow-y-auto flex-1 custom-scrollbar">
        {error && (
          <div className="text-red-500 p-4 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-900/30 rounded-lg text-xs">
            {error}
          </div>
        )}

        {!error && devices.length === 0 && !loading && (
          <div className="text-center p-8 text-slate-400 text-xs italic">
            No se han devuelto dispositivos mapeados en este tenant.
          </div>
        )}

        {loading && (
          <div className="text-slate-500 p-4 animate-pulse text-xs">
            Sincronizando con el IoT Agent...
          </div>
        )}

        {!loading && devices.length > 0 && (
          <div className="w-full overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-800/70 border-b border-slate-200 dark:border-slate-700">
                  <th className="p-3 font-semibold text-slate-600 dark:text-slate-300 text-xs uppercase">Device ID</th>
                  <th className="p-3 font-semibold text-slate-600 dark:text-slate-300 text-xs uppercase">Entity Name</th>
                  <th className="p-3 font-semibold text-slate-600 dark:text-slate-300 text-xs uppercase">Entity Type</th>
                  <th className="p-3 font-semibold text-slate-600 dark:text-slate-300 text-xs uppercase text-center">Acción</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {devices.map((device) => (
                  <tr key={device.device_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/30 transition-colors">
                    <td className="p-3 font-mono font-medium text-slate-700 dark:text-slate-300 text-xs">{device.device_id}</td>
                    <td className="p-3 text-slate-600 dark:text-slate-400 text-xs">{device.entity_name}</td>
                    <td className="p-3">
                      <span className="text-[10px] uppercase font-bold bg-blue-50 dark:bg-blue-950/40 text-blue-600 dark:text-blue-400 px-2 py-0.5 rounded border border-blue-100 dark:border-blue-900/30">
                        {device.entity_type}
                      </span>
                    </td>
                    <td className="p-3 text-center">
                      <button
                        onClick={() => handleDelete(device.device_id)}
                        className="inline-flex items-center gap-1 bg-red-50 hover:bg-red-600 text-red-600 hover:text-white border border-red-200 hover:border-red-600 px-2.5 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-colors cursor-pointer"
                      >
                        Eliminar
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}