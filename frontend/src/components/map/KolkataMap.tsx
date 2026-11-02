"use client";

import React, { useState } from "react";
import { KOLKATA_STATIONS, Station, DATASET_STATION_KEYS } from "@/lib/constants/stations";
import { getAQICategory } from "@/lib/constants/aqi";
import { useUIStore } from "@/lib/store/useUIStore";
import { Wind, Layers, MapPin } from "lucide-react";

interface StationMapProps {
  latestValues?: Record<string, number>;
  onSelectStation?: (key: string) => void;
}

// Kolkata bounding box for the SVG fallback projection
const BOUNDS = { minLat: 22.47, maxLat: 22.61, minLon: 88.31, maxLon: 88.44 };
const SVG_W = 640, SVG_H = 480;

function project(lat: number, lon: number) {
  return {
    x: ((lon - BOUNDS.minLon) / (BOUNDS.maxLon - BOUNDS.minLon)) * (SVG_W - 80) + 40,
    y: ((BOUNDS.maxLat - lat) / (BOUNDS.maxLat - BOUNDS.minLat)) * (SVG_H - 80) + 40,
  };
}

/**
 * Kolkata CAAQMS station map.
 *
 * Uses an SVG-based rendering approach for reliability across all browsers
 * and environments (no WebGL requirement). The map projects station
 * coordinates onto a dark-themed canvas with the Hooghly River corridor,
 * AQI-colored station markers, and interactive toggles.
 *
 * MapLibre GL + Deck.gl integration path: when geospatial layers (AOD
 * heatmaps, wind particles, fire trajectories) move from placeholder to
 * real data, swap this component's rendering to a MapLibre GL canvas
 * using the already-installed `maplibre-gl` package. The station data
 * and interaction logic remain identical.
 */
