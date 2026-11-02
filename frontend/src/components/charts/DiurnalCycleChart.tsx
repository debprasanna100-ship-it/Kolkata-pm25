"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import { KOLKATA_STATIONS } from "@/lib/constants/stations";

interface DiurnalCycleProps {
  data: Array<{
    time: string;
    station: string;
    pm25?: number;
    pred?: number;
  }>;
}

export const DiurnalCycleChart: React.FC<DiurnalCycleProps> = ({ data }) => {
  const option = useMemo(() => {
    if (!data || data.length === 0) return {};

    // Group by station and hour (0-23)
    const stations = Array.from(new Set(data.map((d) => d.station)));
    const hours = Array.from({ length: 24 }, (_, i) => `${i}:00`);

    const series = stations.map((stKey, idx) => {
      const stationData = data.filter((d) => d.station === stKey);
      const hourMeans: number[] = [];

      for (let h = 0; h < 24; h++) {
        const matching = stationData.filter((d) => {
          const date = new Date(d.time);
          return date.getUTCHours() === h;
        });
        const vals = matching
          .map((m) => m.pm25 ?? m.pred)
          .filter((v): v is number => typeof v === "number");
        const mean = vals.length > 0 ? vals.reduce((a, b) => a + b, 0) / vals.length : 0;
        hourMeans.push(Number(mean.toFixed(1)));
      }

      const colors = ["#f97316", "#06b6d4", "#a855f7", "#10b981", "#eab308", "#f43f5e"];
      const color = colors[idx % colors.length];
      const stationName = KOLKATA_STATIONS[stKey]?.name || stKey;

      return {
        name: stationName,
        type: "line",
        smooth: true,
        data: hourMeans,
        itemStyle: { color },
        lineStyle: { width: 2 },
        showSymbol: false,
      };
    });

    return {
      title: {
        text: "Diurnal PM2.5 Cycle by Station",
        subtext: "Hourly mean (UTC) showing rush hour and nocturnal boundary layer compression",
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
        top: 25,
        right: 0,
        textStyle: { color: "#94a3b8", fontSize: 10 },
      },
      grid: {
        left: "4%",
        right: "4%",
        bottom: "10%",
        top: "24%",
        containLabel: true,
      },
      xAxis: {
        type: "category",
        data: hours,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#94a3b8", fontSize: 10 },
      },
      yAxis: {
        type: "value",
        name: "µg/m³",
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#94a3b8" },
      },
      series,
    };
  }, [data]);

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <ReactECharts
        option={option}
        style={{ height: "320px", width: "100%" }}
        notMerge={true}
        lazyUpdate={true}
      />
    </div>
  );
};

