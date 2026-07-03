import { useState, useCallback, useRef } from "react";

/**
 * Simple undo/redo hook for tracking IR tree changes.
 */
export function useUndoRedo<T>(initialValue: T) {
  const [history, setHistory] = useState<T[]>([initialValue]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const initialRef = useRef<T>(initialValue);

  const value = history[currentIndex];

  const pushState = useCallback((newValue: T) => {
    setHistory((prev) => {
      // Trim any "future" states if we're not at the latest
      const trimmed = prev.slice(0, currentIndex + 1);
      return [...trimmed, newValue];
    });
    setCurrentIndex((prev) => prev + 1);
  }, [currentIndex]);

  const undo = useCallback(() => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, []);

  const redo = useCallback(() => {
    setCurrentIndex((prev) => Math.min(history.length - 1, prev + 1));
  }, [history.length]);

  const resetHistory = useCallback((newValue: T) => {
    initialRef.current = newValue;
    setHistory([newValue]);
    setCurrentIndex(0);
  }, []);

  const canUndo = currentIndex > 0;
  const canRedo = currentIndex < history.length - 1;
  const isModified = currentIndex > 0 || history.length > 1;

  return {
    value,
    pushState,
    undo,
    redo,
    canUndo,
    canRedo,
    isModified,
    resetHistory,
    initialValue: initialRef.current,
  };
}
