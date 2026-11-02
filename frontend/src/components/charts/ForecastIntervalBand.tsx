"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";

interface ForecastIntervalBandProps {
  data: Array<{
    time: string;
    y: number;
    pred: number;
    q10?: number;
    q90?: number;
    station: string;
  }>;
  stationName?: string;
  horizonHours?: number;
}

export const ForecastIntervalBand: React.FC<ForecastIntervalBandProps> = ({
  data,
  stationName = "All Selected Stations",
  horizonHours = 1,
}) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) return {};

    // Sort by time ascending
    const sorted = [...data].sort(
      (a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()
    );

    // Limit slice to the latest 300 points for crisp interactive performance
    const slice = sorted.slice(-300);

    const times = slice.map((d) => d.time.replace("T", " ").slice(0, 16));
    const observed = slice.map((d) => (d.y !== undefined ? Number(d.y.toFixed(1)) : null));
    const predicted = slice.map((d) => (d.pred !== undefined ? Number(d.pred.toFixed(1)) : null));
    const q10 = slice.map((d) => (d.q10 !== undefined ? Number(d.q10.toFixed(1)) : null));
    const q90Diff = slice.map((d) =>
      d.q90 !== undefined && d.q10 !== undefined
        ? Number((d.q90 - d.q10).toFixed(1))
        : null
    );

    return {
      title: {
        text: `Nowcast & Forecast Trace (+${horizonHours}h) with 80% Prediction Interval`,
        subtext: `${stationName} — Shaded band indicates [q10, q90] quantile spread`,
        left: "left",
        textStyle: { color: "#f8fafc", fontSize: 14, fontWeight: "bold" },
        subtextStyle: { color: "#94a3b8", fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        backgroundColor: "#0f172a",
        borderColor: "#334155",
        textStyle: { color: "#e2e8f0" },
        axisPointer: { type: "cross", label: { backgroundColor: "#334155" } },
      },
      legend: {
        data: ["Observed PM2.5", "Predicted PM2.5", "80% Interval Band"],
        top: 25,
        right: 10,
        textStyle: { color: "#94a3b8" },
      },
      grid: {
        left: "4%",
        right: "4%",
        bottom: "16%",
        top: "22%",
        containLabel: true,
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: times,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: "PM2.5 (µg/m³)",
        nameTextStyle: { color: "#94a3b8" },
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#94a3b8" },
      },
      dataZoom: [
        {
          type: "slider",
          bottom: "2%",
          height: 20,
          borderColor: "#334155",
          fillerColor: "rgba(194, 65, 12, 0.2)",
          textStyle: { color: "#94a3b8" },
        },
        { type: "inside" },
      ],
      series: [
        // Base of the interval (q10) - transparent line to stack on top of
        {
          name: "q10_base",
          type: "line",
          data: q10,
          lineStyle: { opacity: 0 },
          stack: "confidence-band",
          symbol: "none",
        },
        // The width from q10 to q90 - filled area
        {
          name: "80% Interval Band",
          type: "line",
          data: q90Diff,
          lineStyle: { opacity: 0 },
          areaStyle: { color: "rgba(194, 65, 12, 0.22)" },
          stack: "confidence-band",
          symbol: "none",
        },
        // Observed
        {
          name: "Observed PM2.5",
          type: "line",
          data: observed,
          smooth: true,
          itemStyle: { color: "#ffffff" },
          lineStyle: { width: 1.8, color: "#ffffff" },
          showSymbol: false,
        },
        // Predicted
        {
          name: "Predicted PM2.5",
          type: "line",
          data: predicted,
          smooth: true,
          itemStyle: { color: "#ea580c" },
          lineStyle: { width: 2.2, color: "#ea580c" },
          showSymbol: false,
        },
      ],
    };
  }, [data, stationName, horizonHours]);

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <ReactECharts
        option={option}
        style={{ height: "380px", width: "100%" }}
        notMerge={true}
        lazyUpdate={true}
      />
    </div>
  );
};

