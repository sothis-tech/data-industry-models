import React, { useRef } from 'react';

export default function YamlUploader({ onUpload, isUploading }) {
  const fileInputRef = useRef(null);

  const handleFileChange = (event) => {
    const file = event.target.files[0];
    if (file) {
      onUpload(file);
    }
  };

  return (
    <div className="bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 p-6 shadow-sm transition-colors">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-slate-800 dark:text-slate-100">Cargar Configuración</h2>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          Sube el archivo YAML para desplegar la estructura de la planta simulada.
        </p>
      </div>
      

      <input 
        type="file" 
        accept=".yaml,.yml" 
        className="hidden" 
        ref={fileInputRef}
        onChange={handleFileChange}
      />
      
      <button 
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className={`w-full flex justify-center items-center gap-2 py-2.5 rounded-lg text-white font-medium transition-all ${
          isUploading 
            ? 'bg-blue-400 dark:bg-blue-600/50 cursor-not-allowed' 
            : 'bg-blue-600 hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-500 shadow-sm'
        }`}
      >
        {isUploading ? 'Desplegando...' : 'Seleccionar archivo .yaml'}
      </button>
    </div>
  );
}