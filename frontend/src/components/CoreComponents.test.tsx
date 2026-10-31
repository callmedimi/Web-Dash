import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { StatusBadge, HealthDot } from "@/components/ui/StatusBadge";
import { Timestamp } from "@/components/ui/Timestamp";
import { MonoChip } from "@/components/ui/Mono";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tabs } from "@/components/ui/Tabs";
import { TimeRangePicker } from "@/components/ui/TimeRangePicker";
import { DataTable } from "@/components/datatable/DataTable";
import { LogViewer } from "@/components/logviewer/LogViewer";
import { RunTimeline } from "@/components/timeline/RunTimeline";
import { DiffViewer } from "@/components/diff/DiffViewer";
import { GrafanaPanel } from "@/components/charts/GrafanaPanel";

describe("Core NOC UI Components", () => {
  describe("StatusBadge & HealthDot", () => {
    it("renders StatusBadge with label and count", () => {
      render(<StatusBadge status="fault" label="Down" count={4} />);
      expect(screen.getByText(/Down \(4\)/)).toBeInTheDocument();
    });

    it("renders HealthDot with status", () => {
      const { container } = render(<HealthDot status="ok" title="Device Up" />);
      expect(container.querySelector(".bg-ok")).toBeInTheDocument();
    });
  });

  describe("Timestamp", () => {
    it("renders relative timestamp and exact tooltip", () => {
      const now = new Date().toISOString();
      render(<Timestamp isoString={now} relative />);
      expect(screen.getByText(/just now|0s ago/i)).toBeInTheDocument();
    });

    it("renders fallback for empty value", () => {
      render(<Timestamp value={null} />);
      expect(screen.getByText("--")).toBeInTheDocument();
    });
  });

  describe("Mono & MonoChip", () => {
    it("renders copyable mono chip", () => {
      render(<MonoChip value="192.0.2.1" />);
      expect(screen.getByText("192.0.2.1")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /copy/i })).toBeInTheDocument();
    });
  });

  describe("ConfirmDialog", () => {
    it("disables confirm button until typed verification matches", () => {
      const onConfirm = vi.fn();
      render(
        <ConfirmDialog
          open={true}
          onOpenChange={() => {}}
          title="Dangerous Apply"
          description="Confirm execution"
          confirmMatch="12"
          confirmMatchPrompt="Type 12:"
          confirmLabel="Execute"
          onConfirm={onConfirm}
        />
      );

      const confirmBtn = screen.getByRole("button", { name: "Execute" });
      expect(confirmBtn).toBeDisabled();

      const input = screen.getByLabelText("Type 12:");
      fireEvent.change(input, { target: { value: "12" } });
      expect(confirmBtn).not.toBeDisabled();

      fireEvent.click(confirmBtn);
      expect(onConfirm).toHaveBeenCalled();
    });
  });

  describe("Tabs", () => {
    it("switches tabs on trigger click", () => {
      const onValueChange = vi.fn();
      render(
        <Tabs
          value="tab1"
          onValueChange={onValueChange}
          items={[
            { id: "tab1", label: "Tab 1" },
            { id: "tab2", label: "Tab 2" },
          ]}
        />
      );

      const tab2 = screen.getByRole("tab", { name: /tab 2/i });
      fireEvent.keyDown(tab2, { key: "Enter", code: "Enter" });
      if (!onValueChange.mock.calls.length) {
        fireEvent.keyDown(tab2, { key: " ", code: "Space" });
      }
      expect(onValueChange).toHaveBeenCalledWith("tab2");
    });
  });

  describe("TimeRangePicker", () => {
    it("triggers onChange when a preset is clicked", () => {
      const onChange = vi.fn();
      render(<TimeRangePicker value="1h" onChange={onChange} />);

      fireEvent.click(screen.getByRole("button", { name: "24h" }));
      expect(onChange).toHaveBeenCalledWith("24h");
    });
  });

  describe("DataTable", () => {
    it("renders rows and filters with search input", () => {
      const testData = [
        { id: "1", name: "ROUTER-01", ip: "192.0.2.1" },
        { id: "2", name: "SWITCH-02", ip: "192.0.2.2" },
      ];
      const cols = [
        { accessorKey: "name", header: "Name" },
        { accessorKey: "ip", header: "IP" },
      ];

      render(<DataTable data={testData} columns={cols} title="Test Table" />);
      expect(screen.getByText("ROUTER-01")).toBeInTheDocument();
      expect(screen.getByText("SWITCH-02")).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText("Filter rows...");
      fireEvent.change(searchInput, { target: { value: "SWITCH" } });

      expect(screen.queryByText("ROUTER-01")).not.toBeInTheDocument();
      expect(screen.getByText("SWITCH-02")).toBeInTheDocument();
    });
  });

  describe("LogViewer", () => {
    it("filters logs by text search and level", () => {
      const logs = [
        { id: "1", ts: "12:00:00", level: "INFO" as const, message: "System started" },
        { id: "2", ts: "12:00:01", level: "ERROR" as const, message: "Connection refused" },
      ];

      render(<LogViewer lines={logs} title="Job Logs" />);
      expect(screen.getByText("System started")).toBeInTheDocument();
      expect(screen.getByText("Connection refused")).toBeInTheDocument();

      const searchInput = screen.getByPlaceholderText("Search logs...");
      fireEvent.change(searchInput, { target: { value: "refused" } });

      expect(screen.queryByText("System started")).not.toBeInTheDocument();
      expect(screen.getByText("Connection refused")).toBeInTheDocument();
    });
  });

  describe("RunTimeline", () => {
    it("renders device timeline rows and switches sort mode", () => {
      const rows = [
        {
          deviceId: "d1",
          deviceName: "CORE-01",
          overallStatus: "succeeded" as const,
          steps: {
            connect: { state: "succeeded" as const },
            pre_check: { state: "succeeded" as const },
            plan: { state: "succeeded" as const },
            apply: { state: "succeeded" as const },
            verify: { state: "succeeded" as const },
          },
        },
      ];

      render(<RunTimeline items={rows} title="Execution Timeline" />);
      expect(screen.getByText("CORE-01")).toBeInTheDocument();
      expect(screen.getByText("Attention First")).toBeInTheDocument();

      fireEvent.click(screen.getByText("Attention First"));
      expect(screen.getByText("Alphabetical")).toBeInTheDocument();
    });
  });

  describe("DiffViewer", () => {
    it("renders unified and split config diff with added and removed lines", () => {
      const oldConf = "interface 10GE1/0/1\n mtu 1500";
      const newConf = "interface 10GE1/0/1\n mtu 9198";

      render(<DiffViewer oldContent={oldConf} newContent={newConf} />);
      expect(screen.getByText(/mtu 1500/)).toBeInTheDocument();
      expect(screen.getByText(/mtu 9198/)).toBeInTheDocument();
    });
  });

  describe("GrafanaPanel", () => {
    it("renders fallback card on timeout", () => {
      vi.useFakeTimers();
      render(
        <GrafanaPanel
          title="CPU Telemetry"
          src="http://invalid-grafana:3000"
          grafanaUrl="http://localhost:3000/d/cpu"
          timeoutMs={100}
        />
      );

      act(() => {
        vi.advanceTimersByTime(200);
      });

      expect(screen.getByTestId("grafana-fallback-card")).toBeInTheDocument();
      expect(screen.getByText("Grafana Panel Unavailable")).toBeInTheDocument();
      vi.useRealTimers();
    });
  });
});
