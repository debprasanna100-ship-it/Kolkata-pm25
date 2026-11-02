"use client";

import React from "react";
import { CheckCircle2, XCircle, ShieldCheck, Flame, Car, Wind, Sparkles } from "lucide-react";
import { ProxyAgreementItem } from "@/lib/types/atmospheric";

interface ProxiesViewProps {
  agreement: ProxyAgreementItem[];
  prevalence: any[];
}

export const ProxiesView: React.FC<ProxiesViewProps> = ({ agreement }) => {
  const supportedCount = agreement.filter((a) => a.supported).length;
  const totalCount = agreement.length || 20;

  const proxiesConfig = [
    {
      name: "Biomass Burning",
      icon: Flame,
      color: "#ea580c",
      heuristic: "Upwind FIRMS fire count in top 15% for that station",
      supportedSeasons: "Post-Monsoon (48% of hours)",
    },
    {
      name: "Road Traffic",
      icon: Car,
      color: "#eab308",
      heuristic: "Weekday rush hours (8-11h, 17-21h) + station road distance < 0.5km + elevated NO2",
      supportedSeasons: "Winter (28%), Pre-Monsoon (21%)",
    },
    {
      name: "Mineral Dust",
      icon: Wind,
      color: "#a855f7",
      heuristic: "PM10 / PM2.5 ratio ≥ 2.6 + Relative Humidity < 62% + Wind Speed ≥ 2.5 m/s",
      supportedSeasons: "Pre-Monsoon (15%)",
    },
    {
      name: "Secondary Aerosol",
      icon: Sparkles,
      color: "#06b6d4",
      heuristic: "High humidity (RH ≥ 70%) + photochemical O3 elevated + low wind speed",
      supportedSeasons: "Sporadic (< 5% of hours)",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Agreement Metric Headline */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-emerald-400" />
            <h2 className="text-base font-bold text-white">Dual-Method Agreement Validation</h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground leading-relaxed max-w-2xl">
            Two independent methods, built from different data sources, telling the same seasonal story: Do the model's top-5 SHAP drivers match the independent rule-based source proxies?
          </p>
        </div>
        <div className="rounded-xl border border-border bg-muted/60 px-5 py-3 text-center">
          <div className="text-2xl font-black text-emerald-400">
            {supportedCount} / {totalCount}
          </div>
          <div className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider">
            Supported Season-Proxy Pairs
          </div>
        </div>
      </div>

      {/* Proxy Definition Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {proxiesConfig.map((p, idx) => {
          const Icon = p.icon;
          return (
            <div key={idx} className="rounded-xl border border-border bg-card p-4 space-y-3">
              <div className="flex items-center gap-2">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${p.color}20`, color: p.color }}
                >
                  <Icon className="h-4 w-4" />
                </div>
                <h3 className="text-sm font-bold text-white">{p.name}</h3>
              </div>
              <div className="text-xs text-gray-300 leading-relaxed">
                <span className="font-semibold text-white">Rule Heuristic: </span>
                {p.heuristic}
              </div>
              <div className="rounded bg-muted/50 p-2 text-[11px] text-muted-foreground border border-border/50">
                <span className="font-medium text-gray-300">Peak Prevalence: </span>
                {p.supportedSeasons}
              </div>
            </div>
          );
        })}
      </div>

      {/* Agreement Matrix Table */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <h3 className="text-sm font-bold text-white mb-3">
          Season × Proxy Agreement Matrix
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/60 uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="py-2.5 px-3">Season</th>
                <th className="py-2.5 px-3">Source Proxy</th>
                <th className="py-2.5 px-3">Proxy Share of Hours</th>
                <th className="py-2.5 px-3">Expected Physical Drivers</th>
                <th className="py-2.5 px-3">Model Top Drivers</th>
                <th className="py-2.5 px-3">Agreement</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/50 text-gray-200">
              {agreement.length > 0 ? (
                agreement.map((row, idx) => (
                  <tr key={idx} className="hover:bg-muted/30">
                    <td className="py-2.5 px-3 font-medium capitalize text-white">{row.season}</td>
                    <td className="py-2.5 px-3 font-mono capitalize">{row.proxy}</td>
                    <td className="py-2.5 px-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                          <div
                            className="h-full bg-accent"
                            style={{ width: `${Math.min(100, (row.proxy_share ?? 0) * 100)}%` }}
                          />
                        </div>
                        <span className="font-mono text-[11px]">
                          {((row.proxy_share ?? 0) * 100).toFixed(0)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-gray-300">
                      {Array.isArray(row.expected_drivers)
                        ? row.expected_drivers.join(", ")
                        : String(row.expected_drivers || "—")}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-[11px] text-gray-300">
                      {Array.isArray(row.model_top_drivers)
                        ? row.model_top_drivers.join(", ")
                        : String(row.model_top_drivers || "—")}
                    </td>
                    <td className="py-2.5 px-3">
                      {row.supported ? (
                        <span className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] font-semibold text-emerald-400">
                          <CheckCircle2 className="h-3 w-3" /> Supported
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 rounded bg-gray-500/20 px-2 py-0.5 text-[11px] font-medium text-gray-400">
                          <XCircle className="h-3 w-3" /> Divergent
                        </span>
                      )}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-4 text-center text-muted-foreground">
                    No proxy agreement data loaded.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

