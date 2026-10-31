/**
 * Mono chip component for IPs, interfaces, MAC addresses, and serial numbers.
 * Features inline copy button with confirmation tooltip.
 */
import React, { useState } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/utils/cn";

export interface MonoProps {
  children: React.ReactNode;
  copyable?: boolean;
  copyValue?: string;
  className?: string;
}

export const Mono: React.FC<MonoProps> = ({
  children,
  copyable = true,
  copyValue,
  className,
}) => {
  const [copied, setCopied] = useState(false);

  const textToCopy = copyValue || (typeof children === "string" ? children : String(children));

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Fallback or ignore
    }
  };

  return (
    <span
      className={cn(
        "group inline-flex items-center gap-1 rounded-control bg-surface-2 px-1.5 py-0.5 font-mono text-xs text-ink border border-line/60 dir-ltr",
        className
      )}
    >
      <span className="truncate">{children}</span>
      {copyable && (
        <button
          type="button"
          onClick={handleCopy}
          aria-label={copied ? "Copied" : "Copy to clipboard"}
          title={copied ? "Copied!" : "Copy"}
          className="ml-0.5 rounded p-0.5 text-ink-2 hover:bg-surface hover:text-ink focus:outline-none"
        >
          {copied ? (
            <Check className="h-2.5 w-2.5 text-ok" />
          ) : (
            <Copy className="h-2.5 w-2.5 opacity-60 group-hover:opacity-100" />
          )}
        </button>
      )}
    </span>
  );
};

export interface MonoChipProps {
  value?: string;
  children?: React.ReactNode;
  copyable?: boolean;
  className?: string;
}

export const MonoChip: React.FC<MonoChipProps> = ({
  value,
  children,
  copyable = true,
  className,
}) => {
  const content = value || children;
  return (
    <Mono copyable={copyable} copyValue={value} className={className}>
      {content}
    </Mono>
  );
};

export interface CliOutputProps {
  content: string;
  className?: string;
}

export const CliOutput: React.FC<CliOutputProps> = ({ content, className }) => {
  return (
    <pre
      className={cn(
        "dir-ltr font-mono text-xs bg-[var(--surface-2)] text-[var(--ink)] p-3 rounded-[3px] border border-[var(--line)] overflow-x-auto whitespace-pre leading-relaxed select-text",
        className
      )}
    >
      {content}
    </pre>
  );
};
