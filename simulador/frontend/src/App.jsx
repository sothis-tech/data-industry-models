import React, { useState, useEffect } from 'react';
import MainMenu from './pages/MainMenu';
import DeviceDashboard from './pages/DeviceDashboard';
import CreateDeviceForm from './pages/CreateDeviceForm';

function App() {
  const [view, setView] = useState('menu'); // 'menu' | 'create' | 'dashboard'
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDark]);

  // Navegación directa al dashboard tras crear el dispositivo
  const handleDeviceCreated = (deviceName) => {
    setSelectedDevice(deviceName);
    setView('dashboard');
  };

  return (
    <div className="min-h-screen w-full bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans transition-colors duration-300">
      
      {/* Botón flotante de Modo Oscuro */}
      <button
        onClick={() => setIsDark(!isDark)}
        className="fixed bottom-6 right-6 p-3 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 shadow-lg hover:shadow-xl transition-all z-50 text-slate-600 dark:text-slate-300 hover:scale-105 cursor-pointer"
      >
        {isDark ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        )}
      </button>

      {/* Enrutador de Vistas */}
      <div className="flex-1 w-full">
        {view === 'menu' && (
          <MainMenu 
            onNavigate={setView} 
            onSelectDevice={(dev) => { setSelectedDevice(dev); setView('dashboard'); }} 
          />
        )}
        
        {view === 'create' && (
          <CreateDeviceForm 
            onBack={() => setView('menu')} 
            onDeviceCreated={handleDeviceCreated} 
          />
        )}
        
        {view === 'dashboard' && (
          <DeviceDashboard 
            deviceName={selectedDevice} 
            onBack={() => setView('menu')} 
          />
        )}
      </div>
    </div>
  );
}

export default App;