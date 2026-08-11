import React from 'react';

export default function DeviceCard({ name, onClick }) {
  return (
    <div 
      onClick={onClick}
      className="bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700 p-4 shadow-sm hover:shadow-md hover:border-blue-300 dark:hover:border-blue-500 hover:-translate-y-0.5 transition-all cursor-pointer flex flex-col justify-between h-full"
    >
      <div className="flex justify-between items-start mb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 bg-blue-50 dark:bg-slate-700 text-blue-600 dark:text-blue-400 rounded-md">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
          </div>
          <div>
            <h3 className="font-semibold text-slate-800 dark:text-slate-100 text-base leading-tight">{name}</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 font-medium">Nodo Raíz</p>
          </div>
        </div>
        
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 text-[10px] uppercase tracking-wider font-bold rounded border border-emerald-100 dark:border-emerald-800/50">
          <span className="relative flex h-1.5 w-1.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
          </span>
          Online
        </div>
      </div>
      
      <div className="mt-2 pt-3 border-t border-slate-100 dark:border-slate-700 flex justify-between items-center text-xs text-slate-500 dark:text-slate-400">
        <span>Protocolo</span>
        <span className="font-mono bg-slate-100 dark:bg-slate-700 px-1.5 py-0.5 rounded text-slate-600 dark:text-slate-300">OPC UA</span>
      </div>
    </div>
  );
}