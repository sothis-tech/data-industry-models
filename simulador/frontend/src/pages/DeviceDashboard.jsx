import React, { useState, useEffect, useCallback } from "react";
import { getDeviceTree, addVariableToDevice, deleteOpcuaNode } from "../api/simulatorService";
import FiwareLinker from "../components/FiwareLinker";
import IoTAgentManager from "../components/IoTAgentManager";

/**
 * Renders a recursive tree node for industrial machinery hierarchy.
 * Conditionally displays real-time telemetry or deletion controls based on edit mode.
 * * @param {Object} node - OPC UA node data containing class, name, type, and value.
 * @param {boolean} isEditMode - Flag to toggle deletion controls.
 * @param {Function} onDeleteNode - Handler for node deletion request.
 */
const TreeNode = ({ node, isEditMode, onDeleteNode }) => {
  const [isOpen, setIsOpen] = useState(true);
  const isObject = node.class === "Object";

  return (
    <div className="ml-4 mt-2">
      <div
        className={`flex items-center gap-3 p-2 rounded-lg border transition-colors ${
          isObject
            ? "bg-slate-100 dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 cursor-pointer hover:bg-slate-200 dark:hover:bg-slate-800"
            : "bg-white dark:bg-slate-900 border-slate-100 dark:border-slate-800 shadow-sm"
        }`}
        onClick={() => isObject && setIsOpen(!isOpen)}
      >
        {isObject ? (
          <svg
            className={`w-5 h-5 text-blue-500 transition-transform ${isOpen ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M9 5l7 7-7 7"
            />
          </svg>
        ) : (
          <div className="w-5 h-5 flex items-center justify-center text-emerald-500">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></div>
          </div>
        )}
        <span className="font-semibold text-slate-700 dark:text-slate-200">
          {node.name}
        </span>
        
        {!isObject && node.class === "Variable" && (
          <div className="ml-auto flex items-center gap-3">
            {isEditMode ? (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteNode(node.node_id);
                }}
                className="flex items-center gap-1 bg-red-50 hover:bg-red-600 text-red-600 hover:text-white border border-red-200 hover:border-red-600 px-3 py-1 rounded text-[11px] font-bold uppercase transition-colors"
                title="Eliminar atributo del PLC"
              >
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Borrar
              </button>
            ) : (
              <>
                <span className="text-[10px] uppercase font-bold bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 px-2 py-1 rounded">
                  {node.type}
                </span>
                <span className="font-mono font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30 px-3 py-1 rounded border border-blue-100 dark:border-blue-800 min-w-[60px] text-right">
                  {node.value}
                </span>
              </>
            )}
          </div>
        )}
      </div>
      {isObject && isOpen && node.children && node.children.length > 0 && (
        <div className="border-l-2 border-slate-200 dark:border-slate-700 ml-2.5 pl-2 mt-2">
          {node.children.map((child, idx) => (
            <TreeNode key={idx} node={child} isEditMode={isEditMode} onDeleteNode={onDeleteNode} />
          ))}
        </div>
      )}
    </div>
  );
};

export default function DeviceDashboard({ deviceName, onBack }) {
  const [treeData, setTreeData] = useState(null);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("telemetry");

  // Estado de seguridad operativa
  const [isEditMode, setIsEditMode] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const [varName, setVarName] = useState("");
  const [dataType, setDataType] = useState("Float");
  const [initVal, setInitVal] = useState("0");

  const [simMode, setSimMode] = useState("none");
  const [updateMs, setUpdateMs] = useState(1000);
  const [mean, setMean] = useState(50);
  const [stddev, setStddev] = useState(5);
  const [min, setMin] = useState(0);
  const [max, setMax] = useState(100);

  const [enableNoise, setEnableNoise] = useState(false);
  const [noiseType, setNoiseType] = useState("gaussian");
  const [enableAnomaly, setEnableAnomaly] = useState(false);
  const [anomalyType, setAnomalyType] = useState("spike");

  /**
   * Retrieves the current variable tree from the OPC UA server.
   */
  const fetchTree = useCallback(async () => {
    try {
      const data = await getDeviceTree(deviceName);
      setTreeData(data.tree);
      setError(null);
    } catch (err) {
      setError("Error leyendo el dispositivo. ¿Sigue encendido?");
    }
  }, [deviceName]);

  useEffect(() => {
    fetchTree();
    const intervalId = setInterval(fetchTree, 1000);
    return () => clearInterval(intervalId);
  }, [fetchTree]);

  /**
   * Constructs the payload and provisions a new variable node in the OPC UA server.
   */
  const handleAddAttribute = async (e) => {
    e.preventDefault();
    if (!varName.trim()) return;

    const payload = {
      browse_name: varName.trim(),
      data_type: dataType,
      initial_value: initVal,
    };

    if (simMode !== "none") {
      payload.simulation = { mode: simMode, update_ms: updateMs };
      if (simMode === "normal") {
        payload.simulation.mean = mean;
        payload.simulation.stddev = stddev;
      }
      if (simMode === "normal" || simMode === "uniform" || simMode === "step") {
        payload.simulation.min = min;
        payload.simulation.max = max;
      }
      if (enableNoise) {
        payload.simulation.noise = {
          enabled: true,
          type: noiseType,
          params: noiseType === "white" ? { percent: 5.0 } : { mean: 0.0, stddev: 1.5 },
        };
      }
      if (enableAnomaly) {
        payload.simulation.anomaly = {
          enabled: true,
          type: anomalyType,
          probability: 0.02,
          params: anomalyType === "spike" ? { multiplier: 1.5, offset: 10.0 } : { value: 0 },
        };
      }
    }

    try {
      await addVariableToDevice(deviceName, payload);
      setVarName("");
      fetchTree();
    } catch (err) {
      alert("Error al inyectar variable. Revisa la consola del backend.");
    }
  };

  /**
   * Removes a variable node from the simulated OPC UA server.
   * Prompts for confirmation to prevent accidental modification of machinery mapping.
   * * @param {string} nodeId - Target OPC UA node identifier.
   */
  const handleDeleteNode = async (nodeId) => {
    if (!nodeId) return;
    
    const confirmDelete = window.confirm(`ATENCIÓN: ¿Confirmas la eliminación del nodo ${nodeId} del servidor OPC UA?`);
    if (!confirmDelete) return;

    setIsDeleting(true);
    try {
      await deleteOpcuaNode(nodeId);
      await fetchTree();
    } catch (error) {
      alert("Fallo al eliminar el nodo. Verifica los logs del servidor.");
      console.error(error);
    } finally {
      setIsDeleting(false);
    }
  };

  const inputClass = "w-full text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:border-blue-500 mb-2";
  const labelClass = "block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wider mt-2";

  return (
    <div className="w-full max-w-[1920px] mx-auto p-6 md:p-8 lg:p-10 flex flex-col h-screen overflow-hidden">
      <div className="flex-none">
        <button
          onClick={onBack}
          className="self-start mb-4 flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300 hover:text-blue-600 bg-white dark:bg-slate-800 px-3 py-1.5 rounded-md border border-slate-200 dark:border-slate-700 shadow-sm transition-colors cursor-pointer"
        >
          Volver al menú principal
        </button>
        <header className="bg-white dark:bg-slate-800 pt-5 px-6 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm mb-6 transition-colors flex justify-between items-center pb-5">
          <div>
            <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">{deviceName}</h1>
            <p className="text-xs text-slate-500 mt-0.5">Control de señales y simulación en tiempo real del PLC</p>
          </div>
          <span className="bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-400 text-xs font-bold px-2 py-0.5 rounded uppercase border border-emerald-200 dark:border-emerald-800">
            Live Server
          </span>
        </header>
      </div>


        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 flex-1 min-h-0 overflow-hidden">
          
          <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-5 shadow-sm flex flex-col min-h-0">
            <h3 className="font-bold text-slate-800 dark:text-slate-100 text-sm uppercase mb-3 flex-none border-b border-slate-100 dark:border-slate-700 pb-2">
              Inyectar Atributo
            </h3>

            <div className="overflow-y-auto flex-1 pr-2 custom-scrollbar">
              <form id="var-form" onSubmit={handleAddAttribute}>
                <label className={labelClass}>Nombre (BrowseName)</label>
                <input type="text" required value={varName} onChange={(e) => setVarName(e.target.value)} className={inputClass} placeholder="ej. Temperatura" />

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className={labelClass}>Data Type</label>
                    <select value={dataType} onChange={(e) => setDataType(e.target.value)} className={inputClass}>
                      <option value="Float">Float</option>
                      <option value="Int32">Int32</option>
                      <option value="Boolean">Boolean</option>
                    </select>
                  </div>
                  <div>
                    <label className={labelClass}>Valor Inicial</label>
                    <input type="text" value={initVal} onChange={(e) => setInitVal(e.target.value)} className={inputClass} />
                  </div>
                </div>

                <label className={labelClass}>Modo de Simulación</label>
                <select value={simMode} onChange={(e) => setSimMode(e.target.value)} className={inputClass}>
                  <option value="none">Estático (Sin simulación)</option>
                  <option value="normal">Normal (Curva Gaussiana)</option>
                  <option value="uniform">Uniforme (Aleatorio)</option>
                  <option value="step">Escalón (Incremento)</option>
                </select>

                {simMode !== "none" && (
                  <div className="p-3 bg-slate-50 dark:bg-slate-900/50 rounded-lg border border-slate-200 dark:border-slate-700 mt-2 space-y-2">
                    <div><label className={labelClass}>Intervalo (ms)</label><input type="number" value={updateMs} onChange={(e) => setUpdateMs(Number(e.target.value))} className={inputClass} /></div>
                    {simMode === "normal" && (
                      <div className="grid grid-cols-2 gap-2">
                        <div><label className={labelClass}>Media</label><input type="number" value={mean} onChange={(e) => setMean(Number(e.target.value))} className={inputClass} /></div>
                        <div><label className={labelClass}>Desviación</label><input type="number" value={stddev} onChange={(e) => setStddev(Number(e.target.value))} className={inputClass} /></div>
                      </div>
                    )}
                    <div className="grid grid-cols-2 gap-2">
                      <div><label className={labelClass}>Mínimo</label><input type="number" value={min} onChange={(e) => setMin(Number(e.target.value))} className={inputClass} /></div>
                      <div><label className={labelClass}>Máximo</label><input type="number" value={max} onChange={(e) => setMax(Number(e.target.value))} className={inputClass} /></div>
                    </div>

                    <label className="flex items-center gap-2 mt-4 cursor-pointer text-xs text-slate-700 dark:text-slate-300">
                      <input type="checkbox" checked={enableNoise} onChange={(e) => setEnableNoise(e.target.checked)} className="rounded text-blue-600" />
                      Inyectar Ruido Constante
                    </label>
                    {enableNoise && (
                      <select value={noiseType} onChange={(e) => setNoiseType(e.target.value)} className={inputClass + " mt-1"}>
                        <option value="gaussian">Gaussiano</option>
                        <option value="white">Ruido Blanco</option>
                      </select>
                    )}

                    <label className="flex items-center gap-2 mt-3 cursor-pointer text-xs text-slate-700 dark:text-slate-300">
                      <input type="checkbox" checked={enableAnomaly} onChange={(e) => setEnableAnomaly(e.target.checked)} className="rounded text-blue-600" />
                      Habilitar Anomalías (Picos/Caídas)
                    </label>
                    {enableAnomaly && (
                      <select value={anomalyType} onChange={(e) => setAnomalyType(e.target.value)} className={inputClass + " mt-1"}>
                        <option value="spike">Pico (Spike)</option>
                        <option value="drop">Caída a Cero (Drop)</option>
                      </select>
                    )}
                  </div>
                )}
              </form>
            </div>
            <button type="submit" form="var-form" className="w-full bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold py-3 rounded-lg shadow transition-colors mt-4 flex-none cursor-pointer">
              Ejecutar Inyección
            </button>
          </div>

          <div className="lg:col-span-3 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm flex flex-col min-h-0 relative">
            <div className="flex justify-between items-center mb-3 border-b border-slate-100 dark:border-slate-800 pb-2 flex-none">
              <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">
                Estructura y Telemetría en Vivo
              </h2>
              
              <button
                onClick={() => setIsEditMode(!isEditMode)}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-bold transition-all ${
                  isEditMode 
                    ? "bg-slate-800 text-white shadow-inner" 
                    : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-200 dark:border-slate-700"
                }`}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                </svg>
                {isEditMode ? "Modo Edición: Activo" : "Editar"}
              </button>
            </div>
            
            <div className="overflow-y-auto flex-1 custom-scrollbar">
              {error ? (
                <div className="text-red-500">{error}</div>
              ) : !treeData ? (
                <div className="animate-pulse">Leyendo...</div>
              ) : (
                <div className={isDeleting ? "opacity-50 pointer-events-none transition-opacity" : ""}>
                  <TreeNode 
                    node={treeData} 
                    isEditMode={isEditMode} 
                    onDeleteNode={handleDeleteNode} 
                  />
                </div>
              )}
            </div>
          </div>
        </div>

    </div>
  );
}