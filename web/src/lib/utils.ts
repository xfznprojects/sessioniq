import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Strong ease-out for entrances — built-in CSS easings are too weak; this
// gives immediate, intentional motion.
export const EASE_OUT = [0.23, 1, 0.32, 1] as const;

export function formatSeconds(value?: number | null) {
  if (value == null) return "—";
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}
