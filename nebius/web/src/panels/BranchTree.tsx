import { Background, type Edge, Handle, type Node, type NodeProps, Position, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { TreeNode } from "@/api/useSessionStream";
import { fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";

type FlowData = { node: TreeNode; active: boolean; human: (text: string) => string };

const KIND_LABEL: Record<TreeNode["kind"], string> = { baseline: "Baseline", attack: "Attack", fix: "Fix", final: "Confirmed" };

function BranchCard({ data }: NodeProps<Node<FlowData>>) {
  const n = data.node;
  const tone = n.status === "break" ? "border-l-danger" : n.status === "ok" ? (n.kind === "fix" && n.accepted ? "border-l-egress" : "border-l-egress")
    : n.status === "rejected" ? "border-l-line" : n.status === "failed" ? "border-l-caution" : "border-l-signal";
  const peak = n.metrics?.peak_density_ppm2;
  return (
    <div className={cn("w-[260px] rounded-[8px] border border-border border-l-[3px] bg-surface px-2.5 py-1.5 text-left shadow-sm transition",
      tone, data.active && "ring-2 ring-signal", n.status === "running" && "animate-pulse")}>
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-line" />
      <div className="flex items-center justify-between text-[10px] font-medium uppercase-none text-muted">
        <span>{KIND_LABEL[n.kind]}{n.fix_id ? ` ${n.fix_id}` : n.attack_id && n.kind === "attack" ? ` ${n.attack_id}` : ""}</span>
        {n.kind === "fix" && n.accepted != null && (
          <span className={n.accepted ? "text-egress" : "text-muted"}>{n.accepted ? "Kept" : "Not kept"}</span>
        )}
        {n.kind !== "fix" && n.status === "break" && <span className="text-danger">Breaks</span>}
        {n.kind !== "fix" && n.status === "ok" && <span className="text-egress">Holds</span>}
      </div>
      <p className="truncate text-xs font-medium text-ink" title={data.human(n.label)}>{data.human(n.label)}</p>
      <p className="text-[10px] tabular text-muted">
        {n.status === "running" ? "Simulating…" : peak != null ? `${fmtNum(peak, 1)} per m²` : "–"}
        {n.metrics?.time_above_danger_s ? ` · ${Math.round(n.metrics.time_above_danger_s)} s danger` : ""}
      </p>
      <Handle type="source" position={Position.Bottom} style={{ left: 12 }} className="!size-1.5 !border-0 !bg-line" />
    </div>
  );
}

const nodeTypes = { branch: BranchCard };

const ROW = 62;
const INDENT = 28;

/** Indented tree (like a file tree): baseline, then each attack with its fixes, then the confirmations. */
function layout(nodes: TreeNode[]): { pos: Record<string, { x: number; y: number }>; height: number } {
  const pos: Record<string, { x: number; y: number }> = {};
  const fixesBy = new Map<string, TreeNode[]>();
  for (const n of nodes.filter((x) => x.kind === "fix")) {
    const k = n.parent_id ?? "";
    fixesBy.set(k, [...(fixesBy.get(k) ?? []), n]);
  }
  let y = 0;
  for (const n of nodes.filter((x) => x.kind === "baseline")) { pos[n.node_id] = { x: 0, y }; y += ROW; }
  for (const a of nodes.filter((x) => x.kind === "attack")) {
    pos[a.node_id] = { x: INDENT, y };
    y += ROW;
    for (const f of fixesBy.get(a.node_id) ?? []) { pos[f.node_id] = { x: 2 * INDENT, y }; y += ROW; }
  }
  for (const n of nodes.filter((x) => x.kind === "final")) { pos[n.node_id] = { x: INDENT, y }; y += ROW; }
  return { pos, height: y };
}

export function BranchTree({ nodes, activeRunId, onPick, human = (x) => x }: {
  nodes: Record<string, TreeNode>; activeRunId: string | null; onPick: (n: TreeNode) => void; human?: (text: string) => string;
}) {
  const list = useMemo(() => Object.values(nodes), [nodes]);
  const { flowNodes, edges, height } = useMemo(() => {
    const { pos, height } = layout(list);
    const flowNodes: Node<FlowData>[] = list.map((n) => ({
      id: n.node_id, type: "branch", position: pos[n.node_id] ?? { x: 0, y: 0 },
      data: { node: n, active: n.run_id === activeRunId, human }, draggable: false,
    }));
    const edges: Edge[] = list.filter((n) => n.parent_id && nodes[n.parent_id]).map((n) => ({
      id: `${n.parent_id}->${n.node_id}`, source: n.parent_id as string, target: n.node_id, type: "smoothstep",
      style: { stroke: n.status === "break" ? "var(--danger)" : n.accepted ? "var(--egress)" : "var(--border-strong)", strokeWidth: 1.5 },
      animated: n.status === "running",
    }));
    return { flowNodes, edges, height };
  }, [list, nodes, activeRunId, human]);
  if (!list.length) return <p className="p-4 text-sm text-muted">The tree grows as attacks and fixes are simulated.</p>;
  return (
    <div className="overflow-hidden rounded-[10px] border border-border bg-plan" style={{ height: height + 24 }}
         aria-label="Branch tree of simulated scenarios">
      {/* full size, no inner pan/zoom: the side panel scrolls, so every branch stays readable */}
      <ReactFlow nodes={flowNodes} edges={edges} nodeTypes={nodeTypes} defaultViewport={{ x: 12, y: 12, zoom: 1 }}
                 proOptions={{ hideAttribution: true }} nodesConnectable={false} elementsSelectable
                 panOnDrag={false} zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false}
                 preventScrolling={false} onNodeClick={(_, n) => onPick((n.data as FlowData).node)}>
        <Background gap={20} size={1} color="var(--border)" />
      </ReactFlow>
    </div>
  );
}
