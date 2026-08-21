import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(date: string | null | undefined): string {
  if (!date) return "—"
  return new Date(date).toLocaleDateString("en-US", {
    year: "numeric", month: "short", day: "numeric",
  })
}
