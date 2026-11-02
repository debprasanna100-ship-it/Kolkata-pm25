"use client";

import React from "react";
import { ShapImportanceChart } from "../charts/ShapImportanceChart";
import { SeasonalHeatmap } from "../charts/SeasonalHeatmap";
import { Info, Sparkles, CheckCircle2 } from "lucide-react";

interface AttributionViewProps {
  importance: any[];
  seasonalImportance: any[];
  summary: Record<string, any> | null;
}

export const AttributionView: React.FC<AttributionViewProps> = ({
  importance,
  seasonalImportance,
  summary,
}) => {
  const method = summary?.method || "TreeSHAP / Permutation (Lag-free)";

  return (
    <div className="space-y-6">
      {/* Attribution Principle Banner */}
      <div className="rounded-xl border border-accent/30 bg-accent/10 p-4">
        <div className="flex items-start gap-3">
          <Sparkles className="h-5 w-5 text-accent mt-0.5" />
          <div>
            <h2 className="text-sm font-bold text-white">
              Causal Attribution Model — Autoregressive PM2.5 Lags Stripped
            </h2>
            <p className="mt-1 text-xs text-orange-200/90 leading-relaxed">
              In operational nowcasting, PM2.5(t-1) naturally absorbs 80%+ of the variance due to persistence. If included in SHAP, lag-1 masks all underlying physics. Our attribution model explicitly trains on the identical feature matrix <strong>minus AR lags</strong>, revealing genuine contributions from satellite AOD, boundary layer inversion (<code className="text-white">pbl_inv</code>), ventilation coefficients, and upwind fire transport.
            </p>
            <div className="mt-2 text-[11px] font-mono text-orange-300">
              Active Method: {method} · Evaluated across 4 meteorological seasons
            </div>
          </div>
        </div>
      </div>

      {/* Side-by-Side: Global Importance & Seasonal Driver Shift */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ShapImportanceChart importanceData={importance} />
        <SeasonalHeatmap seasonalData={seasonalImportance} />
      </div>

      {/* Seasonal Story Breakdown */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-white">
            <span>Winter (Nov–Feb)</span>
            <span className="rounded bg-red-500/20 px-1.5 py-0.5 text-[10px] text-red-400">Peak Crisis</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            Severe ground-level inversions (shallow PBL) and high humidity compress particulate matter, compounding post-harvest regional biomass plumes.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-white">
            <span>Pre-Monsoon (Mar–May)</span>
            <span className="rounded bg-yellow-500/20 px-1.5 py-0.5 text-[10px] text-yellow-400">Dust & Convection</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            High ventilation and strong westerly winds disperse local combustion but entrain regional mineral dust, shifting the PM10/PM2.5 ratio above 2.6.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-white">
            <span>Monsoon (Jun–Sep)</span>
            <span className="rounded bg-emerald-500/20 px-1.5 py-0.5 text-[10px] text-emerald-400">Cleanest Baseline</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            Wet scavenging and rapid maritime ventilation flush the urban corridor, bringing PM2.5 to annual lows (typically under 35 µg/m³).
          </p>
        </div>

        <div className="rounded-xl border border-border bg-card p-4 space-y-2">
          <div className="flex items-center justify-between text-xs font-bold text-white">
            <span>Post-Monsoon (Oct)</span>
            <span className="rounded bg-orange-500/20 px-1.5 py-0.5 text-[10px] text-orange-400">Plume Inception</span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            Winds turn north-westerly; NASA FIRMS detects upwind crop residue burning across the Gangetic plain, triggering Kolkata's first winter smog spike.
          </p>
        </div>
      </div>
    </div>
  );
};
