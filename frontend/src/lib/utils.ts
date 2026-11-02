import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * shadcn/ui-style class name merger: clsx for conditional classes,
 * tailwind-merge to resolve conflicting Tailwind utilities.
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
