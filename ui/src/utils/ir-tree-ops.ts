/**
 * IR Tree navigation and mutation helpers.
 *
 * These utilities allow us to navigate the AgentIR tree by path and
 * modify it in place, keeping the IR as the single source of truth.
 */

import type { IRNode } from "../types";

/** A path into the IR tree: e.g., ["steps", 0] or ["true_branch", "body"] */
export type IRPath = (string | number)[];

/** Result of navigating to a node at a path */
export interface PathResult {
  node: IRNode;
  parent: IRNode | null;
  parentKey: string | number | null;
}

/**
 * Deep clone an IRNode tree.
 */
export function cloneIR(node: IRNode): IRNode {
  return JSON.parse(JSON.stringify(node));
}

/**
 * Navigate to the node at the given path within the tree.
 * Returns the node, its parent, and the key in the parent that references it.
 */
export function getAtPath(root: IRNode, path: IRPath): PathResult | null {
  if (path.length === 0) {
    return { node: root, parent: null, parentKey: null };
  }

  let current: IRNode | null = root;
  let parent: IRNode | null = null;
  let parentKey: string | number | null = null;

  for (let i = 0; i < path.length; i++) {
    const key = path[i];
    parent = current;

    if (typeof key === "number") {
      // Numeric index: must be accessing a list (steps, branches)
      if (current.type === "sequence" && "steps" in current && Array.isArray(current.steps)) {
        current = current.steps[key] ?? null;
        parentKey = key;
      } else if (current.type === "parallel" && "branches" in current && Array.isArray(current.branches)) {
        current = current.branches[key] ?? null;
        parentKey = key;
      } else {
        return null;
      }
    } else {
      // String key: accessing a named child (true_branch, false_branch, body)
      if (current.type === "condition") {
        if (key === "true_branch") {
          current = current.true_branch;
        } else if (key === "false_branch") {
          current = current.false_branch;
        } else {
          return null;
        }
      } else if (current.type === "loop" && key === "body") {
        current = current.body;
      } else {
        return null;
      }
      parentKey = key;
    }

    if (current === null || current === undefined) return null;
  }

  if (!current) return null;
  return { node: current, parent, parentKey };
}

/**
 * Check if a node is a container (can hold children).
 */
export function isContainer(node: IRNode): boolean {
  return node.type === "sequence" || node.type === "parallel";
}

/**
 * Check if a node is a branching node (can hold conditional branches).
 */
export function isBranching(node: IRNode): boolean {
  return node.type === "condition";
}

/**
 * Check if a node is a leaf (agent or tool).
 */
export function isLeaf(node: IRNode): boolean {
  return node.type === "agent" || node.type === "tool" || node.type === "subworkflow";
}

/**
 * Get the list of child references from a container-like parent path.
 * For sequence: returns the steps array and the key "steps".
 * For parallel: returns the branches array and the key "branches".
 */
export function getChildList(
  parent: IRNode
): { list: IRNode[]; key: string } | null {
  if (parent.type === "sequence") {
    return { list: parent.steps, key: "steps" };
  }
  if (parent.type === "parallel") {
    return { list: parent.branches, key: "branches" };
  }
  return null;
}

/**
 * Create a default empty node of a given type.
 */
export function createDefaultNode(type: string): IRNode {
  switch (type) {
    case "agent":
      return { type: "agent", agent: "new_agent" };
    case "tool":
      return { type: "tool", tool: "new_tool" };
    case "subworkflow":
      return { type: "subworkflow", workflow: "new_subworkflow" };
    case "condition":
      return {
        type: "condition",
        expression: "true",
        true_branch: { type: "agent", agent: "placeholder" },
        false_branch: { type: "agent", agent: "placeholder" },
      };
    case "loop":
      return {
        type: "loop",
        max_iterations: 3,
        body: { type: "agent", agent: "placeholder" },
      };
    case "sequence":
      return { type: "sequence", steps: [] };
    case "parallel":
      return { type: "parallel", branches: [] };
    default:
      return { type: "agent", agent: type };
  }
}

/**
 * Add a child node to a container at the specified path.
 */
export function addChildNode(
  root: IRNode,
  containerPath: IRPath,
  childType: string,
  index?: number
): IRNode {
  const result = getAtPath(root, containerPath);
  if (!result) return root;

  const { node: container } = result;
  const child = createDefaultNode(childType);
  const childList = getChildList(container);

  if (childList) {
    if (index !== undefined && index >= 0 && index <= childList.list.length) {
      childList.list.splice(index, 0, child);
    } else {
      childList.list.push(child);
    }
  }

  return root;
}

/**
 * Remove a node at the given path from its parent.
 */
export function removeNode(root: IRNode, path: IRPath): IRNode | null {
  const result = getAtPath(root, path);
  if (!result || !result.parent || result.parentKey === null) return root;

  const { parent, parentKey } = result;

  if (typeof parentKey === "number") {
    const childList = getChildList(parent);
    if (childList) {
      childList.list.splice(parentKey, 1);
    }
  } else if (parentKey === "true_branch" && parent.type === "condition") {
    parent.true_branch = { type: "agent", agent: "placeholder" };
  } else if (parentKey === "false_branch" && parent.type === "condition") {
    parent.false_branch = { type: "agent", agent: "placeholder" };
  } else if (parentKey === "body" && parent.type === "loop") {
    parent.body = { type: "agent", agent: "placeholder" };
  }

  return root;
}

/**
 * Update a property on a node at the given path.
 * Returns a new root (immutable update via clone).
 */
export function updateNodeProperty(
  root: IRNode,
  path: IRPath,
  property: string,
  value: string | number
): IRNode {
  // We mutate in place for simplicity since the IR tree is treated as mutable
  const result = getAtPath(root, path);
  if (!result) return root;

  const { node } = result;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (node as any)[property] = value;
  return root;
}

/**
 * Get a human-readable label for the container at a path.
 */
export function getContainerLabel(node: IRNode): string {
  switch (node.type) {
    case "sequence":
      return "Sequence";
    case "parallel":
      return "Parallel";
    case "condition":
      return "Condition";
    case "loop":
      return "Loop";
    default:
      return node.type;
  }
}

/**
 * Get available child types for a container node.
 */
export function getAvailableChildTypes(_node: IRNode): string[] {
  return ["agent", "tool", "subworkflow", "condition", "loop"];
}
