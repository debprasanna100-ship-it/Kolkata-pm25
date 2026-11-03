import { ModelMetrics, ProxyAgreementItem } from "./types/atmospheric";

export function parseCSV<T = Record<string, any>>(csvText: string): T[] {
  const lines = csvText.trim().split(/\r?\n/);
  if (lines.length < 2) return [];

  const headers = lines[0].split(",").map((h) => h.trim());
  const rows: T[] = [];

  for (let i = 1; i < lines.length; i++) {
    const currentLine = lines[i];
    if (!currentLine.trim()) continue;

    // Handle standard CSV cells (including potential quotes)
    const values: string[] = [];
    let insideQuotes = false;
    let currentValue = "";

    for (let charIndex = 0; charIndex < currentLine.length; charIndex++) {
      const char = currentLine[charIndex];
      if (char === '"') {
        insideQuotes = !insideQuotes;
      } else if (char === "," && !insideQuotes) {
        values.push(currentValue.trim());
        currentValue = "";
      } else {
        currentValue += char;
      }
    }
    values.push(currentValue.trim());

    const obj: any = {};
    headers.forEach((header, idx) => {
      let val: any = values[idx] ?? "";
      if (val.startsWith('"') && val.endsWith('"')) {
        val = val.slice(1, -1);
      }
      if (val === "" || val === "NaN") {
        obj[header] = null;
      } else if (!isNaN(Number(val)) && val !== "") {
        obj[header] = Number(val);
      } else if (val === "True" || val === "true") {
        obj[header] = true;
      } else if (val === "False" || val === "false") {
        obj[header] = false;
      } else {
        obj[header] = val;
      }
    });
    rows.push(obj as T);
  }

  return rows;
}

/**
 * Parse JSON that may contain bare NaN/Infinity tokens (Python's json.dumps
 * emits them by default, and they are invalid per RFC 8259). We replace the
 * tokens with null before parsing so the browser's strict JSON.parse succeeds.
 */
function parseLenientJSON(text: string): any {
  // Replace bare NaN / Infinity / -Infinity tokens that appear as object or
  // array values (i.e. preceded by ':' or ',' and not inside a quoted string)
  // with null. A tiny scanner keeps this correct even if a quoted value ever
  // contains the substring "NaN".
  let out = "";
  let inString = false;
  let escape = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      out += ch;
      if (escape) escape = false;
      else if (ch === "\\") escape = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') {
      inString = true;
      out += ch;
      continue;
    }
    const rest = text.slice(i);
    const m = rest.match(/^(NaN|-Infinity|Infinity)(?=[\s,\]}:]|$)/);
    if (m) {
      out += "null";
      i += m[1].length - 1;
      continue;
    }
    out += ch;
  }
  return JSON.parse(out);
}

export async function fetchMetrics(): Promise<Record<string, any> | null> {
  try {
    const res = await fetch("/data/metrics.json");
    if (!res.ok) return null;
    return parseLenientJSON(await res.text());
  } catch {
    return null;
  }
}

export async function fetchAttributionSummary(): Promise<Record<string, any> | null> {
  try {
    const res = await fetch("/data/attribution_summary.json");
    if (!res.ok) return null;
    return parseLenientJSON(await res.text());
  } catch {
    return null;
  }
}

export async function fetchProxyAgreement(): Promise<ProxyAgreementItem[]> {
  try {
    const res = await fetch("/data/proxy_agreement.csv");
    if (!res.ok) return [];
    const text = await res.text();
    return parseCSV<ProxyAgreementItem>(text);
  } catch {
    return [];
  }
}

export async function fetchSeasonalImportance(): Promise<any[]> {
  try {
    const res = await fetch("/data/seasonal_importance.csv");
    if (!res.ok) return [];
    const text = await res.text();
    return parseCSV(text);
  } catch {
    return [];
  }
}

export async function fetchGlobalImportance(): Promise<any[]> {
  try {
    const res = await fetch("/data/importance_attrib.csv");
    if (!res.ok) return [];
    const text = await res.text();
    return parseCSV(text);
  } catch {
    return [];
  }
}

export async function fetchProxyPrevalence(): Promise<any[]> {
  try {
    const res = await fetch("/data/proxy_prevalence.csv");
    if (!res.ok) return [];
    const text = await res.text();
    return parseCSV(text);
  } catch {
    return [];
  }
}

export async function fetchPredictions(): Promise<any[]> {
  try {
    const res = await fetch("/data/predictions.csv");
    if (!res.ok) return [];
    const text = await res.text();
    return parseCSV(text);
  } catch {
    return [];
  }
}

