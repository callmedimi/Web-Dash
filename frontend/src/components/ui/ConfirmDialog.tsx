/**
 * ConfirmDialog component with typed confirmation for high-risk operations.
 * Requires user to type an exact string/count (e.g. device count) before enabling apply.
 */
import React, { useState, useEffect } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { AlertTriangle } from "lucide-react";
import { cn } from "@/utils/cn";

export interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: React.ReactNode;
  confirmMatch?: string;
  confirmMatchPrompt?: string;
  confirmLabel: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void | Promise<void>;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  open,
  onOpenChange,
  title,
  description,
  confirmMatch,
  confirmMatchPrompt,
  confirmLabel,
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
}) => {
  const [typedInput, setTypedInput] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setTypedInput("");
      setIsSubmitting(false);
    }
  }, [open]);

  const canConfirm = !confirmMatch || typedInput.trim() === confirmMatch.trim();

  const handleConfirm = async () => {
    if (!canConfirm) return;
    setIsSubmitting(true);
    try {
      await onConfirm();
      onOpenChange(false);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-dialog border border-line bg-surface p-6 shadow-floating">
          <div className="flex items-start gap-3">
            {destructive && (
              <span className="flex h-8 w-8 items-center justify-center rounded-control bg-fault/15 text-fault flex-shrink-0">
                <AlertTriangle className="h-4 w-4" />
              </span>
            )}
            <div>
              <Dialog.Title className="text-sm font-semibold text-ink">
                {title}
              </Dialog.Title>
              <Dialog.Description className="mt-1 text-xs text-ink-2">
                {description}
              </Dialog.Description>
            </div>
          </div>

          {confirmMatch && (
            <div className="mt-4 rounded-control bg-surface-2 p-3 border border-line/60">
              <label htmlFor="confirm-typed-input" className="block text-xs font-medium text-ink mb-1.5">
                {confirmMatchPrompt || (
                  <span>
                    To confirm, please type <code className="font-mono font-bold text-signal px-1 bg-surface rounded border border-line">{confirmMatch}</code> below:
                  </span>
                )}
              </label>
              <input
                id="confirm-typed-input"
                type="text"
                autoFocus
                value={typedInput}
                onChange={(e) => setTypedInput(e.target.value)}
                placeholder={confirmMatch}
                className="h-8 w-full rounded-control border border-line bg-surface px-2.5 font-mono text-xs text-ink focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal"
              />
            </div>
          )}

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              disabled={isSubmitting}
              className="inline-flex h-8 items-center justify-center rounded-control border border-line bg-surface px-3 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {cancelLabel}
            </button>
            <button
              type="button"
              onClick={handleConfirm}
              disabled={!canConfirm || isSubmitting}
              className={cn(
                "inline-flex h-8 items-center justify-center rounded-control px-4 text-xs font-medium text-white transition-opacity focus:outline-none focus:ring-1 disabled:opacity-50",
                destructive ? "bg-fault hover:opacity-90 focus:ring-fault" : "bg-signal hover:opacity-90 focus:ring-signal"
              )}
            >
              {isSubmitting ? "Processing..." : confirmLabel}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
