/**
 * Convert an AgentIR tree to ReactFlow nodes and edges.
 *
 * Uses dagre for automatic layout. Each generated node includes an ``irPath``
 * that maps back to its location in the AgentIR tree for bidirectional editing.
 */

import dagre from "dagre";
import type { IRNode, FlowNode, FlowEdge } from "../types";
import type { IRPath } from "./ir-tree-ops";

const NODE_WIDTH = 170;
const NODE_HEIGHT = 60;
const HELPER_WIDTH = 90;
const HELPER_HEIGHT = 40;

interface Graph {
  nodes: FlowNode[];
  edges: FlowEdge[];
  nextId: number;
}

function newGraph(): Graph {
  return { nodes: [], edges: [], nextId: 1 };
}

function makeId(g: Graph, prefix = "n"): string {
  return `${prefix}_${g.nextId++}`;
}

function nodeLabel(n: IRNode): { label: string; kind: string } {
  switch (n.type) {
    case "agent":  return { label: n.agent, kind: "agent" };
    case "tool":   return { label: n.tool, kind: "tool" };
    case "subworkflow": return { label: n.workflow, kind: "subworkflow" };
    case "condition": return { label: n.expression, kind: "condition" };
    case "loop":   return { label: `loop ×${n.max_iterations}`, kind: "loop" };
    default:       return { label: n.type, kind: "helper" };
  }
}

function isLeaf(n: IRNode): boolean {
  return n.type === "agent" || n.type === "tool" || n.type === "subworkflow";
}

function addNode(g: Graph, n: IRNode, irPath?: IRPath): string {
  const id = makeId(g);
  const { label, kind } = nodeLabel(n);
  g.nodes.push({
    id,
    type: kind,
    position: { x: 0, y: 0 }, // dagre will calculate positions
    data: { label, kind, irPath, irNode: n },
    width: isLeaf(n) ? NODE_WIDTH : (kind === "condition" ? NODE_WIDTH : HELPER_WIDTH),
    height: NODE_HEIGHT,
  } as FlowNode);
  return id;
}

function addHelper(g: Graph, label: string): string {
  const id = makeId(g);
  g.nodes.push({
    id,
    type: "helper",
    position: { x: 0, y: 0 },
    data: { label, kind: "helper" },
    width: HELPER_WIDTH,
    height: HELPER_HEIGHT,
  } as FlowNode);
  return id;
}

function addEdge(g: Graph, source: string, target: string, opts?: Partial<FlowEdge>): void {
  g.edges.push({
    id: makeId(g, "e"),
    source,
    target,
    ...opts,
  });
}

/**
 * Flatten the IR tree into nodes and edges (structure only, no positioning).
 * Positioning is handled by dagre after flattening.
 */
function flatten(
  node: IRNode,
  g: Graph,
  fromId: string,
  irPath: IRPath = []
): { exitId: string } {
  if (isLeaf(node)) {
    const id = addNode(g, node, irPath);
    addEdge(g, fromId, id);
    return { exitId: id };
  }

  if (node.type === "sequence") {
    let currentId = fromId;
    for (let i = 0; i < node.steps.length; i++) {
      const stepPath = [...irPath, "steps", i];
      const result = flatten(node.steps[i], g, currentId, stepPath);
      currentId = result.exitId;
    }
    return { exitId: currentId };
  }

  if (node.type === "condition") {
    const condId = addNode(g, node, irPath);
    addEdge(g, fromId, condId);

    const truePath = [...irPath, "true_branch"];
    const trueResult = flatten(node.true_branch, g, condId, truePath);
    // Tag the last edge as "true"
    g.edges[g.edges.length - 1] = { ...g.edges[g.edges.length - 1], label: "true" };

    const falsePath = [...irPath, "false_branch"];
    const falseResult = flatten(node.false_branch, g, condId, falsePath);
    g.edges[g.edges.length - 1] = { ...g.edges[g.edges.length - 1], label: "false" };

    // Merge point
    const mergeId = addHelper(g, "merge");
    addEdge(g, trueResult.exitId, mergeId);
    addEdge(g, falseResult.exitId, mergeId);

    return { exitId: mergeId };
  }

  if (node.type === "parallel") {
    const forkId = addHelper(g, "fork");
    addEdge(g, fromId, forkId);

    const branchExits: string[] = [];
    for (let i = 0; i < node.branches.length; i++) {
      const branchPath = [...irPath, "branches", i];
      const result = flatten(node.branches[i], g, forkId, branchPath);
      branchExits.push(result.exitId);
    }

    const joinId = addHelper(g, "join");
    for (const exitId of branchExits) {
      addEdge(g, exitId, joinId);
    }
    return { exitId: joinId };
  }

  if (node.type === "loop") {
    const loopId = addNode(g, node, irPath);
    addEdge(g, fromId, loopId);

    const bodyPath = [...irPath, "body"];
    const bodyResult = flatten(node.body, g, loopId, bodyPath);

    // Loop back edge
    addEdge(g, bodyResult.exitId, loopId, {
      label: `retry (<${node.max_iterations})`,
      animated: true,
      style: { strokeDasharray: "5 5" },
    });

    const exitId = addHelper(g, "exit");
    addEdge(g, loopId, exitId, { label: "done" });

    return { exitId };
  }

  return { exitId: fromId };
}

/**
 * Run dagre layout on the flattened graph.
 */
function applyDagreLayout(g: Graph): void {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({
    rankdir: "TB",
    ranksep: 80,
    nodesep: 50,
    edgesep: 20,
    marginx: 40,
    marginy: 40,
  });

  for (const node of g.nodes) {
    const w = node.width ?? NODE_WIDTH;
    const h = node.height ?? NODE_HEIGHT;
    dagreGraph.setNode(node.id, { width: w, height: h });
  }

  for (const edge of g.edges) {
    dagreGraph.setEdge(edge.source, edge.target);
  }

  dagre.layout(dagreGraph);

  // Apply computed positions
  for (const node of g.nodes) {
    const dagreNode = dagreGraph.node(node.id);
    if (dagreNode) {
      const w = node.width ?? NODE_WIDTH;
      const h = node.height ?? NODE_HEIGHT;
      node.position = {
        x: dagreNode.x - w / 2,
        y: dagreNode.y - h / 2,
      };
    }
  }
}

export function irToGraph(root: IRNode): {
  nodes: FlowNode[];
  edges: FlowEdge[];
} {
  const g = newGraph();

  // Virtual START node
  g.nodes.push({
    id: "START",
    type: "helper",
    position: { x: 0, y: 0 },
    data: { label: "START", kind: "helper" },
    width: HELPER_WIDTH,
    height: HELPER_HEIGHT,
  } as FlowNode);

  flatten(root, g, "START", []);

  // Apply dagre auto-layout
  applyDagreLayout(g);

  return { nodes: g.nodes, edges: g.edges };
}
