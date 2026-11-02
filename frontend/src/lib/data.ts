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

export async function fetchMetrics(): Promise<Record<string, any> | null> {
  try {
    const res = await fetch("/data/metrics.json");
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchAttributionSummary(): Promise<Record<string, any> | null> {
  try {
    const res = await fetch("/data/attribution_summary.json");
    if (!res.ok) return null;
    return await res.json();
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

