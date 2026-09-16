import React, { useState } from 'react';
import { getFiwareTypes, getFiwareEntities, getFiwareEntityDetails, exploreExternalOpcua, provisionFiwareDevice } from '../api/simulatorService';

const getShortName = (uri) => {
  if (!uri) return '';
  return uri.split(/[/\#]/).pop();
};

const SelectableTree = ({ node, selectedNodeId, onSelect }) => {
  const [isOpen, setIsOpen] = useState(true);
  const isObject = node.class === 'Object';
  const isSelected = selectedNodeId === node.node_id;

  return (
    <div className="ml-3 mt-1">
      <div 
        className={`flex items-center gap-2 p-1.5 rounded border transition-colors cursor-pointer text-xs ${
          isSelected ? 'bg-blue-100 dark:bg-blue-900/50 border-blue-400' : 
          isObject ? 'hover:bg-slate-100 dark:hover:bg-slate-800 border-transparent' : 
          'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 hover:border-blue-300'
        }`}
        onClick={() => isObject ? setIsOpen(!isOpen) : onSelect(node)}
      >
        {isObject ? (
          <svg className={`w-4 h-4 text-slate-400 transition-transform ${isOpen ? 'rotate-90' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
        ) : (
          <div className="w-4 h-4 flex justify-center items-center"><div className="w-1.5 h-1.5 bg-emerald-500 rounded-full"></div></div>
        )}
        <span className={`font-mono truncate ${isSelected ? 'font-bold text-blue-700 dark:text-blue-300' : 'text-slate-700 dark:text-slate-300'}`}>
          {node.name}
        </span>
      </div>
      {isObject && isOpen && node.children && (
        <div className="border-l border-slate-200 dark:border-slate-700 ml-2 pl-1">
          {node.children.map((child, idx) => <SelectableTree key={idx} node={child} selectedNodeId={selectedNodeId} onSelect={onSelect} />)}
        </div>
      )}
    </div>
  );
};

export default function FiwareLinker() {
  const [toast, setToast] = useState(null);
  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  };

  const [config, setConfig] = useState({
    orion_url: window.APP_CONFIG?.orion_url || 'http://orion-ld:1026',
    iota_url: window.APP_CONFIG?.iota_url || 'http://iot-agent:4041',
    tenant: window.APP_CONFIG?.tenant || 'ibermot',
    service_path: window.APP_CONFIG?.service_path || '/',
    apikey: window.APP_CONFIG?.apikey || 'iot-ibermot',
    context_url: window.APP_CONFIG?.context_url || 'http://context-provider/industrial-oven-context.jsonld'
  });

  const [opcuaUrl, setOpcuaUrl] = useState(window.APP_CONFIG?.opcua_default_endpoint || 'opc.tcp://opcua-linker-backend:5679');

  const [types, setTypes] = useState([]);
  const [selectedType, setSelectedType] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  
  const [entities, setEntities] = useState([]);
  const [selectedEntity, setSelectedEntity] = useState(null);
  const [entityAttributes, setEntityAttributes] = useState([]);
  const [selectedAttr, setSelectedAttr] = useState(null);
  const [loadingOrion, setLoadingOrion] = useState(false);

  const [opcuaTree, setOpcuaTree] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [loadingOpcua, setLoadingOpcua] = useState(false);

  const fetchTypes = async () => {
    setLoadingOrion(true);
    try {
      const data = await getFiwareTypes(config);
      setTypes(data.types || []);
      setEntities([]);
      setSelectedType(null);
      setSelectedEntity(null);
      setEntityAttributes([]);
    } catch (err) {
      showToast('Error obteniendo tipos de Orion-LD.', 'error');
    } finally {
      setLoadingOrion(false);
    }
  };

  const fetchEntitiesByType = async (type) => {
    setSelectedType(type);
    setLoadingOrion(true);
    try {
      const data = await getFiwareEntities(config, type);
      setEntities(data.entities || []);
      setSelectedEntity(null);
      setEntityAttributes([]);
      setSearchTerm(''); 
    } catch (err) {
      showToast(`Error obteniendo entidades del tipo ${getShortName(type)}.`, 'error');
    } finally {
      setLoadingOrion(false);
    }
  };

  const loadEntityAttributes = async (entity) => {
    setSelectedEntity(entity);
    try {
      const data = await getFiwareEntityDetails(entity.id, config);
      const keys = Object.keys(data.entity).filter(k => !['id', 'type', '@context'].includes(k));
      setEntityAttributes(keys);
      setSelectedAttr(null);
    } catch (err) {
      showToast('Error cargando atributos.', 'error');
    }
  };

  const connectToOpcua = async () => {
    setLoadingOpcua(true);
    setOpcuaTree(null);
    setSelectedNode(null);
    try {
      const data = await exploreExternalOpcua(opcuaUrl);
      setOpcuaTree(data.tree);
    } catch (err) {
      showToast('No se pudo conectar al servidor OPC UA.', 'error');
    } finally {
      setLoadingOpcua(false);
    }
  };

  const handleProvision = async () => {
    if (!selectedEntity || !selectedAttr || !selectedNode) {
      showToast("Selecciona Entidad, Atributo y Nodo para vincular.", "error");
      return;
    }

    const shortType = getShortName(selectedEntity.type);
    const shortAttr = getShortName(selectedAttr);
    const baseEntityId = selectedEntity.id.split(':').pop();
    const safeDeviceId = `${baseEntityId}_${shortAttr}`.toLowerCase().replace(/[^a-z0-9_]/g, '');

    const payload = {
      config,
      device_id: safeDeviceId,
      entity_id: selectedEntity.id,
      entity_type: shortType,
      opcua_endpoint: opcuaUrl,
      opcua_node_id: selectedNode.node_id,
      attribute_name: shortAttr,
      attribute_type: 'Number'
    };

    try {
      await provisionFiwareDevice(payload);
      showToast(`¡${shortAttr} vinculado correctamente!`, 'success');
      setSelectedAttr(null);
      setSelectedNode(null);
    } catch (err) {
      showToast('Error creando el vínculo en el IoT Agent.', 'error');
    }
  };

  const filteredEntities = entities.filter(ent => 
    ent.id.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const inputClass = "w-full text-xs bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-2 text-slate-800 dark:text-slate-100 focus:outline-none focus:border-blue-500 mb-2";
  const labelClass = "block text-[11px] font-semibold text-slate-500 dark:text-slate-400 mb-1 uppercase tracking-wider";

  return (
    <div className="flex flex-col h-full bg-slate-100 dark:bg-slate-950 relative">
      
      {toast && (
        <div className={`absolute bottom-20 left-1/2 transform -translate-x-1/2 flex items-center gap-3 px-5 py-3 rounded-lg shadow-xl text-sm font-semibold text-white transition-all z-50 animate-bounce ${
          toast.type === 'success' ? 'bg-emerald-600 shadow-emerald-900/20' : 'bg-red-600 shadow-red-900/20'
        }`}>
          {toast.message}
        </div>
      )}

      {/* BARRA SUPERIOR DE CONFIGURACIÓN */}
      <div className="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 p-4 flex-none z-10 relative">
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <div><label className={labelClass}>Orion-LD</label><input type="text" value={config.orion_url} onChange={e=>setConfig({...config, orion_url: e.target.value})} className={inputClass} /></div>
          <div><label className={labelClass}>IoT Agent</label><input type="text" value={config.iota_url} onChange={e=>setConfig({...config, iota_url: e.target.value})} className={inputClass} /></div>
          <div><label className={labelClass}>Tenant</label><input type="text" value={config.tenant} onChange={e=>setConfig({...config, tenant: e.target.value})} className={inputClass} /></div>
          <div><label className={labelClass}>API Key</label><input type="text" value={config.apikey} onChange={e=>setConfig({...config, apikey: e.target.value})} className={inputClass} /></div>
          <div className="lg:col-span-2 flex gap-3">
            <div className="flex-1"><label className={labelClass}>Context URL</label><input type="text" value={config.context_url} onChange={e=>setConfig({...config, context_url: e.target.value})} className={inputClass} title={config.context_url} /></div>
            <div className="flex-none pb-2">
              <button onClick={fetchTypes} disabled={loadingOrion} className="bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold px-4 py-2.5 rounded shadow-sm transition-colors h-[34px] cursor-pointer">
                {loadingOrion ? 'Conectando...' : 'Conectar y Leer Tipos'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ZONA PRINCIPAL */}
      <div className="flex flex-1 min-h-0">
        
        {/* PANEL IZQUIERDO: FIWARE (REDISEÑADO CON SPLIT INTERNO) */}
        <div className="w-1/2 flex flex-col border-r border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          
          {/* Cabecera, Tipos y Buscador */}
          <div className="p-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex flex-col gap-3 flex-none">
            <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-orange-500"></span> Buscador de Entidades
            </h2>
            
            {types.length > 0 && (
              <div className="flex overflow-x-auto gap-2 pb-1 custom-scrollbar">
                {types.map(t => (
                  <button 
                    key={t} 
                    onClick={() => fetchEntitiesByType(t)}
                    className={`flex-none px-3 py-1.5 rounded-full text-[11px] font-semibold transition-colors border ${
                      selectedType === t 
                      ? 'bg-orange-500 text-white border-orange-600' 
                      : 'bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:bg-slate-100 dark:hover:bg-slate-700'
                    }`}
                  >
                    {getShortName(t)}
                  </button>
                ))}
              </div>
            )}

            {selectedType && (
              <div className="relative">
                <svg className="w-4 h-4 absolute left-2.5 top-2.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" /></svg>
                <input 
                  type="text" 
                  placeholder={`Buscar en ${entities.length} entidades de ${getShortName(selectedType)}...`}
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full text-xs pl-9 pr-3 py-2 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-600 rounded-md focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500 text-slate-800 dark:text-slate-100 shadow-sm"
                />
              </div>
            )}
          </div>
          
          {/* Área de Listas (Entidades / Atributos) */}
          {!selectedType ? (
            <div className="flex-1 flex items-center justify-center p-4">
              <div className="text-xs text-slate-400 text-center">
                {types.length === 0 ? "Conecta al entorno para leer los tipos." : "Selecciona un tipo en la barra superior."}
              </div>
            </div>
          ) : (
            <div className="flex-1 flex overflow-hidden">
              
              {/* COLUMNA INTERNA 1: LISTA DE ENTIDADES */}
              <div className={`overflow-y-auto p-4 custom-scrollbar transition-all ${selectedEntity ? 'w-1/2 border-r border-slate-200 dark:border-slate-700' : 'w-full'}`}>
                <label className={labelClass}>1. Entidad</label>
                <div className="grid grid-cols-1 gap-2 mt-2">
                  {filteredEntities.length === 0 ? (
                    <div className="text-xs text-slate-500 italic p-2">No hay entidades que coincidan.</div>
                  ) : (
                    filteredEntities.map(ent => (
                      <div key={ent.id} onClick={() => loadEntityAttributes(ent)} className={`p-2 border rounded cursor-pointer text-xs transition-colors ${selectedEntity?.id === ent.id ? 'bg-orange-50 dark:bg-orange-900/20 border-orange-400' : 'bg-slate-50 dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-orange-300'}`}>
                        <div className="font-mono text-slate-800 dark:text-slate-200 truncate" title={ent.id}>{ent.id}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* COLUMNA INTERNA 2: ATRIBUTOS (Solo visible si hay entidad seleccionada) */}
              {selectedEntity && (
                <div className="w-1/2 overflow-y-auto p-4 custom-scrollbar bg-slate-50/50 dark:bg-slate-800/30">
                  <label className={labelClass}>2. Atributo a vincular</label>
                  <div className="mt-2 space-y-1">
                    {entityAttributes.length === 0 ? <div className="text-xs text-slate-500">Sin atributos configurados.</div> : 
                      entityAttributes.map(attr => (
                        <div key={attr} onClick={() => setSelectedAttr(attr)} className={`p-2 border rounded cursor-pointer font-mono text-xs transition-colors ${selectedAttr === attr ? 'bg-orange-500 text-white border-orange-600 shadow-md' : 'bg-white dark:bg-slate-800 border-slate-200 dark:border-slate-700 hover:border-orange-400 dark:text-slate-300'}`} title={attr}>
                          {getShortName(attr)}
                        </div>
                      ))
                    }
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* PANEL DERECHO: OPC UA */}
        <div className="w-1/2 flex flex-col bg-white dark:bg-slate-900">
          <div className="p-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50 flex gap-2 items-center flex-none">
            <h2 className="text-sm font-bold text-slate-800 dark:text-slate-100 flex items-center gap-2 flex-none">
              <span className="w-2 h-2 rounded-full bg-blue-500"></span> Servidor OPC UA
            </h2>
            <input type="text" value={opcuaUrl} onChange={e=>setOpcuaUrl(e.target.value)} className="flex-1 text-xs px-2 py-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded focus:outline-none" placeholder="opc.tcp://..." />
            <button onClick={connectToOpcua} disabled={loadingOpcua} className="bg-slate-800 hover:bg-slate-700 text-white text-[11px] font-semibold px-3 py-1.5 rounded transition-colors flex-none cursor-pointer">
              {loadingOpcua ? 'Conectando...' : 'Explorar IP'}
            </button>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
             {!opcuaTree ? (
               <div className="flex h-full items-center justify-center">
                 <div className="text-xs text-slate-400 text-center">Explora una IP para ver el árbol.</div>
               </div>
             ) : (
               <div>
                  <label className={labelClass + " mb-3"}>3. Variable (Origen OPC UA)</label>
                  <div className="bg-slate-50 dark:bg-slate-800/30 border border-slate-200 dark:border-slate-700 rounded p-2">
                    <SelectableTree node={opcuaTree} selectedNodeId={selectedNode?.node_id} onSelect={setSelectedNode} />
                  </div>
               </div>
             )}
          </div>
        </div>
      </div>

      {/* BARRA DE ACCIÓN INFERIOR */}
      <div className="bg-white dark:bg-slate-800 border-t border-slate-200 dark:border-slate-700 p-4 flex justify-between items-center flex-none">
        <div className="flex items-center gap-4">
          <div className={`text-xs px-3 py-1.5 rounded-full border ${selectedAttr ? 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800' : 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-transparent'}`}>
            1. Atributo: <b>{selectedAttr ? getShortName(selectedAttr) : 'Pendiente'}</b>
          </div>
          <svg className="w-5 h-5 text-slate-300 dark:text-slate-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          <div className={`text-xs px-3 py-1.5 rounded-full border ${selectedNode ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800' : 'bg-slate-100 dark:bg-slate-800 text-slate-400 border-transparent'}`}>
            2. Nodo: <b>{selectedNode ? selectedNode.name : 'Pendiente'}</b>
          </div>
        </div>
        
        <button 
          onClick={handleProvision}
          disabled={!selectedAttr || !selectedNode}
          className={`px-8 py-2.5 rounded-lg text-sm font-bold transition-all ${
            selectedAttr && selectedNode 
              ? 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-md hover:shadow-lg transform hover:-translate-y-0.5 cursor-pointer' 
              : 'bg-slate-200 dark:bg-slate-700 text-slate-400 cursor-not-allowed'
          }`}
        >
          Crear Vínculo
        </button>
      </div>

    </div>
  );
}