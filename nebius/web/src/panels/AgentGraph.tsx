import { useQuery } from "@tanstack/react-query";
import { Background, type Edge, Handle, type Node, type NodeProps, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { api } from "@/api/client";
import { cn } from "@/lib/utils";

export type NodeStatus = "idle" | "running" | "done" | "warn" | "failed";

interface Shape { nodes: string[]; edges: { source: string; target: string; conditional: boolean }[] }

const LABELS: Record<string, string> = {
  __start__: "Your request", understand: "Brief agent", locate: "Map lookup", design: "Designer agent",
  layout: "Layout solver", estimate: "Planning ratios", create: "Project", simulate: "Simulation sandbox",
  sweep: "Scenario sandboxes", review: "Safety officer", __end__: "Plan ready",
};
const POS: Record<string, [number, number]> = {
  __start__: [70, 0], understand: [70, 52], locate: [0, 104], design: [140, 156], layout: [0, 156],
  estimate: [70, 208], create: [70, 260], simulate: [70, 312], sweep: [70, 364], review: [70, 416], __end__: [70, 468],
};

function GraphNode({ data }: NodeProps<Node<{ label: string; status: NodeStatus }>>) {
  const s = data.status;
  return (
    <div className={cn(
      "relative w-[130px] rounded-full border px-2.5 py-1 text-center text-[11px] font-medium shadow-sm transition-colors",
      s === "running" && "border-signal bg-signal text-signal-ink shadow-[0_0_14px_var(--signal)]",
      s === "done" && "border-egress bg-egress-soft text-ink",
      s === "warn" && "border-caution bg-caution-soft text-ink",
      s === "failed" && "border-danger bg-danger-soft text-ink",
      s === "idle" && "border-border bg-surface text-muted",
    )}>
      <Handle type="target" position={Position.Top} className="!h-1 !w-1 !border-0 !bg-transparent" />
      {s === "running" && <span className="absolute -right-1 -top-1 size-2.5 animate-ping rounded-full bg-signal" />}
      {data.label}
      <Handle type="source" position={Position.Bottom} className="!h-1 !w-1 !border-0 !bg-transparent" />
    </div>
  );
}

const nodeTypes = { agent: GraphNode };

/** The Copilot's LangGraph, drawn from the server's compiled graph, lit up as nodes run. */
export function AgentGraph({ status }: { status: Record<string, NodeStatus> }) {
  const shape = useQuery({ queryKey: ["copilot-graph"], queryFn: () => api.get<Shape>("/copilot/graph"), staleTime: Infinity });
  const { nodes, edges } = useMemo(() => {
    const s = shape.data;
    if (!s) return { nodes: [] as Node[], edges: [] as Edge[] };
    const any = Object.keys(status).length > 0;
    const nodes: Node[] = s.nodes.map((id) => {
      const st: NodeStatus = id === "__start__" ? (any ? "done" : "idle")
        : id === "__end__" ? (status.review === "done" ? "done" : "idle") : status[id] ?? "idle";
      return { id, type: "agent", position: { x: POS[id]?.[0] ?? 70, y: POS[id]?.[1] ?? 0 }, data: { label: LABELS[id] ?? id, status: st }, draggable: false };
    });
    const edges: Edge[] = s.edges.map((e) => {
      const live = status[e.target] === "running";
      const taken = (status[e.source] === "done" || status[e.source] === "warn" || e.source === "__start__") && (status[e.target] ?? "idle") !== "idle";
      return {
        id: `${e.source}-${e.target}`, source: e.source, target: e.target, animated: live,
        style: { stroke: taken || live ? "var(--signal)" : "var(--border)", strokeWidth: taken || live ? 2 : 1.2, strokeDasharray: e.conditional && !taken ? "4 3" : undefined },
      };
    });
    return { nodes, edges };
  }, [shape.data, status]);
  return (
    <div className="h-[500px] w-[300px] shrink-0 rounded-[10px] border border-border bg-plan/60" aria-label="Agent graph">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} defaultViewport={{ x: 15, y: 12, zoom: 1 }}
                 nodesConnectable={false} elementsSelectable={false} panOnDrag={false} zoomOnScroll={false}
                 zoomOnPinch={false} zoomOnDoubleClick={false} proOptions={{ hideAttribution: true }}>
        <Background gap={16} size={1} color="var(--border)" />
      </ReactFlow>
    </div>
  );
}
