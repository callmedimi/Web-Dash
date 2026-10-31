import React, { useState, useMemo } from "react";
import { type ColumnDef } from "@tanstack/react-table";
import { StatusBadge, HealthDot, type StatusVariant } from "@/components/ui/StatusBadge";
import { Timestamp } from "@/components/ui/Timestamp";
import { MonoChip, CliOutput } from "@/components/ui/Mono";
import { toast, ToastContainer } from "@/components/ui/Toast";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Drawer } from "@/components/ui/Drawer";
import { Tabs } from "@/components/ui/Tabs";
import { TimeRangePicker, type TimeRangePreset } from "@/components/ui/TimeRangePicker";
import { CommandPalette } from "@/components/ui/CommandPalette";
import { DataTable } from "@/components/datatable/DataTable";
import { LogViewer, type LogLine } from "@/components/logviewer/LogViewer";
import { RunTimeline, type TimelineDeviceRow, type TimelineStepDef } from "@/components/timeline/RunTimeline";
import { DiffViewer } from "@/components/diff/DiffViewer";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { TopologyGraph } from "@/components/charts/TopologyGraph";
import { GrafanaPanel } from "@/components/charts/GrafanaPanel";
import {
  AlertTriangle,
  Layers,
  Terminal,
  Activity,
  GitCommit,
  Network,
  Sliders,
} from "lucide-react";

// --- Demo Data Types & Generators ---

interface DemoDevice extends Record<string, unknown> {
  id: string;
  hostname: string;
  ip: string;
  role: "core" | "aggregation" | "edge";
  status: StatusVariant;
  vrfCount: number;
  cpuPercent: number;
  lastSeen: string;
}

const generateDemoDevices = (count: number): DemoDevice[] => {
  const roles: ("core" | "aggregation" | "edge")[] = ["core", "aggregation", "edge"];
  const statuses: StatusVariant[] = ["ok", "ok", "ok", "warn", "fault"];
  const list: DemoDevice[] = [];

  for (let i = 1; i <= count; i++) {
    const role = roles[i % roles.length];
    const status = statuses[i % statuses.length];
    list.push({
      id: `dev-${i}`,
      hostname: `ROUTER-${role.toUpperCase().slice(0, 3)}-${String(i).padStart(3, "0")}`,
      ip: `192.0.2.${(i % 250) + 1}`,
      role,
      status,
      vrfCount: (i % 8) + 1,
      cpuPercent: Math.min(99, Math.floor(15 + (i * 7) % 80)),
      lastSeen: new Date(Date.now() - i * 60_000).toISOString(),
    });
  }
  return list;
};

const sampleOldConfig = `sysname CORE-ROUTER-01
#
router id 192.0.2.1
#
bgp 65000
 peer 192.0.2.2 as-number 65000
 peer 192.0.2.2 description PEER-PE-01
 #
 ipv4-family unicast
  undo synchronization
  peer 192.0.2.2 enable
  peer 192.0.2.2 route-policy POLICY_OLD import
#
interface 10GE1/0/1
 description UPLINK-TO-TRANSIT
 ip address 198.51.100.1 255.255.255.252
#
return`;

const sampleNewConfig = `sysname CORE-ROUTER-01
#
router id 192.0.2.1
#
bgp 65000
 peer 192.0.2.2 as-number 65000
 peer 192.0.2.2 description PEER-PE-01
 peer 192.0.2.3 as-number 65000
 peer 192.0.2.3 description PEER-PE-02-BACKUP
 #
 ipv4-family unicast
  undo synchronization
  peer 192.0.2.2 enable
  peer 192.0.2.2 route-policy POLICY_HARDENED_V2 import
  peer 192.0.2.3 enable
  peer 192.0.2.3 route-policy POLICY_HARDENED_V2 import
#
interface 10GE1/0/1
 description UPLINK-TO-TRANSIT-PRIMARY
 ip address 198.51.100.1 255.255.255.252
 mtu 9198
#
return`;

