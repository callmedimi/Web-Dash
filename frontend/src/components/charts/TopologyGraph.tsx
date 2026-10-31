import React, { useMemo, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Panel,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeProps,
  BackgroundVariant,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { cn } from "@/utils/cn";
import { HealthDot } from "@/components/ui/StatusBadge";

export interface TopologyNodeData extends Record<string, unknown> {
  label: string;
  role?: "core" | "aggregation" | "access" | "edge";
  ip?: string;
  status: "ok" | "warn" | "fault" | "info-muted";
  model?: string;
}

export interface TopologyGraphProps {
  nodes: Node<TopologyNodeData>[];
  edges: Edge[];
  height?: number | string;
  className?: string;
  onNodeClick?: (node: Node<TopologyNodeData>) => void;
}

/**
 * Custom Device Node displaying network device status, role, and IP.
 */
const DeviceNode: React.FC<NodeProps> = ({ data, selected }) => {
  const nodeData = data as unknown as TopologyNodeData;
  const statusBorder =
    nodeData.status === "ok"
      ? "border-[var(--ok)]"
      : nodeData.status === "warn"
      ? "border-[var(--warn)]"
      : nodeData.status === "fault"
      ? "border-[var(--fault)]"
      : "border-[var(--line)]";

  return (
    <div
      className={cn(
        "min-w-[150px] rounded-[3px] border bg-[var(--surface)] p-2 shadow-sm transition-all",
        statusBorder,
        selected && "ring-2 ring-[var(--signal)]"
      )}
    >
      <div className="flex items-center justify-between gap-1.5 pb-1 border-b border-[var(--line)]">
        <div className="flex items-center gap-1.5 min-w-0">
          <HealthDot status={nodeData.status} />
          <span className="truncate font-mono text-xs font-semibold text-[var(--ink)]">
            {nodeData.label}
          </span>
        </div>
        {nodeData.role && (
          <span className="rounded bg-[var(--surface-2)] px-1 py-0.5 text-[9px] uppercase tracking-wider text-[var(--ink-2)]">
            {nodeData.role}
          </span>
        )}
      </div>
      {nodeData.ip && (
        <div className="mt-1 flex items-center justify-between text-[11px] font-mono text-[var(--ink-2)]">
          <span>{nodeData.ip}</span>
          {nodeData.model && <span className="text-[10px] opacity-75">{nodeData.model}</span>}
        </div>
      )}
    </div>
  );
};

const nodeTypes = {
  device: DeviceNode,
};

/**
 * Simple layered layout algorithm for network topologies.
 * Arranges nodes by rank: core -> aggregation -> access/edge.
 */
function layoutTopologyNodes(
  rawNodes: Node<TopologyNodeData>[],
  horizontalSpacing = 220,
  verticalSpacing = 120
): Node<TopologyNodeData>[] {
  const ranks: Record<string, number> = {
    core: 0,
    aggregation: 1,
    access: 2,
    edge: 2,
  };

  const layers: Record<number, Node<TopologyNodeData>[]> = { 0: [], 1: [], 2: [], 3: [] };

  rawNodes.forEach((node) => {
    const rank = node.data?.role ? ranks[node.data.role] ?? 3 : 1;
    if (!layers[rank]) layers[rank] = [];
    layers[rank].push(node);
  });

  const positioned: Node<TopologyNodeData>[] = [];
  Object.keys(layers).forEach((key) => {
    const rankNum = Number(key);
    const layerNodes = layers[rankNum];
    const totalWidth = layerNodes.length * horizontalSpacing;
    const startX = -totalWidth / 2 + horizontalSpacing / 2;

    layerNodes.forEach((node, idx) => {
      positioned.push({
        ...node,
        type: "device",
        position: {
          x: startX + idx * horizontalSpacing + 300,
          y: rankNum * verticalSpacing + 50,
        },
      });
    });
  });

  return positioned;
}

/**
 * Interactive Network Topology Graph component for NOC visualization.
 */
export const TopologyGraph: React.FC<TopologyGraphProps> = ({
  nodes: initialNodes,
  edges: initialEdges,
  height = 420,
  className,
  onNodeClick,
}) => {
  const layoutedNodes = useMemo(() => layoutTopologyNodes(initialNodes), [initialNodes]);

  const styledEdges = useMemo(() => {
    return initialEdges.map((e) => ({
      ...e,
      style: { stroke: "var(--line)", strokeWidth: 1.5, ...e.style },
      labelStyle: { fill: "var(--ink-2)", fontSize: 10, fontFamily: "JetBrains Mono, monospace" },
      markerEnd: e.markerEnd ?? { type: MarkerType.ArrowClosed, color: "var(--line)", width: 12, height: 12 },
    }));
  }, [initialEdges]);

  const [nodes, , onNodesChange] = useNodesState(layoutedNodes);
  const [edges, , onEdgesChange] = useEdgesState(styledEdges);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (onNodeClick) {
        onNodeClick(node as Node<TopologyNodeData>);
      }
    },
    [onNodeClick]
  );

  return (
    <div
      className={cn(
        "relative rounded-[3px] border border-[var(--line)] bg-[var(--surface)] overflow-hidden",
        className
      )}
      style={{ height }}
      data-testid="topology-graph"
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--line)" />
        <Controls
          className="!bg-[var(--surface)] !border-[var(--line)] !shadow-sm [&>button]:!bg-[var(--surface)] [&>button]:!border-[var(--line)] [&>button]:!fill-[var(--ink)]"
          showInteractive={false}
        />
        <MiniMap
          className="!bg-[var(--surface-2)] !border-[var(--line)] !rounded-[3px]"
          nodeColor={(n) => {
            const status = (n.data as TopologyNodeData)?.status;
            if (status === "ok") return "#4CC38A";
            if (status === "warn") return "#E8B04A";
            if (status === "fault") return "#FF6B5B";
            return "#7C8DA3";
          }}
          maskColor="rgba(0,0,0, 0.15)"
        />
        <Panel position="top-right" className="flex items-center gap-2">
          <div className="flex items-center gap-1 rounded-[3px] border border-[var(--line)] bg-[var(--surface)] px-2 py-1 text-xs text-[var(--ink-2)]">
            <span className="font-semibold text-[var(--ink)]">{nodes.length}</span> devices ·{" "}
            <span className="font-semibold text-[var(--ink)]">{edges.length}</span> links
          </div>
        </Panel>
      </ReactFlow>
    </div>
  );
};