export const KolkataMap: React.FC<StationMapProps> = ({ latestValues = {} }) => {
  const { selectedStations, toggleStation, setSelectedStationForDetail, mapLayers, toggleMapLayer } =
    useUIStore();
  const [hoveredStation, setHoveredStation] = useState<Station | null>(null);

  const riverCoords = [[22.61, 88.36], [22.58, 88.35], [22.55, 88.33], [22.52, 88.32], [22.47, 88.31]];
  const riverPath = riverCoords
    .map((c, i) => {
      const p = project(c[0], c[1]);
      return `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`;
    })
    .join(" ");

  return (
    <div className="relative rounded-xl border border-border bg-card overflow-hidden shadow-lg">
      {/* Map Control Bar */}
      <div className="absolute top-3 left-3 z-10 flex items-center gap-2 rounded-lg bg-card/90 px-3 py-1.5 backdrop-blur border border-border shadow-sm text-xs">
        <MapPin className="h-4 w-4 text-accent" />
        <span className="font-semibold text-white">Greater Kolkata CAAQMS Network</span>
      </div>

      <div className="absolute top-3 right-3 z-10 flex items-center gap-1.5 rounded-lg bg-card/90 p-1 backdrop-blur border border-border shadow-sm text-xs">
        <button
          onClick={() => toggleMapLayer("windParticles")}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
            mapLayers.windParticles ? "bg-cool/30 text-teal-300 border border-cool/50" : "text-muted-foreground hover:text-white"
          }`}
          title="Toggle ERA5 Wind Streamlines"
        >
          <Wind className="h-3.5 w-3.5" />
          <span>Wind</span>
        </button>
        <button
          onClick={() => toggleMapLayer("aodHeatmap")}
          className={`flex items-center gap-1 px-2.5 py-1 rounded transition-colors ${
            mapLayers.aodHeatmap ? "bg-accent/30 text-orange-300 border border-accent/50" : "text-muted-foreground hover:text-white"
          }`}
          title="Toggle Satellite MAIAC AOD Optical Depth"
        >
          <Layers className="h-3.5 w-3.5" />
          <span>AOD</span>
        </button>
      </div>

      {/* SVG GIS Canvas */}
      <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="w-full h-[440px] bg-[#0c1424] select-none">
        <defs>
          <pattern id="grid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#1e293b" strokeWidth="0.5" />
          </pattern>
          <radialGradient id="stationGlow">
            <stop offset="0%" stopColor="#c2410c" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#c2410c" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="aodGradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f97316" stopOpacity={mapLayers.aodHeatmap ? "0.15" : "0"} />
            <stop offset="50%" stopColor="#ef4444" stopOpacity={mapLayers.aodHeatmap ? "0.22" : "0"} />
            <stop offset="100%" stopColor="#991b1b" stopOpacity={mapLayers.aodHeatmap ? "0.10" : "0"} />
          </linearGradient>
        </defs>

        {/* Base Grid */}
        <rect width={SVG_W} height={SVG_H} fill="url(#grid)" />

        {/* Atmospheric AOD Layer Simulation */}
        <rect width={SVG_W} height={SVG_H} fill="url(#aodGradient)" />

        {/* Hooghly River Corridor */}
        <path d={riverPath} fill="none" stroke="#0284c7" strokeWidth="14" strokeLinecap="round" strokeOpacity="0.3" />
        <path d={riverPath} fill="none" stroke="#38bdf8" strokeWidth="3" strokeLinecap="round" strokeOpacity="0.6" />
        <text x="75" y="440" fill="#38bdf8" fontSize="10" opacity="0.6" fontStyle="italic">Hooghly River</text>

        {/* Animated Wind Streamlines */}
        {mapLayers.windParticles && (
          <g opacity="0.4">
            {[80, 160, 240, 320, 400].map((y, idx) => (
              <path
                key={idx}
                d={`M 60 ${y} Q 200 ${y - 30} 350 ${y} T 580 ${y + 20}`}
                fill="none"
                stroke="#14b8a6"
                strokeWidth="1.2"
                strokeDasharray="6 8"
                className="animate-pulse"
              />
            ))}
          </g>
        )}

        {/* Station Markers */}
        {DATASET_STATION_KEYS.map((key) => {
          const st = KOLKATA_STATIONS[key];
          const { x, y } = project(st.lat, st.lon);
          const isSelected = selectedStations.includes(key);
          const currentPM = latestValues[key] ?? null;
          const aqi = currentPM != null ? getAQICategory(currentPM) : null;
          const color = aqi?.color ?? "#64748b";

          return (
            <g
              key={key}
              className="cursor-pointer transition-transform hover:scale-110"
              onClick={() => { toggleStation(key); setSelectedStationForDetail(key); }}
              onMouseEnter={() => setHoveredStation(st)}
              onMouseLeave={() => setHoveredStation(null)}
            >
              {isSelected && (
                <circle cx={x} cy={y} r="18" fill={color} fillOpacity="0.25" className="animate-ping" />
              )}
              <circle cx={x} cy={y} r="10" fill="#0f172a" stroke={color} strokeWidth={isSelected ? "3" : "1.5"} />
              <circle cx={x} cy={y} r="5" fill={color} />
              <text x={x} y={y - 14} textAnchor="middle" fill={isSelected ? "#ffffff" : "#94a3b8"} fontSize="11" fontWeight={isSelected ? "700" : "500"} className="drop-shadow-md">
                {st.name}
              </text>
              {currentPM != null && (
                <>
                  <rect x={x - 22} y={y + 12} width="44" height="16" rx="4" fill={color} fillOpacity="0.9" />
                  <text x={x} y={y + 24} textAnchor="middle" fill={aqi?.textColor ?? "#fff"} fontSize="10" fontWeight="700">
                    {currentPM.toFixed(0)} µg
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>

      {/* Map Legend Footer */}
      <div className="flex flex-wrap items-center justify-between border-t border-border bg-card/95 px-4 py-2.5 text-xs text-muted-foreground">
        <div className="flex items-center gap-3">
          <span className="font-medium text-white">AQI Scale:</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-[#10b981]" /> Good (0-30)</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-[#84cc16]" /> Satisfactory</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-[#eab308]" /> Moderate</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-[#f97316]" /> Poor</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-[#ef4444]" /> Very Poor (120+)</span>
        </div>
        <span className="text-[11px] text-gray-400">Click marker to toggle station details</span>
      </div>
    </div>
  );
};
