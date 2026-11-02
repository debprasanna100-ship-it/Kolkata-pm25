"use client";

import React from "react";
import { KOLKATA_STATIONS } from "@/lib/constants/stations";
import { getAQICategory } from "@/lib/constants/aqi";
import { useUIStore } from "@/lib/store/useUIStore";
import { X, MapPin, Navigation, Info, ShieldAlert } from "lucide-react";

interface StationDrawerProps {
  currentPM?: number;
}

export const StationDrawer: React.FC<StationDrawerProps> = ({ currentPM = 88.5 }) => {
  const { selectedStationForDetail, setSelectedStationForDetail } = useUIStore();

  if (!selectedStationForDetail) return null;

  const station = KOLKATA_STATIONS[selectedStationForDetail];
  if (!station) return null;

  const aqi = getAQICategory(currentPM);

  return (
    <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card p-6 shadow-2xl backdrop-blur transition-all">
      <div className="flex items-center justify-between border-b border-border pb-4">
        <div className="flex items-center gap-2">
          <MapPin className="h-5 w-5 text-accent" />
          <h2 className="text-lg font-bold text-white">{station.name}</h2>
        </div>
        <button
          onClick={() => setSelectedStationForDetail(null)}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-white"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      <div className="mt-6 space-y-6 overflow-y-auto">
        {/* Real-time AQI Banner */}
        <div
          className="rounded-xl p-4 text-white shadow-inner flex items-center justify-between"
          style={{ backgroundColor: aqi.color }}
        >
          <div>
            <div className="text-xs uppercase tracking-wider font-semibold opacity-90">
              Current PM2.5 Status
            </div>
            <div className="text-2xl font-black">{currentPM.toFixed(1)} µg/m³</div>
            <div className="text-xs font-medium mt-1">{aqi.name} — {aqi.advisory}</div>
          </div>
          <div className="rounded-full bg-black/20 p-3">
            <ShieldAlert className="h-6 w-6" />
          </div>
        </div>

        {/* Spatial & Physical Attributes */}
        <div className="rounded-xl border border-border bg-muted/40 p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Geographic Attributes
          </h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-xs text-muted-foreground">Latitude:</span>
              <div className="font-mono font-medium text-white">{station.lat.toFixed(4)}° N</div>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Longitude:</span>
              <div className="font-mono font-medium text-white">{station.lon.toFixed(4)}° E</div>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">Distance to Highway:</span>
              <div className="font-semibold text-accent">{station.distRoadKm} km</div>
            </div>
            <div>
              <span className="text-xs text-muted-foreground">OpenAQ Identifier:</span>
              <div className="font-mono text-xs text-gray-300">{station.openaqHint}</div>
            </div>
          </div>
        </div>

        {/* Context & Microclimate Notes */}
        <div className="rounded-xl border border-border bg-muted/40 p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            <Info className="h-4 w-4 text-cool" /> Station Context & Source Dynamics
          </div>
          <p className="text-sm text-gray-300 leading-relaxed">{station.notes}</p>
        </div>

        {/* Source Proxy Dynamics */}
        <div className="rounded-xl border border-border bg-muted/40 p-4 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Active Source Signatures
          </h3>
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
              <span className="text-muted-foreground">Traffic Vulnerability:</span>
              <span className="font-semibold text-white">
                {station.distRoadKm <= 0.4 ? "High (Corridor)" : "Moderate"}
              </span>
            </div>
            <div className="flex items-center justify-between border-b border-border/50 pb-1.5">
              <span className="text-muted-foreground">Regional Fire Exposure:</span>
              <span className="font-semibold text-orange-400">Upwind Indo-Gangetic Trajectory</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Topographic Inversion Risk:</span>
              <span className="font-semibold text-red-400">Severe in Winter (Nov–Feb)</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

