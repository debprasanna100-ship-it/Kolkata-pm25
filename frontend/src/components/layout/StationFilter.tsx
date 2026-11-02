"use client";

import React from "react";
import { KOLKATA_STATIONS, STATION_KEYS } from "@/lib/constants/stations";
import { useUIStore } from "@/lib/store/useUIStore";
import { MapPin, Check } from "lucide-react";

export const StationFilter: React.FC = () => {
  const { selectedStations, toggleStation, setSelectedStations, setSelectedStationForDetail } =
    useUIStore();

  const allSelected = selectedStations.length === STATION_KEYS.length;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground mr-1">
          <MapPin className="h-3.5 w-3.5 text-accent" /> Filter Stations:
        </span>
        {STATION_KEYS.map((key) => {
          const station = KOLKATA_STATIONS[key];
          const isSelected = selectedStations.includes(key);
          return (
            <button
              key={key}
              onClick={() => toggleStation(key)}
              onDoubleClick={() => setSelectedStationForDetail(key)}
              title={`${station.name} (${station.distRoadKm}km from highway) - Double click for details`}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-all ${
                isSelected
                  ? "bg-muted text-white border border-accent/40 shadow-sm"
                  : "bg-background/50 text-muted-foreground border border-border/50 hover:bg-muted/40"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  isSelected ? "bg-accent" : "bg-gray-500 opacity-50"
                }`}
              />
              <span>{station.name}</span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => setSelectedStations(allSelected ? [] : STATION_KEYS)}
          className="text-xs text-muted-foreground hover:text-white underline underline-offset-4"
        >
          {allSelected ? "Clear all" : "Select all"}
        </button>
      </div>
    </div>
  );
};

