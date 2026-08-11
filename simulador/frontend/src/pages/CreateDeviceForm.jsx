import React, { useState } from 'react';
import { createDevice } from '../api/simulatorService';

export default function CreateDeviceForm({ onBack, onDeviceCreated }) {
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setLoading(true);
    try {
      await createDevice(name.trim());
      alert('¡Nodo raíz creado en el servidor OPC UA!');
      onDeviceCreated(name.trim()); // Nos lleva directo a su dashboard
    } catch (error) {
      console.error(error);
      alert('Error al crear el dispositivo. Comprueba si ya existe.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="w-full max-w-md mx-auto p-6 mt-12 bg-white dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-slate-700 shadow-sm transition-colors">
      <h2 className="text-xl font-bold text-slate-900 dark:text-slate-100 mb-2">Nuevo Activo Industrial</h2>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-6">
        Se instanciará un Nodo Raíz de tipo Objeto en caliente dentro del servidor.
      </p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
            Nombre del Nodo Raíz (ej. PLC_MANUAL)
          </label>
          <input
            type="text"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Introduce el identificador..."
            className="w-full text-sm bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg p-2.5 focus:outline-none focus:border-blue-500 text-slate-800 dark:text-slate-100 transition-colors"
          />
        </div>

        <div className="flex gap-3 pt-2">
          <button
            type="button"
            onClick={onBack}
            className="flex-1 text-sm font-medium bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 py-2.5 rounded-lg text-slate-700 dark:text-slate-200 transition-colors cursor-pointer text-center"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={loading}
            className="flex-1 text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white py-2.5 rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            {loading ? 'Creando...' : 'Dar de alta'}
          </button>
        </div>
      </form>
    </div>
  );
}