const sampleLogs: LogLine[] = [
  { id: "1", timestamp: "14:02:11.102", level: "INFO", device: "CORE-ROUTER-01", message: "SSH session established (user: noc-automation)" },
  { id: "2", timestamp: "14:02:11.340", level: "INFO", device: "CORE-ROUTER-01", message: "Pre-check starting: verifying BGP neighbor states" },
  { id: "3", timestamp: "14:02:12.015", level: "INFO", device: "CORE-ROUTER-01", message: "BGP peer 192.0.2.2 is Established (uptime: 14d 06h)" },
  { id: "4", timestamp: "14:02:12.890", level: "WARN", device: "PE-TEH-02", message: "Interface 10GE1/0/2 input CRC errors detected (delta: +12)" },
  { id: "5", timestamp: "14:02:13.200", level: "INFO", device: "CORE-ROUTER-01", message: "Generating configuration diff against running config" },
  { id: "6", timestamp: "14:02:14.050", level: "ERROR", device: "AGG-SHR-01", message: "Commit failed: route-policy POLICY_HARDENED_V2 node 10 has syntax error" },
  { id: "7", timestamp: "14:02:14.500", level: "INFO", device: "CORE-ROUTER-01", message: "Rolling back transaction #49102" },
  { id: "8", timestamp: "14:02:15.110", level: "INFO", device: "CORE-ROUTER-01", message: "Rollback successful. Running configuration restored." },
];

const timelineSteps: TimelineStepDef[] = [
  { key: "connect", label: "Connect" },
  { key: "pre_check", label: "Pre-Check" },
  { key: "plan", label: "Diff Plan" },
  { key: "apply", label: "Apply" },
  { key: "verify", label: "Verify" },
];

const sampleTimelineRows: TimelineDeviceRow[] = [
  {
    deviceId: "dev-01",
    deviceName: "CORE-ROUTER-01",
    overallStatus: "succeeded",
    steps: {
      connect: { state: "succeeded", durationMs: 420 },
      pre_check: { state: "succeeded", durationMs: 1250 },
      plan: { state: "succeeded", durationMs: 680 },
      apply: { state: "succeeded", durationMs: 2400 },
      verify: { state: "succeeded", durationMs: 1100 },
    },
  },
  {
    deviceId: "dev-02",
    deviceName: "PE-TEH-01",
    overallStatus: "failed",
    steps: {
      connect: { state: "succeeded", durationMs: 380 },
      pre_check: { state: "succeeded", durationMs: 1100 },
      plan: { state: "succeeded", durationMs: 720 },
      apply: { state: "failed", durationMs: 3100, detail: "BGP route-policy syntax error at node 10" },
      verify: { state: "skipped" },
    },
  },
  {
    deviceId: "dev-03",
    deviceName: "AGG-KRN-01",
    overallStatus: "running",
    steps: {
      connect: { state: "succeeded", durationMs: 410 },
      pre_check: { state: "succeeded", durationMs: 1300 },
      plan: { state: "succeeded", durationMs: 650 },
      apply: { state: "running" },
      verify: { state: "pending" },
    },
  },
  {
    deviceId: "dev-04",
    deviceName: "CORE-ROUTER-02",
    overallStatus: "pending",
    steps: {
      connect: { state: "pending" },
      pre_check: { state: "pending" },
      plan: { state: "pending" },
      apply: { state: "pending" },
      verify: { state: "pending" },
    },
  },
];

// Sample time series metrics: 30 minutes timestamps
const nowSec = Math.floor(Date.now() / 1000);
const timePoints: number[] = [];
const rxTraffic: (number | null)[] = [];
const txTraffic: (number | null)[] = [];
for (let i = 30; i >= 0; i--) {
  timePoints.push(nowSec - i * 60);
  if (i === 15) {
    rxTraffic.push(null);
    txTraffic.push(null);
  } else {
    rxTraffic.push(Math.round(450 + Math.sin(i / 3) * 120 + (i % 4) * 20));
    txTraffic.push(Math.round(380 + Math.cos(i / 3) * 100 + (i % 3) * 25));
  }
}
const sampleTimeSeriesData: [number[], (number | null)[], (number | null)[]] = [
  timePoints,
  rxTraffic,
  txTraffic,
];

// Sample topology nodes and edges
const sampleTopologyNodes = [
  { id: "core1", data: { label: "CORE-ROUTER-01", role: "core" as const, ip: "192.0.2.1", status: "ok" as const, model: "NE40E-X8A" }, position: { x: 0, y: 0 } },
  { id: "core2", data: { label: "CORE-ROUTER-02", role: "core" as const, ip: "192.0.2.2", status: "ok" as const, model: "NE40E-X8A" }, position: { x: 0, y: 0 } },
  { id: "agg1", data: { label: "AGG-TEH-01", role: "aggregation" as const, ip: "192.0.2.11", status: "ok" as const, model: "S6730-H" }, position: { x: 0, y: 0 } },
  { id: "agg2", data: { label: "AGG-TEH-02", role: "aggregation" as const, ip: "192.0.2.12", status: "warn" as const, model: "S6730-H" }, position: { x: 0, y: 0 } },
  { id: "pe1", data: { label: "PE-ACCESS-01", role: "access" as const, ip: "192.0.2.21", status: "fault" as const, model: "ATN 910C" }, position: { x: 0, y: 0 } },
];

