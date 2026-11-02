import { create } from "zustand";
import { ForecastHorizon, Season } from "../types/atmospheric";
import { DATASET_STATION_KEYS } from "../constants/stations";

interface UIState {
  selectedStations: string[];
  activeHorizon: ForecastHorizon;
  activeSeason: Season | "all";
  timeWindow: [string | null, string | null];
  selectedStationForDetail: string | null;
  mapLayers: {
    stations: boolean;
    windParticles: boolean;
    aodHeatmap: boolean;
    fireCones: boolean;
  };
  setSelectedStations: (stations: string[]) => void;
  toggleStation: (station: string) => void;
  setActiveHorizon: (horizon: ForecastHorizon) => void;
  setActiveSeason: (season: Season | "all") => void;
  setTimeWindow: (window: [string | null, string | null]) => void;
  setSelectedStationForDetail: (station: string | null) => void;
  toggleMapLayer: (layer: keyof UIState["mapLayers"]) => void;
}

export const useUIStore = create<UIState>((set) => ({
  selectedStations: DATASET_STATION_KEYS,
  activeHorizon: 1,
  activeSeason: "all",
  timeWindow: [null, null],
  selectedStationForDetail: null,
  mapLayers: {
    stations: true,
    windParticles: true,
    aodHeatmap: true,
    fireCones: false,
  },
  setSelectedStations: (stations) => set({ selectedStations: stations }),
  toggleStation: (station) =>
    set((state) => ({
      selectedStations: state.selectedStations.includes(station)
        ? state.selectedStations.filter((s) => s !== station)
        : [...state.selectedStations, station],
    })),
  setActiveHorizon: (horizon) => set({ activeHorizon: horizon }),
  setActiveSeason: (season) => set({ activeSeason: season }),
  setTimeWindow: (window) => set({ timeWindow: window }),
  setSelectedStationForDetail: (station) => set({ selectedStationForDetail: station }),
  toggleMapLayer: (layer) =>
    set((state) => ({
      mapLayers: {
        ...state.mapLayers,
        [layer]: !state.mapLayers[layer],
      },
    })),
}));

