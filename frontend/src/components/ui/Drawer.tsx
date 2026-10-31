/**
 * Accessible Drawer / Slide-Over Panel for NOC detail inspections.
 */
import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/utils/cn";

export interface DrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  widthClass?: string;
}

export const Drawer: React.FC<DrawerProps> = ({
  open,
  onOpenChange,
  title,
  subtitle,
  children,
  footer,
  widthClass = "max-w-xl",
}) => {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm transition-opacity" />
        <Dialog.Content
          className={cn(
            "fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-line bg-surface shadow-floating transition-transform duration-150 ease-out",
            widthClass
          )}
        >
          {/* Header */}
          <div className="flex h-12 flex-shrink-0 items-center justify-between border-b border-line px-4">
            <div>
              <Dialog.Title className="text-sm font-semibold text-ink leading-tight">
                {title}
              </Dialog.Title>
              {subtitle && (
                <Dialog.Description className="text-[11px] text-ink-2 leading-tight">
                  {subtitle}
                </Dialog.Description>
              )}
            </div>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              aria-label="Close"
              className="rounded p-1 text-ink-2 hover:bg-surface-2 hover:text-ink focus:outline-none"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Internal scrollable body */}
          <div className="flex-1 overflow-y-auto p-4">{children}</div>

          {/* Optional Footer */}
          {footer && (
            <div className="flex-shrink-0 border-t border-line bg-surface-2/50 p-3">
              {footer}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
