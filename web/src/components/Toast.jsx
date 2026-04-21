import React, { useState, useCallback, createContext, useContext, useRef } from 'react';
import { CheckCircle2, XCircle, AlertCircle, X } from 'lucide-react';

const ToastContext = createContext(null);

const ICONS = {
  success: <CheckCircle2 size={15} className="text-emerald-500 flex-shrink-0" />,
  error: <XCircle size={15} className="text-red-500 flex-shrink-0" />,
  warning: <AlertCircle size={15} className="text-amber-500 flex-shrink-0" />,
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timerRefs = useRef({});

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
    clearTimeout(timerRefs.current[id]);
  }, []);

  const toast = useCallback(({ type = 'success', message, duration = 3500 }) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, type, message }]);
    timerRefs.current[id] = setTimeout(() => dismiss(id), duration);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={toast}>
      {children}
      <div className="fixed bottom-6 right-6 z-[100] flex flex-col gap-2 pointer-events-none">
        {toasts.map(t => (
          <div
            key={t.id}
            className="flex items-center gap-3 bg-white border border-slate-200 shadow-lg rounded-xl px-4 py-3 min-w-[260px] max-w-sm pointer-events-auto animate-slide-up"
          >
            {ICONS[t.type]}
            <span className="text-sm text-slate-700 flex-1 leading-snug">{t.message}</span>
            <button
              type="button"
              aria-label="关闭通知"
              onClick={() => dismiss(t.id)}
              className="text-slate-300 hover:text-slate-500 transition-colors"
            >
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
