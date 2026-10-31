/**
 * Idle Timeout Warning / Notification Dialog.
 * Prompts user to re-authenticate when backend session expires after 30m inactivity.
 */
import React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "@/store/auth";
import { useNavigate } from "react-router-dom";

export const IdleTimeoutNotice: React.FC = () => {
  const { t } = useTranslation();
  const { idleTimeoutNotice, setIdleTimeoutNotice } = useAuthStore();
  const navigate = useNavigate();

  const handleSignInAgain = () => {
    setIdleTimeoutNotice(false);
    navigate("/login", { replace: true });
  };

  return (
    <Dialog.Root open={idleTimeoutNotice} onOpenChange={setIdleTimeoutNotice}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-dialog border border-line bg-surface p-6 shadow-floating">
          <div className="flex items-center gap-3">
            <span className="flex h-8 w-8 items-center justify-center rounded-control bg-warn/20 text-warn font-mono text-sm font-bold">
              !
            </span>
            <Dialog.Title className="text-base font-semibold text-ink">
              {t("auth.sessionExpiredTitle")}
            </Dialog.Title>
          </div>

          <Dialog.Description className="mt-3 text-sm text-ink-2">
            {t("auth.sessionExpiredDetail")}
          </Dialog.Description>

          <div className="mt-6 flex justify-end">
            <button
              type="button"
              onClick={handleSignInAgain}
              className="inline-flex h-8 items-center justify-center rounded-control bg-signal px-4 text-xs font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-1 focus:ring-signal"
            >
              {t("auth.signInAgain")}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};
