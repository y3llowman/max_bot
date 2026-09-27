import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Icon, type IconName } from "./Icon";
import s from "./Toast.module.css";

interface ToastOptions {
  text: string;
  /** По умолчанию check-circle, как в ките; для сбоев — alert-circle. */
  icon?: IconName;
  action?: { label: string; onClick: () => void };
  /** Вызывается, если тост закрылся сам, без нажатия на действие — например, «Отменить» не нажали. */
  onTimeout?: () => void;
  duration?: number;
}

interface ToastState extends ToastOptions {
  id: number;
}

const ToastContext = createContext<(options: ToastOptions) => void>(() => {});

export function useToast() {
  return useContext(ToastContext);
}

/** Toast — сообщение о результате действия, над нижней панелью, 5 секунд. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const counter = useRef(0);

  const show = useCallback((options: ToastOptions) => {
    counter.current += 1;
    setToast({ ...options, id: counter.current });
  }, []);

  useEffect(() => {
    if (!toast) return;
    timer.current = window.setTimeout(() => {
      setToast(null);
      toast.onTimeout?.();
    }, toast.duration ?? 5000);
    return () => window.clearTimeout(timer.current);
  }, [toast]);

  const act = () => {
    if (!toast) return;
    window.clearTimeout(timer.current);
    setToast(null);
    toast.action?.onClick();
  };

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className={s.region} role="status" aria-live="polite">
        {toast && (
          <div key={toast.id} className={s.toast}>
            <Icon name={toast.icon ?? "check-circle"} size={20} className={s.icon} />
            <span className={`t-detail ${s.text}`}>{toast.text}</span>
            {toast.action && (
              <button type="button" className={`t-action-s ${s.action}`} onClick={act}>
                {toast.action.label}
              </button>
            )}
          </div>
        )}
      </div>
    </ToastContext.Provider>
  );
}
