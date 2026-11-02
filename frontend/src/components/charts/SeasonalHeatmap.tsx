"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";

interface SeasonalHeatmapProps {
  seasonalData: Array<{
    feature: string;
    season: string;
    share?: number;
    importance?: number;
  }>;
}

export const SeasonalHeatmap: React.FC<SeasonalHeatmapProps> = ({ seasonalData }) => {
  const option = useMemo(() => {
    if (!seasonalData || seasonalData.length === 0) return {};

    const seasons = ["winter", "pre-monsoon", "monsoon", "post-monsoon"];
    // Extract unique features
    const allFeatures = Array.from(new Set(seasonalData.map((d) => d.feature)));
    // Top 10 features by max share
    const featureMaxMap = new Map<string, number>();
    seasonalData.forEach((d) => {
      const val = d.share ?? d.importance ?? 0;
      const cur = featureMaxMap.get(d.feature) ?? 0;
      if (val > cur) featureMaxMap.set(d.feature, val);
    });

    const topFeatures = allFeatures
      .sort((a, b) => (featureMaxMap.get(b) ?? 0) - (featureMaxMap.get(a) ?? 0))
      .slice(0, 10);

    // Matrix coordinates [x, y, value] where x = season index, y = feature index
    const dataPoints: [number, number, number][] = [];
    topFeatures.forEach((feat, yIdx) => {
      seasons.forEach((season, xIdx) => {
        const item = seasonalData.find(
          (d) => d.feature === feat && d.season.toLowerCase() === season
        );
        const val = item?.share ?? item?.importance ?? 0;
        dataPoints.push([xIdx, yIdx, Number((val * 100).toFixed(1))]);
      });
    });

    return {
      title: {
        text: "Seasonal Driver Shift (% Share of Attribution)",
        subtext: "Fires & inversion dominate winter; dust & ventilation dominate pre-monsoon",
        left: "left",
        textStyle: { color: "#f8fafc", fontSize: 13, fontWeight: "bold" },
        subtextStyle: { color: "#94a3b8", fontSize: 11 },
      },
      tooltip: {
        position: "top",
        backgroundColor: "#0f172a",
        borderColor: "#334155",
        textStyle: { color: "#e2e8f0" },
        formatter: (params: any) => {
          const season = seasons[params.data[0]];
          const feat = topFeatures[params.data[1]];
          const val = params.data[2];
          return `<strong>${feat}</strong><br/>${season}: ${val}% share`;
        },
      },
      grid: {
        left: "4%",
        right: "10%",
        bottom: "8%",
        top: "22%",
        containLabel: true,
      },
      xAxis: {
        type: "category",
        data: ["Winter", "Pre-Monsoon", "Monsoon", "Post-Monsoon"],
        splitArea: { show: true },
        axisLabel: { color: "#cbd5e1" },
        axisLine: { lineStyle: { color: "#334155" } },
      },
      yAxis: {
        type: "category",
        data: topFeatures,
        splitArea: { show: true },
        axisLabel: { color: "#cbd5e1", fontSize: 11 },
        axisLine: { lineStyle: { color: "#334155" } },
      },
      visualMap: {
        min: 0,
        max: 30,
        calculable: true,
        orient: "vertical",
        right: "0%",
        top: "center",
        textStyle: { color: "#94a3b8" },
        inRange: {
          color: ["#1e293b", "#0f766e", "#eab308", "#f97316", "#dc2626"],
        },
      },
      series: [
        {
          name: "Attribution Share",
          type: "heatmap",
          data: dataPoints,
          label: {
            show: true,
            formatter: (p: any) => `${p.data[2]}%`,
            color: "#ffffff",
            fontSize: 10,
          },
          emphasis: {
            itemStyle: {
              shadowBlur: 10,
              shadowColor: "rgba(0, 0, 0, 0.5)",
            },
          },
        },
      ],
    };
  }, [seasonalData]);

  return (
    <div className="rounded-xl border border-border bg-card p-4 shadow-sm">
      <ReactECharts
        option={option}
        style={{ height: "360px", width: "100%" }}
        notMerge={true}
        lazyUpdate={true}
      />
    </div>
  );
};

