import { memo, useEffect, useMemo, useState } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { NodeType } from "@dataform-dag/core";
import type { FlowGraph } from "./graphToFlow.js";

export interface DagGraphProps {
  graph: FlowGraph;
  selectedId: string | null;
  /** Bumped by the host asking to focus a node; pans/zooms to it. */
  focus: { nodeId: string; nonce: number } | null;
  onSelectNode: (nodeId: string) => void;
}

type ModelNodeData = {
  label: string;
  color: string;
  nodeType: NodeType;
  selected: boolean;
  dimmed: boolean;
};
type ModelNode = Node<ModelNodeData, "model">;

/** A model as a card: type-colored left accent, monospace name, type label. Sized by its label. */
const ModelNode = memo(function ModelNode({ data }: NodeProps<ModelNode>) {
  const cls = `ddag-node${data.selected ? " is-selected" : ""}${data.dimmed ? " is-dimmed" : ""}`;
  return (
    <div className={cls} style={{ ["--accent" as string]: data.color }}>
      <Handle type="target" position={Position.Left} className="ddag-node__handle" />
      <span className="ddag-node__label">{data.label}</span>
      <span className="ddag-node__type">{data.nodeType}</span>
      <Handle type="source" position={Position.Right} className="ddag-node__handle" />
    </div>
  );
});

const nodeTypes = { model: ModelNode };

/** React Flow canvas. Owns only rendering + focus; all graph shape comes from {@link FlowGraph}. */
export function DagGraph(props: DagGraphProps): JSX.Element {
  return (
    <ReactFlowProvider>
      <DagCanvas {...props} />
    </ReactFlowProvider>
  );
}

function DagCanvas({ graph, selectedId, focus, onSelectNode }: DagGraphProps): JSX.Element {
  // useNodesState/useEdgesState (not raw controlled props) so nodes stay interactive — draggable and
  // selectable. Controlled `nodes=` without an onNodesChange handler renders them frozen (RF #002).
  const [nodes, setNodes, onNodesChange] = useNodesState<ModelNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  // The node whose relationships we emphasize: hover wins over selection so you can trace by pointing.
  const focusId = hoveredId ?? selectedId;
  // Edges touching the focused node, and the neighbor set to keep bright while the rest fade.
  const { activeEdges, activeNodes } = useMemo(() => {
    if (!focusId) return { activeEdges: null, activeNodes: null };
    const e = new Set<string>();
    const n = new Set<string>([focusId]);
    for (const edge of graph.edges) {
      if (edge.source === focusId || edge.target === focusId) {
        e.add(edge.id);
        n.add(edge.source);
        n.add(edge.target);
      }
    }
    return { activeEdges: e, activeNodes: n };
  }, [focusId, graph.edges]);
  // Rebuild positions from the dagre layout only when the graph itself changes (preserves drags).
  useEffect(() => {
    setNodes(
      graph.nodes.map((n) => ({
        id: n.id,
        type: "model" as const,
        position: n.position,
        width: n.width,
        height: n.height,
        data: {
          label: n.data.label,
          color: n.data.color,
          nodeType: n.data.nodeType,
          selected: false,
          dimmed: false,
        },
      })),
    );
    setEdges(
      graph.edges.map((e) => ({ id: e.id, source: e.source, target: e.target, type: "default" })),
    );
  }, [graph, setNodes, setEdges]);
  // Re-derive emphasis (selection ring + focus dimming) without disturbing positions.
  useEffect(() => {
    setNodes((nds) =>
      nds.map((n) => ({
        ...n,
        data: {
          ...n.data,
          selected: n.id === selectedId,
          dimmed: activeNodes != null && !activeNodes.has(n.id),
        },
      })),
    );
    setEdges((eds) =>
      eds.map((e) => {
        const active = activeEdges != null && activeEdges.has(e.id);
        const faded = activeEdges != null && !active;
        return {
          ...e,
          style: {
            stroke: active ? "#334155" : "#c3ccd6",
            strokeWidth: active ? 2 : 1.5,
            opacity: faded ? 0.12 : 1,
          },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            width: 15,
            height: 15,
            color: active ? "#334155" : "#c3ccd6",
          },
          zIndex: active ? 10 : 0,
        };
      }),
    );
  }, [selectedId, activeEdges, activeNodes, setNodes, setEdges]);
  const { setCenter } = useReactFlow();
  useEffect(() => {
    if (!focus) return;
    const target = graph.nodes.find((n) => n.id === focus.nodeId);
    if (target) {
      setCenter(target.position.x + target.width / 2, target.position.y + target.height / 2, {
        zoom: 1.2,
        duration: 400,
      });
    }
  }, [focus, graph.nodes, setCenter]);
  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      onNodeClick={(_, node) => onSelectNode(node.id)}
      onNodeMouseEnter={(_, node) => setHoveredId(node.id)}
      onNodeMouseLeave={() => setHoveredId(null)}
      minZoom={0.2}
      fitView
      fitViewOptions={{ padding: 0.2 }}
      proOptions={{ hideAttribution: true }}
    >
      <Background color="#dbe1e8" gap={20} />
      <Controls showInteractive={false} />
      <MiniMap pannable zoomable nodeColor={(n) => (n.data as ModelNodeData).color} />
    </ReactFlow>
  );
}
