"use client";

import React from "react";
import {
  MapPin,
  TrendingUp,
  Sparkles,
  ShieldCheck,
  Satellite,
  Sliders,
} from "lucide-react";

export type TabId =
  | "overview"
  | "forecast"
  | "attribution"
  | "proxies"
  | "robustness"
  | "simulator";

interface NavigationTabsProps {
  activeTab: TabId;
  onChangeTab: (tab: TabId) => void;
}

export const NavigationTabs: React.FC<NavigationTabsProps> = ({
  activeTab,
  onChangeTab,
}) => {
  const tabs: { id: TabId; label: string; icon: React.ElementType }[] = [
    { id: "overview", label: "Overview & Map", icon: MapPin },
    { id: "forecast", label: "Forecasting & Benchmarks", icon: TrendingUp },
    { id: "attribution", label: "Causal Attribution", icon: Sparkles },
    { id: "proxies", label: "Source Proxies", icon: ShieldCheck },
    { id: "robustness", label: "Robustness & Satellite", icon: Satellite },
    { id: "simulator", label: "What-If Simulator", icon: Sliders },
  ];

  return (
    <div className="flex border-b border-border overflow-x-auto bg-card/40 px-6 backdrop-blur">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onChangeTab(tab.id)}
            className={`flex items-center gap-2 border-b-2 px-4 py-3 text-xs font-semibold whitespace-nowrap transition-all ${
              isActive
                ? "border-accent text-accent bg-accent/5"
                : "border-transparent text-muted-foreground hover:text-white hover:border-muted-foreground/40"
            }`}
          >
            <Icon className="h-4 w-4" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
};

