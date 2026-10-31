/**
 * StatusBadge and HealthDot components.
 * Adheres to NOC Design Brief: Status color is loud, but NEVER color-only.
 * Always combines semantic color, icon, and readable text label.
 */
import React from "react";
import { CheckCircle2, AlertTriangle, XCircle, HelpCircle, Activity } from "lucide-react";
import { cn } from "@/utils/cn";

export type StatusVariant = "ok" | "warn" | "fault" | "info-muted" | "signal";

export interface StatusBadgeProps {
  variant?: StatusVariant;
  status?: StatusVariant;
  label?: string;
  count?: number;
  icon?: React.ReactNode;
  pulse?: boolean;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  variant,
  status,
  label,
  count,
  icon,
  pulse = false,
  className,
}) => {
  const effectiveVariant = variant || status || "info-muted";
  const displayLabel = label || effectiveVariant.toUpperCase();

  const getDefaultIcon = () => {
    switch (effectiveVariant) {
      case "ok":
        return <CheckCircle2 className="h-3 w-3 text-ok" />;
      case "warn":
        return <AlertTriangle className="h-3 w-3 text-warn" />;
      case "fault":
        return <XCircle className="h-3 w-3 text-fault" />;
      case "signal":
        return <Activity className="h-3 w-3 text-signal" />;
      case "info-muted":
      default:
        return <HelpCircle className="h-3 w-3 text-info-muted" />;
    }
  };

  const getVariantStyles = () => {
    switch (effectiveVariant) {
      case "ok":
        return "border-ok/30 bg-ok/10 text-ok";
      case "warn":
        return "border-warn/30 bg-warn/10 text-warn";
      case "fault":
        return "border-fault/30 bg-fault/10 text-fault";
      case "signal":
        return "border-signal/30 bg-signal/10 text-signal";
      case "info-muted":
      default:
        return "border-info-muted/30 bg-info-muted/10 text-info-muted";
    }
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-control border px-2 py-0.5 text-xs font-medium leading-none select-none",
        getVariantStyles(),
        className
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span
            className={cn(
              "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
              variant === "ok" && "bg-ok",
              variant === "warn" && "bg-warn",
              variant === "fault" && "bg-fault",
              variant === "signal" && "bg-signal",
              variant === "info-muted" && "bg-info-muted"
            )}
          />
          <span
            className={cn(
              "relative inline-flex h-2 w-2 rounded-full",
              effectiveVariant === "ok" && "bg-ok",
              effectiveVariant === "warn" && "bg-warn",
              effectiveVariant === "fault" && "bg-fault",
              effectiveVariant === "signal" && "bg-signal",
              effectiveVariant === "info-muted" && "bg-info-muted"
            )}
          />
        </span>
      )}
      {!pulse && (icon || getDefaultIcon())}
      <span>{displayLabel}{count !== undefined ? ` (${count})` : ""}</span>
    </span>
  );
};

export interface HealthDotProps {
  status: StatusVariant;
  pulse?: boolean;
  title?: string;
  className?: string;
}

export const HealthDot: React.FC<HealthDotProps> = ({
  status,
  pulse = false,
  title,
  className,
}) => {
  return (
    <span className={cn("relative inline-flex h-2 w-2 items-center justify-center", className)} title={title}>
      {pulse && (
        <span
          className={cn(
            "absolute inline-flex h-full w-full animate-ping rounded-full opacity-75",
            status === "ok" && "bg-ok",
            status === "warn" && "bg-warn",
            status === "fault" && "bg-fault",
            status === "signal" && "bg-signal",
            status === "info-muted" && "bg-info-muted"
          )}
        />
      )}
      <span
        className={cn(
          "inline-flex h-2 w-2 rounded-full",
          status === "ok" && "bg-ok",
          status === "warn" && "bg-warn",
          status === "fault" && "bg-fault",
          status === "signal" && "bg-signal",
          status === "info-muted" && "bg-info-muted"
        )}
      />
    </span>
  );
};
