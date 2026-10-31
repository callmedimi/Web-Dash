/* eslint-disable react-refresh/only-export-components */
/**
 * Accessible Toast notification system with aria-live and semantic status styling.
 */
import React from "react";
import { create } from "zustand";
import { CheckCircle2, AlertTriangle, XCircle, Info, X } from "lucide-react";
import { cn } from "@/utils/cn";

export type ToastType = "success" | "error" | "warn" | "info";

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastState {
  toasts: ToastItem[];
  addToast: (message: string, type?: ToastType, duration?: number) => string;
  removeToast: (id: string) => void;
  clear: () => void;
}

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  addToast: (message: string, type: ToastType = "info", duration = 4000) => {
    const id = Math.random().toString(36).slice(2, 9);
    const newToast: ToastItem = { id, type, message, duration };

    set({ toasts: [...get().toasts, newToast] });

    if (duration > 0) {
      setTimeout(() => {
        get().removeToast(id);
      }, duration);
    }
    return id;
  },
  removeToast: (id: string) => {
    set({ toasts: get().toasts.filter((t) => t.id !== id) });
  },
  clear: () => set({ toasts: [] }),
}));

export const toast = {
  success: (msg: string, duration?: number) =>
    useToastStore.getState().addToast(msg, "success", duration),
  error: (msg: string, duration?: number) =>
    useToastStore.getState().addToast(msg, "error", duration),
  warn: (msg: string, duration?: number) =>
    useToastStore.getState().addToast(msg, "warn", duration),
  info: (msg: string, duration?: number) =>
    useToastStore.getState().addToast(msg, "info", duration),
};

export const ToastContainer: React.FC = () => {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-live="polite"
      aria-label="Notifications"
      className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none"
    >
      {toasts.map((t) => {
        const getIcon = () => {
          switch (t.type) {
            case "success":
              return <CheckCircle2 className="h-4 w-4 text-ok flex-shrink-0" />;
            case "error":
              return <XCircle className="h-4 w-4 text-fault flex-shrink-0" />;
            case "warn":
              return <AlertTriangle className="h-4 w-4 text-warn flex-shrink-0" />;
            case "info":
            default:
              return <Info className="h-4 w-4 text-signal flex-shrink-0" />;
          }
        };

        const getBorderColor = () => {
          switch (t.type) {
            case "success":
              return "border-ok/40";
            case "error":
              return "border-fault/40";
            case "warn":
              return "border-warn/40";
            case "info":
            default:
              return "border-signal/40";
          }
        };

        return (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-dialog border bg-surface p-3 text-xs text-ink shadow-floating transition-all",
              getBorderColor()
            )}
          >
            {getIcon()}
            <div className="flex-1 text-xs">{t.message}</div>
            <button
              type="button"
              onClick={() => removeToast(t.id)}
              className="text-ink-2 hover:text-ink focus:outline-none"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
};
