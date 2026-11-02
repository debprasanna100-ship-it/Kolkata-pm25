"use client";

import React from "react";
import { CloudFog, Clock, ShieldCheck, Activity } from "lucide-react";
import { useUIStore } from "@/lib/store/useUIStore";
import { ForecastHorizon } from "@/lib/types/atmospheric";

export const Header: React.FC = () => {
  const { activeHorizon, setActiveHorizon, selectedStations } = useUIStore();

  const horizons: { label: string; value: ForecastHorizon; sub: string }[] = [
    { label: "+0 h", value: 0, sub: "Nowcast" },
    { label: "+1 h", value: 1, sub: "Short-lead" },
    { label: "+6 h", value: 6, sub: "Mid-lead" },
    { label: "+24 h", value: 24, sub: "Day-ahead" },
  ];

  return (
    <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-4 border-b border-border bg-card/95 px-6 py-3 backdrop-blur shadow-sm">
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent/20 text-accent">
          <CloudFog className="h-6 w-6" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight text-white">Kolkata PM2.5</h1>
            <span className="rounded bg-accent/20 px-2 py-0.5 text-xs font-semibold uppercase tracking-wider text-accent border border-accent/30">
              Demo Mode
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            Hourly Estimation, 80% Uncertainty & Causal Source Attribution
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4">
        {/* Horizon selector */}
        <div className="flex items-center rounded-lg bg-muted p-1">
          <span className="flex items-center gap-1.5 px-2 text-xs font-medium text-muted-foreground">
            <Clock className="h-3.5 w-3.5" /> Horizon:
          </span>
          {horizons.map((h) => {
            const isActive = activeHorizon === h.value;
            return (
              <button
                key={h.value}
                onClick={() => setActiveHorizon(h.value)}
                className={`flex items-center gap-1 rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                  isActive
                    ? "bg-accent text-white shadow"
                    : "text-muted-foreground hover:text-white"
                }`}
              >
                <span>{h.label}</span>
                <span className={`text-[10px] ${isActive ? "text-orange-200" : "text-gray-400"}`}>
                  ({h.sub})
                </span>
              </button>
            );
          })}
        </div>

        {/* Station counter */}
        <div className="hidden sm:flex items-center gap-2 rounded-lg bg-muted/60 px-3 py-1.5 text-xs text-muted-foreground border border-border">
          <Activity className="h-3.5 w-3.5 text-emerald-400" />
          <span>
            Stations: <strong className="text-white">{selectedStations.length} / 6</strong> active
          </span>
        </div>
      </div>
    </header>
  );
};