const sampleTopologyEdges = [
  { id: "e1", source: "core1", target: "core2", label: "100GE1/0/1" },
  { id: "e2", source: "core1", target: "agg1", label: "40GE1/0/1" },
  { id: "e3", source: "core2", target: "agg2", label: "40GE1/0/1" },
  { id: "e4", source: "agg1", target: "pe1", label: "10GE1/0/1" },
  { id: "e5", source: "agg2", target: "pe1", label: "10GE1/0/2" },
];

/**
 * KitchenSink Showcase Page for testing and validating all NOC core components.
 */
export const KitchenSink: React.FC = () => {
  const [activeTab, setActiveTab] = useState("atoms");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedRange, setSelectedRange] = useState<TimeRangePreset>("1h");
  const [isLiveLogs, setIsLiveLogs] = useState(true);

  // 1,000 devices for virtualized DataTable performance testing
  const demoDevices = useMemo(() => generateDemoDevices(1000), []);

  const deviceColumns = useMemo<ColumnDef<DemoDevice, unknown>[]>(
    () => [
      {
        accessorKey: "hostname",
        header: "Device Name",
        cell: (info) => (
          <div className="flex items-center gap-1.5 font-mono font-medium">
            <HealthDot status={info.row.original.status} />
            <span>{String(info.getValue())}</span>
          </div>
        ),
      },
      {
        accessorKey: "ip",
        header: "IP Address",
        cell: (info) => <MonoChip value={String(info.getValue())} />,
      },
      {
        accessorKey: "role",
        header: "Role",
        cell: (info) => (
          <span className="uppercase text-[11px] text-[var(--ink-2)]">{String(info.getValue())}</span>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: (info) => <StatusBadge status={info.getValue() as StatusVariant} />,
      },
      {
        accessorKey: "vrfCount",
        header: "VRFs",
        cell: (info) => <span className="font-mono">{Number(info.getValue())}</span>,
      },
      {
        accessorKey: "cpuPercent",
        header: "CPU %",
        cell: (info) => {
          const val = Number(info.getValue());
          const color = val > 80 ? "text-[var(--fault)]" : val > 60 ? "text-[var(--warn)]" : "text-[var(--ok)]";
          return <span className={`font-mono font-semibold ${color}`}>{val}%</span>;
        },
      },
      {
        accessorKey: "lastSeen",
        header: "Last Seen",
        cell: (info) => <Timestamp isoString={String(info.getValue())} />,
      },
    ],
    []
  );

  const tabsList = [
    { id: "atoms", label: "UI Atoms", icon: <Sliders size={14} /> },
    { id: "datatable", label: "Data Table (1,000)", icon: <Layers size={14} /> },
    { id: "logviewer", label: "Log Stream", icon: <Terminal size={14} /> },
    { id: "timeline", label: "Run Timeline", icon: <Activity size={14} /> },
    { id: "diff", label: "Config Diff", icon: <GitCommit size={14} /> },
    { id: "telemetry", label: "Charts & Topology", icon: <Network size={14} /> },
  ];

  return (
    <div className="flex flex-col h-full bg-[var(--bg)] text-[var(--ink)] overflow-y-auto p-4 space-y-4">
      {/* Toast and Command Palette Mounts */}
      <ToastContainer />
      <CommandPalette />

      {/* Header */}
      <div className="flex flex-wrap items-center justify-between border-b border-[var(--line)] pb-3 gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight">NOC Design System Showcase</h1>
            <span className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[11px] font-mono text-[var(--ink-2)]">
              /_ui
            </span>
          </div>
          <p className="text-xs text-[var(--ink-2)]">
            Interactive test workbench for virtualized tables, streaming logs, swimlanes, diffs, and charts.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <TimeRangePicker value={selectedRange} onChange={setSelectedRange} />
          <button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="flex items-center gap-1.5 rounded-[3px] bg-[var(--fault)] px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90 transition-opacity"
          >
            <AlertTriangle size={14} />
            <span>Apply 12 Changes</span>
          </button>
        </div>
      </div>

      {/* Navigation Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} items={tabsList} />

      {/* Tab 1: UI Atoms */}
      {activeTab === "atoms" && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="tab-atoms">
          {/* Status Badges & Health Dots */}
          <div className="rounded-[3px] border border-[var(--line)] bg-[var(--surface)] p-4 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--ink-2)]">
              Status Badges & Health Dots
            </h3>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status="ok" label="Up / Normal" />
              <StatusBadge status="warn" label="Degraded" />
              <StatusBadge status="fault" label="Down / Alarm" count={3} />
              <StatusBadge status="info-muted" label="Unknown" />
            </div>
            <div className="flex items-center gap-4 text-xs font-mono pt-2 border-t border-[var(--line)]">
              <div className="flex items-center gap-1.5">
                <HealthDot status="ok" />
                <span>Healthy</span>
              </div>
              <div className="flex items-center gap-1.5">
                <HealthDot status="warn" />
                <span>Warning</span>
              </div>
              <div className="flex items-center gap-1.5">
                <HealthDot status="fault" />
                <span>Critical</span>
              </div>
            </div>
          </div>

          {/* Timestamps & Chips */}
          <div className="rounded-[3px] border border-[var(--line)] bg-[var(--surface)] p-4 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--ink-2)]">
              Timestamps & Monospace Chips
            </h3>
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between items-center">
                <span className="text-[var(--ink-2)]">Just now:</span>
                <Timestamp isoString={new Date().toISOString()} />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-[var(--ink-2)]">2 hours ago:</span>
                <Timestamp isoString={new Date(Date.now() - 7200000).toISOString()} />
              </div>
            </div>
            <div className="flex flex-wrap gap-2 pt-2 border-t border-[var(--line)]">
              <MonoChip value="192.0.2.1" />
              <MonoChip value="10GE1/0/1" />
              <MonoChip value="AS65000" />
              <MonoChip value="HW-NE40E-001" />
            </div>
          </div>

          {/* Interactive Toasts & Drawer Trigger */}
          <div className="rounded-[3px] border border-[var(--line)] bg-[var(--surface)] p-4 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-[var(--ink-2)]">
              Toast & Drawer Triggers
            </h3>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => toast.success("Configuration committed successfully to CORE-ROUTER-01")}
                className="rounded-[3px] border border-[var(--ok)] bg-[var(--surface-2)] px-2.5 py-1 text-xs text-[var(--ok)] hover:bg-[var(--surface)]"
              >
                Toast Success
              </button>
              <button
                type="button"
                onClick={() => toast.warn("BGP session 192.0.2.2 flap count exceeded threshold")}
                className="rounded-[3px] border border-[var(--warn)] bg-[var(--surface-2)] px-2.5 py-1 text-xs text-[var(--warn)] hover:bg-[var(--surface)]"
              >
                Toast Warning
              </button>
              <button
                type="button"
                onClick={() => toast.error("BGP neighbor down on interface 10GE1/0/1")}
                className="rounded-[3px] border border-[var(--fault)] bg-[var(--surface-2)] px-2.5 py-1 text-xs text-[var(--fault)] hover:bg-[var(--surface)]"
              >
                Toast Error
              </button>
              <button
                type="button"
                onClick={() => setDrawerOpen(true)}
                className="rounded-[3px] bg-[var(--signal)] px-2.5 py-1 text-xs font-medium text-white hover:opacity-90"
              >
                Open Drawer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Virtualized Data Table */}
      {activeTab === "datatable" && (
        <div className="h-[520px] flex flex-col" data-testid="tab-datatable">
          <DataTable
            data={demoDevices}
            columns={deviceColumns}
            title="Managed Router Fleet"
            exportFilename="router-inventory.csv"
            height={460}
          />
        </div>
      )}

      {/* Tab 3: Virtualized Log Stream */}
      {activeTab === "logviewer" && (
        <div className="h-[520px] flex flex-col" data-testid="tab-logviewer">
          <LogViewer
            lines={sampleLogs}
            title="Automation Job Execution Stream"
            isLive={isLiveLogs}
            onToggleTail={() => setIsLiveLogs(!isLiveLogs)}
            height={460}
          />
        </div>
      )}

      {/* Tab 4: Run Timeline Swimlane */}
      {activeTab === "timeline" && (
        <div className="h-[520px] flex flex-col" data-testid="tab-timeline">
          <RunTimeline
            items={sampleTimelineRows}
            steps={timelineSteps}
            title="Bulk Configuration Deployment (Job #49102)"
            height={460}
            onSelectDevice={(id) => toast.info(`Filtered view for device: ${id}`)}
          />
        </div>
      )}

      {/* Tab 5: Configuration Diff Viewer */}
      {activeTab === "diff" && (
        <div className="h-[540px] flex flex-col" data-testid="tab-diff">
          <DiffViewer
            oldContent={sampleOldConfig}
            newContent={sampleNewConfig}
            oldLabel="Current Running Config (CORE-ROUTER-01)"
            newLabel="Proposed Staged Changes"
            title="BGP Hardening & Uplink MTU 9198 Diff"
          />
        </div>
      )}

      {/* Tab 6: Telemetry & Topology */}
      {activeTab === "telemetry" && (
        <div className="space-y-4" data-testid="tab-telemetry">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TimeSeriesChart
              title="Interface 10GE1/0/1 Throughput"
              unit="Mbps"
              data={sampleTimeSeriesData}
              series={[
                { label: "RX Traffic", stroke: "#2F5BEA", fill: "rgba(47, 91, 234, 0.08)" },
                { label: "TX Traffic", stroke: "#4CC38A", fill: "rgba(76, 195, 138, 0.08)" },
              ]}
              height={260}
            />

            <GrafanaPanel
              title="Grafana CPU & Memory Heatmap"
              src="about:blank"
              grafanaUrl="http://localhost:3000/d/router-metrics"
              timeoutMs={2000}
              height={260}
            />
          </div>

          <div>
            <div className="mb-1 text-xs font-bold uppercase tracking-wider text-[var(--ink-2)]">
              Core Path Topology Map
            </div>
            <TopologyGraph
              nodes={sampleTopologyNodes}
              edges={sampleTopologyEdges}
              height={360}
              onNodeClick={(n) => toast.info(`Selected device: ${n.data?.label} (${n.data?.ip})`)}
            />
          </div>
        </div>
      )}

      {/* High-Risk Confirm Dialog */}
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Apply Changes to 12 Routers"
        description={
          <div>
            You are about to commit configuration changes to <strong>12 Huawei routers</strong> in the core ring.
            This action can affect active BGP sessions.
          </div>
        }
        confirmMatch="12"
        confirmMatchPrompt="Type 12 to confirm execution:"
        confirmLabel="Apply 12 Changes"
        destructive
        onConfirm={() => {
          toast.success("Job #49103 dispatched to worker queue for 12 devices");
          setConfirmOpen(false);
        }}
      />

      {/* Slide-over Inspection Drawer */}
      <Drawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title="Device Telemetry Inspection"
        subtitle="CORE-ROUTER-01 (192.0.2.1)"
      >
        <div className="space-y-4 text-xs">
          <div className="space-y-2">
            <h4 className="font-semibold text-[var(--ink)]">Hardware Status</h4>
            <div className="grid grid-cols-2 gap-2 rounded bg-[var(--surface-2)] p-2.5">
              <div>
                <span className="text-[var(--ink-2)]">Chassis:</span> NE40E-X8A
              </div>
              <div>
                <span className="text-[var(--ink-2)]">Uptime:</span> 142 days 18 hrs
              </div>
              <div>
                <span className="text-[var(--ink-2)]">Active MPU:</span> Slot 9 (Master)
              </div>
              <div>
                <span className="text-[var(--ink-2)]">Memory Usage:</span> 34%
              </div>
            </div>
          </div>

          <div className="space-y-1">
            <h4 className="font-semibold text-[var(--ink)]">Recent CLI Output</h4>
            <CliOutput
              content={`<CORE-ROUTER-01>display bgp peer
 BGP local router ID : 192.0.2.1
 Local AS number : 65000
 Total number of peers : 2                 Peers in established state : 2

  Peer            V    AS  MsgRcvd  MsgSent  OutQ  Up/Down       State PrefRcv
  192.0.2.2       4 65000    48291    48302     0 14d06h   Established      42
  192.0.2.3       4 65000    12040    12041     0 04d12h   Established      15`}
            />
          </div>
        </div>
      </Drawer>
    </div>
  );
};
