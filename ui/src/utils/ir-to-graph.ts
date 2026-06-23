/**
 * Convert an AgentIR tree to ReactFlow nodes and edges.
 *
 * Strategy: recursively flatten the tree to a DAG, similar to the compiler's
 * legacy _flatten_node but producing visual layout coordinates.
 */

import type { IRNode, FlowNode, FlowEdge } from "../types";

interface Graph {
  nodes: FlowNode[];
  edges: FlowEdge[];
  nextId: number;
  nextRow: number;
}

const NODE_W = 180;
const NODE_H = 60;
const GAP_X = 80;
const GAP_Y = 120;

function newGraph(): Graph {
  return { nodes: [], edges: [], nextId: 1, nextRow: 0 };
}

function makeId(g: Graph, prefix = "n"): string {
  return `${prefix}_${g.nextId++}`;
}

function nodeLabel(n: IRNode): { label: string; kind: string } {
  switch (n.type) {
    case "agent":
      return { label: n.agent, kind: "agent" };
    case "tool":
      return { label: n.tool, kind: "tool" };
    case "condition":
      return { label: n.expression, kind: "condition" };
    case "loop":
      return { label: `loop ×${n.max_iterations}`, kind: "loop" };
    default:
      return { label: n.type, kind: "helper" };
  }
}

function isLeaf(n: IRNode): boolean {
  return n.type === "agent" || n.type === "tool";
}

function addNode(g: Graph, n: IRNode, x: number, y: number): string {
  const id = makeId(g);
  const { label, kind } = nodeLabel(n);
  g.nodes.push({
    id,
    type: kind,
    position: { x, y },
    data: { label, kind },
  });
  return id;
}

function flatten(
  node: IRNode,
  g: Graph,
  fromId: string,
  startX: number,
  startY: number
): { exitId: string; width: number } {
  if (isLeaf(node)) {
    const id = addNode(g, node, startX, startY);
    g.edges.push({
      id: makeId(g, "e"),
      source: fromId,
      target: id,
    });
    return { exitId: id, width: NODE_W };
  }

  if (node.type === "sequence") {
    let currentId = fromId;
    let totalHeight = startY;
    let maxWidth = NODE_W;
    for (const step of node.steps) {
      const result = flatten(step, g, currentId, startX, totalHeight);
      currentId = result.exitId;
      totalHeight += GAP_Y;
      if (result.width > maxWidth) maxWidth = result.width;
    }
    return { exitId: currentId, width: maxWidth };
  }

  if (node.type === "condition") {
    const condId = makeId(g);
    const { label } = nodeLabel(node);
    g.nodes.push({
      id: condId,
      type: "condition",
      position: { x: startX, y: startY },
      data: { label, kind: "condition" },
    });
    g.edges.push({ id: makeId(g, "e"), source: fromId, target: condId });

    const trueResult = flatten(node.true_branch, g, condId, startX - 100, startY + GAP_Y);
    g.edges[g.edges.length - 1] = {
      ...g.edges[g.edges.length - 1],
      label: "true",
    };

    const falseResult = flatten(node.false_branch, g, condId, startX + 100, startY + GAP_Y);
    const lastFalseEdge = g.edges[g.edges.length - 1];
    lastFalseEdge.label = "false";

    // Merge point
    const mergeId = makeId(g);
    const mergeY = startY + GAP_Y * 2;
    g.nodes.push({
      id: mergeId,
      type: "helper",
      position: { x: startX, y: mergeY },
      data: { label: "merge", kind: "helper" },
    });
    g.edges.push({ id: makeId(g, "e"), source: trueResult.exitId, target: mergeId });
    g.edges.push({ id: makeId(g, "e"), source: falseResult.exitId, target: mergeId });

    return { exitId: mergeId, width: 300 };
  }

  if (node.type === "parallel") {
    const forkId = makeId(g);
    g.nodes.push({
      id: forkId,
      type: "helper",
      position: { x: startX, y: startY },
      data: { label: "fork", kind: "helper" },
    });
    g.edges.push({ id: makeId(g, "e"), source: fromId, target: forkId });

    const branchExits: string[] = [];
    const spread = node.branches.length > 1 ? (node.branches.length - 1) * 200 : 0;
    for (let i = 0; i < node.branches.length; i++) {
      const bx = startX - spread / 2 + i * 200;
      const result = flatten(node.branches[i], g, forkId, bx, startY + GAP_Y);
      branchExits.push(result.exitId);
    }

    const joinId = makeId(g);
    g.nodes.push({
      id: joinId,
      type: "helper",
      position: { x: startX, y: startY + GAP_Y * 2 },
      data: { label: "join", kind: "helper" },
    });
    for (const exitId of branchExits) {
      g.edges.push({ id: makeId(g, "e"), source: exitId, target: joinId });
    }
    return { exitId: joinId, width: Math.max(NODE_W, spread + NODE_W) };
  }

  if (node.type === "loop") {
    const loopId = makeId(g);
    g.nodes.push({
      id: loopId,
      type: "loop",
      position: { x: startX, y: startY },
      data: { label: `loop ×${node.max_iterations}`, kind: "loop" },
    });
    g.edges.push({ id: makeId(g, "e"), source: fromId, target: loopId });

    const bodyResult = flatten(node.body, g, loopId, startX, startY + GAP_Y);
    // Loop back
    g.edges.push({
      id: makeId(g, "e"),
      source: bodyResult.exitId,
      target: loopId,
      label: `retry (<${node.max_iterations})`,
      animated: true,
      style: { strokeDasharray: "5 5" },
    });

    const exitId = makeId(g);
    g.nodes.push({
      id: exitId,
      type: "helper",
      position: { x: startX + GAP_X, y: startY },
      data: { label: "exit", kind: "helper" },
    });
    g.edges.push({
      id: makeId(g, "e"),
      source: loopId,
      target: exitId,
      label: "done",
    });

    return { exitId, width: 300 };
  }

  return { exitId: fromId, width: NODE_W };
}

export function irToGraph(root: IRNode): { nodes: FlowNode[]; edges: FlowEdge[] } {
  const g = newGraph();
  // Virtual START node
  g.nodes.push({
    id: "START",
    type: "helper",
    position: { x: 400, y: 0 },
    data: { label: "START", kind: "helper" },
  });
  flatten(root, g, "START", 400, NODE_H);
  return { nodes: g.nodes, edges: g.edges };
}
