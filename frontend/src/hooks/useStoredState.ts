import { useState } from "react";

/** Local UI preferences only: never store questions, production inputs or credentials. */
export function useStoredState<T extends string | boolean | null>(key: string, fallback: T) {
  const [value, setValue] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`opspilot:${key}`);
      if (raw === null) return fallback;
      const parsed = JSON.parse(raw);
      return (
        fallback === null
          ? parsed === null || typeof parsed === "string"
          : typeof parsed === typeof fallback
      )
        ? (parsed as T)
        : fallback;
    } catch {
      return fallback;
    }
  });
  function update(next: T) {
    setValue(next);
    try {
      localStorage.setItem(`opspilot:${key}`, JSON.stringify(next));
    } catch {
      /* Optional storage. */
    }
  }
  return [value, update] as const;
}
