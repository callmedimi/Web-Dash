/**
 * Styled Tabs component based on Radix UI Tabs primitive.
 */
import React from "react";
import * as RadixTabs from "@radix-ui/react-tabs";
import { cn } from "@/utils/cn";

export interface TabItem {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  count?: number | string;
  disabled?: boolean;
}

export interface TabsProps {
  value: string;
  onValueChange: (val: string) => void;
  items: TabItem[];
  children?: React.ReactNode;
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  value,
  onValueChange,
  items,
  children,
  className,
}) => {
  return (
    <RadixTabs.Root
      value={value}
      onValueChange={onValueChange}
      className={cn("flex flex-col h-full w-full", className)}
    >
      <RadixTabs.List className="flex items-center gap-1 border-b border-line bg-surface px-2">
        {items.map((tab) => (
          <RadixTabs.Trigger
            key={tab.id}
            value={tab.id}
            disabled={tab.disabled}
            className={cn(
              "group inline-flex items-center gap-1.5 border-b-2 border-transparent px-3 py-2 text-xs font-medium text-ink-2 transition-colors hover:text-ink focus:outline-none disabled:opacity-50",
              "data-[state=active]:border-signal data-[state=active]:text-signal"
            )}
          >
            {tab.icon}
            <span>{tab.label}</span>
            {tab.count !== undefined && (
              <span className="rounded-control bg-surface-2 px-1.5 py-0.2 text-[10px] font-mono text-ink-2 group-data-[state=active]:bg-signal/15 group-data-[state=active]:text-signal">
                {tab.count}
              </span>
            )}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {children}
    </RadixTabs.Root>
  );
};

export const TabContent = RadixTabs.Content;
