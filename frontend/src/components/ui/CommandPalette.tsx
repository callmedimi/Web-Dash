/**
 * CommandPalette component triggered via Ctrl+K / Cmd+K.
 * Rapid keyboard navigation for NOC engineers across pages and tools.
 */
import React, { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate } from "react-router-dom";
import {
  Search,
  LayoutDashboard,
  Server,
  AlertTriangle,
  GitCommit,
  Terminal,
  FileText,
  Activity,
  Layers,
} from "lucide-react";

export const CommandPalette: React.FC = () => {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleSelect = (callback: () => void) => {
    setOpen(false);
    callback();
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-20 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-dialog border border-line bg-surface p-2 shadow-floating">
        <Command className="w-full">
          <div className="flex items-center gap-2 border-b border-line px-3 pb-2 pt-1">
            <Search className="h-4 w-4 text-ink-2" />
            <Command.Input
              autoFocus
              placeholder="Type a command or jump to page... (ESC to close)"
              className="w-full bg-transparent text-xs text-ink placeholder-ink-2/60 outline-none"
            />
          </div>

          <Command.List className="max-h-72 overflow-y-auto p-1 text-xs">
            <Command.Empty className="py-6 text-center text-xs text-ink-2">
              No matching pages or commands found.
            </Command.Empty>

            <Command.Group heading="Navigation" className="px-1 py-1 text-[11px] font-semibold text-ink-2 uppercase">
              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <LayoutDashboard className="h-3.5 w-3.5 text-signal" />
                <span>Dashboard / Overview</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/_ui"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <Layers className="h-3.5 w-3.5 text-warn" />
                <span>UI Kitchen Sink (/_ui)</span>
              </Command.Item>
            </Command.Group>

            <Command.Group heading="NOC Operations" className="px-1 py-1 text-[11px] font-semibold text-ink-2 uppercase">
              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <Server className="h-3.5 w-3.5 text-ink-2" />
                <span>Managed Routers</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <AlertTriangle className="h-3.5 w-3.5 text-fault" />
                <span>Alarms Center</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <GitCommit className="h-3.5 w-3.5 text-ok" />
                <span>Safe Changes Pipeline</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <Terminal className="h-3.5 w-3.5 text-signal" />
                <span>Command Runner</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <FileText className="h-3.5 w-3.5 text-ink-2" />
                <span>Reports & Daily Digest</span>
              </Command.Item>

              <Command.Item
                onSelect={() => handleSelect(() => navigate("/"))}
                className="flex cursor-pointer items-center gap-2 rounded-control px-2.5 py-1.5 text-xs text-ink hover:bg-surface-2 aria-selected:bg-surface-2"
              >
                <Activity className="h-3.5 w-3.5 text-signal" />
                <span>Telemetry & Zabbix Hub</span>
              </Command.Item>
            </Command.Group>
          </Command.List>
        </Command>
      </div>
    </div>
  );
};
