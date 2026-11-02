"use client";

import React from "react";
import { KolkataMap } from "../map/KolkataMap";
import { DiurnalCycleChart } from "../charts/DiurnalCycleChart";
import { StationFilter } from "../layout/StationFilter";
import { Activity, Satellite, Flame, Wind } from "lucide-react";

interface OverviewViewProps {
  predictions: any[];
}

export const OverviewView: React.FC<OverviewViewProps> = ({ predictions }) => {
  // Aggregate top-line metrics from actual data
  const totalRows = predictions.length;
  const pmValues = predictions.map((p) => p.y ?? p.pred).filter((v): v is number => typeof v === "number");
  const meanPM = pmValues.length ? pmValues.reduce((a, b) => a + b, 0) / pmValues.length : null;

  // Sorted for 95th percentile
  const sorted = [...pmValues].sort((a, b) => a - b);
  const p95 = sorted.length ? sorted[Math.floor(sorted.length * 0.95)] : null;

  // AOD coverage
  const validAod = predictions.filter((p) => p.aod_missing === 0).length;
  const aodCoverage = predictions.length ? Math.round((validAod / predictions.length) * 100) : null;

  if (!predictions.length) {
    return (
      <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
        No prediction artifacts loaded. Run <code className="text-accent">python -m pm25.cli train</code> and copy
        artifacts to <code className="text-accent">frontend/public/data/</code>.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Metric Cards Banner */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-semibold uppercase tracking-wider">Total Samples</span>
            <Activity className="h-4 w-4 text-blue-400" />
          </div>
          <div className="mt-2 text-2xl font-black text-white">{totalRows.toLocaleString()}</div>
          <div className="text-xs text-muted-foreground mt-1">Verified hourly records</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-semibold uppercase tracking-wider">Mean PM2.5</span>
            <Wind className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-2xl font-black text-white">{meanPM != null ? meanPM.toFixed(1) : "—"} <span className="text-sm font-normal text-muted-foreground">µg/m³</span></div>
          <div className="text-xs text-muted-foreground mt-1">Across monitored stations</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-semibold uppercase tracking-wider">95th Percentile</span>
            <Flame className="h-4 w-4 text-orange-400" />
          </div>
          <div className="mt-2 text-2xl font-black text-white">{p95 != null ? p95.toFixed(1) : "—"} <span className="text-sm font-normal text-muted-foreground">µg/m³</span></div>
          <div className="text-xs text-orange-400 mt-1 font-medium">Severe episodic threshold</div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center justify-between text-muted-foreground">
            <span className="text-xs font-semibold uppercase tracking-wider">Satellite AOD</span>
            <Satellite className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 text-2xl font-black text-white">{aodCoverage != null ? `${aodCoverage}%` : "—"}</div>
          <div className="text-xs text-muted-foreground mt-1">Clear-sky MAIAC retrieval</div>
        </div>
      </div>

      {/* Station Multi-Select Filter Bar */}
      <StationFilter />

      {/* Spatial GIS Map & Temporal Diurnal Side-by-Side */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <KolkataMap />
        </div>
        <div className="lg:col-span-5">
          <DiurnalCycleChart data={predictions.slice(-1000)} />
        </div>
      </div>
    </div>
  );
};

