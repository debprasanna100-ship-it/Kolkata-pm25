"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { CloudOff, Satellite, ShieldAlert, Droplets } from "lucide-react";

interface RobustnessViewProps {
  predictions: any[];
}

export const RobustnessView: React.FC<RobustnessViewProps> = ({ predictions }) => {
  // Compute AOD available vs missing statistics from real predictions
  const { availableStats, missingStats, hasData } = useMemo(() => {
    const available = predictions.filter((p) => p.aod_missing === 0);
    const missing = predictions.filter((p) => p.aod_missing === 1);

    const calc = (rows: any[]) => {
      if (rows.length === 0) return { n: 0, rmse: 0, mae: 0, r2: 0, meanWidth: 0 };
      const errs = rows.map((r) => r.pred - r.y);
      const rmse = Math.sqrt(errs.reduce((a, b) => a + b * b, 0) / rows.length);
      const mae = errs.reduce((a, b) => a + Math.abs(b), 0) / rows.length;

      const yMean = rows.reduce((a, b) => a + b.y, 0) / rows.length;
      const ssTot = rows.reduce((a, b) => a + Math.pow(b.y - yMean, 2), 0);
      const ssRes = errs.reduce((a, b) => a + b * b, 0);
      const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;

      const widths = rows
        .filter((r) => r.q90 !== undefined && r.q10 !== undefined && r.q90 !== null && r.q10 !== null)
        .map((r) => r.q90 - r.q10);
      const meanWidth = widths.length ? widths.reduce((a, b) => a + b, 0) / widths.length : 0;

      return { n: rows.length, rmse, mae, r2, meanWidth };
    };

    return {
      availableStats: calc(available),
      missingStats: calc(missing),
      hasData: predictions.length > 0,
    };
  }, [predictions]);

  // Compute actual humidity bins from prediction data
  const { humidityBins, widthAvailable, widthMissing, hasHumidityData } = useMemo(() => {
    if (!predictions.length) return { humidityBins: [], widthAvailable: [], widthMissing: [], hasHumidityData: false };

    const withRh = predictions.filter((p) => typeof p.rh === "number" && p.q10 != null && p.q90 != null);
    if (withRh.length < 50) return { humidityBins: [], widthAvailable: [], widthMissing: [], hasHumidityData: false };

    const binEdges = [30, 40, 50, 60, 70, 80, 90, 100];
    const labels: string[] = [];
    const availWidths: number[] = [];
    const missWidths: number[] = [];

    for (let i = 0; i < binEdges.length - 1; i++) {
      const lo = binEdges[i], hi = binEdges[i + 1];
      labels.push(`${lo}-${hi}%`);
      const inBin = withRh.filter((p) => p.rh >= lo && p.rh < hi);
      const avail = inBin.filter((p) => p.aod_missing === 0);
      const miss = inBin.filter((p) => p.aod_missing === 1);
      availWidths.push(avail.length ? avail.reduce((a, p) => a + (p.q90 - p.q10), 0) / avail.length : 0);
      missWidths.push(miss.length ? miss.reduce((a, p) => a + (p.q90 - p.q10), 0) / miss.length : 0);
    }

    return { humidityBins: labels, widthAvailable: availWidths, widthMissing: missWidths, hasHumidityData: true };
  }, [predictions]);

  if (!hasData) {
    return (
      <div className="rounded-xl border border-border bg-card p-10 text-center text-sm text-muted-foreground">
        No prediction data available. Run <code className="text-accent">python -m pm25.cli train</code> to generate artifacts.
      </div>
    );
  }

  const option = {
    title: {
      text: "Uncertainty Interval Width vs Relative Humidity",
      subtext: "Prediction intervals widen as humidity increases — the model quantifies its own reduced certainty",
      left: "left",
      textStyle: { color: "#f8fafc", fontSize: 13, fontWeight: "bold" },
      subtextStyle: { color: "#94a3b8", fontSize: 11 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0f172a",
      borderColor: "#334155",
      textStyle: { color: "#e2e8f0" },
    },
    legend: {
      data: ["AOD Available (Clear Sky)", "AOD Missing (Cloudy)"],
      top: 25,
      right: 10,
      textStyle: { color: "#94a3b8" },
    },
    grid: {
      left: "4%",
      right: "4%",
      bottom: "10%",
      top: "22%",
      containLabel: true,
    },
    xAxis: {
      type: "category",
      data: humidityBins,
      name: "Relative Humidity",
      axisLine: { lineStyle: { color: "#334155" } },
      axisLabel: { color: "#cbd5e1" },
    },
    yAxis: {
      type: "value",
      name: "80% Interval Width (µg/m³)",
      splitLine: { lineStyle: { color: "#1e293b" } },
      axisLabel: { color: "#cbd5e1" },
    },
    series: [
      {
        name: "AOD Available (Clear Sky)",
        type: "line",
        smooth: true,
        data: widthAvailable,
        itemStyle: { color: "#06b6d4" },
        lineStyle: { width: 2.5 },
      },
      {
        name: "AOD Missing (Cloudy)",
        type: "line",
        smooth: true,
        data: widthMissing,
        itemStyle: { color: "#f97316" },
        lineStyle: { width: 2.5, type: "dashed" },
      },
    ],
  };

  return (
    <div className="space-y-6">
      {/* Satellite Blindness Context Card */}
      <div className="rounded-xl border border-border bg-card p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <Satellite className="h-5 w-5 text-accent" />
          <h2 className="text-base font-bold text-white">
            Satellite Blindness Deconstruction (AOD Missingness)
          </h2>
        </div>
        <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
          Satellite MAIAC AOD cannot penetrate cloud cover. Cloudy days are non-random—they correlate with boundary layer moisture and acute winter smog episodes. Rather than disguising missing satellite retrievals through naive imputation, the pipeline preserves an explicit <code className="text-accent">aod_missing</code> flag and quantifies performance degradation honestly.
        </p>

        {/* Comparison Grid */}
        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-muted/40 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-teal-400 flex items-center gap-1.5">
                <Satellite className="h-4 w-4" /> Clear-Sky Retrievals
              </span>
              <span className="rounded bg-teal-500/20 px-2 py-0.5 text-xs font-mono font-bold text-teal-300">
                AOD Available
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">RMSE</div>
                <div className="text-lg font-bold text-white font-mono">{availableStats.rmse.toFixed(2)}</div>
              </div>
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">MAE</div>
                <div className="text-lg font-bold text-white font-mono">{availableStats.mae.toFixed(2)}</div>
              </div>
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">R²</div>
                <div className="text-lg font-bold text-emerald-400 font-mono">{availableStats.r2.toFixed(3)}</div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-orange-500/30 bg-orange-500/5 p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-orange-400 flex items-center gap-1.5">
                <CloudOff className="h-4 w-4" /> Cloud-Obscured Hours
              </span>
              <span className="rounded bg-orange-500/20 px-2 py-0.5 text-xs font-mono font-bold text-orange-300">
                AOD Missing
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-3 text-center">
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">RMSE</div>
                <div className="text-lg font-bold text-white font-mono">{missingStats.rmse.toFixed(2)}</div>
              </div>
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">MAE</div>
                <div className="text-lg font-bold text-white font-mono">{missingStats.mae.toFixed(2)}</div>
              </div>
              <div className="rounded bg-card p-2">
                <div className="text-[11px] text-muted-foreground">R²</div>
                <div className="text-lg font-bold text-yellow-400 font-mono">{missingStats.r2.toFixed(3)}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Uncertainty Interval vs Humidity Chart */}
      {hasHumidityData ? (
        <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
          <ReactECharts
            option={option}
            style={{ height: "360px", width: "100%" }}
            notMerge={true}
            lazyUpdate={true}
          />
        </div>
      ) : (
        <div className="rounded-xl border border-border bg-card p-6 text-center text-xs text-muted-foreground">
          Not enough rows with RH + interval data to compute humidity-binned widths.
        </div>
      )}
    </div>
  );
};

