/** Open-vocabulary targets used by the live Grounding DINO discovery pass. */

export const MAX_OBJECT_PROMPTS = 32;

export const DEFAULT_LIVE_PROMPTS = [
  "person",
  "phone",
  "earbuds",
  "keys",
  "wallet",
  "card",
  "whiteboard",
  "wall decoration",
  "picture frame",
  "poster",
  "sticky note",
  "computer mouse",
  "laptop",
  "monitor",
  "keyboard",
  "notebook",
  "book",
  "paper",
  "pen",
  "pencil",
  "bottle",
  "cup",
  "mug",
  "headphones",
  "charger",
  "cable",
  "backpack",
  "remote control",
  "speaker",
  "lamp",
  "box",
  "tablet",
] as const;

export const SYNTHETIC_PROMPTS = ["cup", "book", "phone"] as const;

export function normalizeObjectPrompts(prompts: readonly string[]): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];
  for (const prompt of prompts) {
    const value = prompt.trim().replace(/\s+/g, " ").toLowerCase();
    if (value.length === 0 || seen.has(value)) {
      continue;
    }
    seen.add(value);
    normalized.push(value);
    if (normalized.length === MAX_OBJECT_PROMPTS) {
      break;
    }
  }
  return normalized;
}

export function parseObjectPrompts(value: string): string[] {
  return normalizeObjectPrompts(value.split(","));
}
