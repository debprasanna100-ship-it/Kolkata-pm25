"use client";

import React, { useState } from "react";
import { NavigationTabs, TabId } from "@/components/layout/NavigationTabs";
import { OverviewView } from "@/components/views/OverviewView";
import { ForecastView } from "@/components/views/ForecastView";
import { AttributionView } from "@/components/views/AttributionView";
import { ProxiesView } from "@/components/views/ProxiesView";
import { RobustnessView } from "@/components/views/RobustnessView";
import { SimulatorView } from "@/components/views/SimulatorView";
import { StationDrawer } from "@/components/station/StationDrawer";
import {
  useMetrics,
  useAttributionSummary,
  useProxyAgreement,
  useSeasonalImportance,
  useGlobalImportance,
  useProxyPrevalence,
  usePredictions,
} from "@/lib/queries";
import { Loader2 } from "lucide-react";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  // TanStack Query hooks replace the manual useEffect/useState pattern.
  // `?? null` normalizes undefined (query not yet resolved) to match the
  // views' prop types, which accept null for "artifact missing".
  const { data: metricsData, isLoading: mLoading } = useMetrics();
  const { data: attributionData, isLoading: aLoading } = useAttributionSummary();
  const { data: agreementData, isLoading: paLoading } = useProxyAgreement();
  const { data: seasonalData, isLoading: siLoading } = useSeasonalImportance();
  const { data: globalImpData, isLoading: giLoading } = useGlobalImportance();
  const { data: prevalenceData, isLoading: ppLoading } = useProxyPrevalence();
  const { data: predictionsData, isLoading: predLoading } = usePredictions();

  const metrics = metricsData ?? null;
  const attributionSummary = attributionData ?? null;
  const proxyAgreement = agreementData ?? [];
  const seasonalImportance = seasonalData ?? [];
  const globalImportance = globalImpData ?? [];
  const proxyPrevalence = prevalenceData ?? [];
  const predictions = predictionsData ?? [];

  const loading = mLoading || aLoading || paLoading || siLoading || giLoading || ppLoading || predLoading;

  return (
    <div className="min-h-[calc(100vh-60px)] flex flex-col">
      <NavigationTabs activeTab={activeTab} onChangeTab={setActiveTab} />

      <div className="flex-1 p-6 max-w-7xl mx-auto w-full">
        {loading ? (
          <div className="flex h-64 flex-col items-center justify-center gap-3 text-muted-foreground">
            <Loader2 className="h-8 w-8 animate-spin text-accent" />
            <span className="text-xs font-medium">Loading atmospheric artifacts...</span>
          </div>
        ) : (
          <>
            {activeTab === "overview" && <OverviewView predictions={predictions} />}
            {activeTab === "forecast" && (
              <ForecastView metrics={metrics} predictions={predictions} />
            )}
            {activeTab === "attribution" && (
              <AttributionView
                importance={globalImportance}
                seasonalImportance={seasonalImportance}
                summary={attributionSummary}
              />
            )}
            {activeTab === "proxies" && (
              <ProxiesView agreement={proxyAgreement} prevalence={proxyPrevalence} />
            )}
            {activeTab === "robustness" && <RobustnessView predictions={predictions} />}
            {activeTab === "simulator" && <SimulatorView />}
          </>
        )}
      </div>

      {/* Station detail sliding inspector */}
      <StationDrawer />
    </div>
  );
}
