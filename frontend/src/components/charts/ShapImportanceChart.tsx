"use client";

import React, { useMemo } from "react";
import ReactECharts from "echarts-for-react";

interface FeatureImportanceProps {
  importanceData: Array<{
    feature: string;
    importance: number;
  }>;
}

export const ShapImportanceChart: React.FC<FeatureImportanceProps> = ({
  importanceData,
}) => {
  const option = useMemo(() => {
    if (!importanceData || importanceData.length === 0) return {};

    // Sort ascending so the top driver appears at the top of the horizontal bar chart
    const top = [...importanceData]
      .sort((a, b) => a.importance - b.importance)
      .slice(-12);

    const features = top.map((d) => d.feature);
    const values = top.map((d) => Number(d.importance.toFixed(3)));

    return {
      title: {
        text: "Lag-Free Model Feature Importance",
        subtext:
          "Attribution model excludes AR lags to surface genuine environmental & transport drivers",
        left: "left",
        textStyle: { color: "#f8fafc", fontSize: 13, fontWeight: "bold" },
        subtextStyle: { color: "#94a3b8", fontSize: 11 },
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: "#0f172a",
        borderColor: "#334155",
        textStyle: { color: "#e2e8f0" },
      },
      grid: {
        left: "3%",
        right: "6%",
        bottom: "5%",
        top: "22%",
        containLabel: true,
      },
      xAxis: {
        type: "value",
        name: "Permutation / SHAP Importance",
        splitLine: { lineStyle: { color: "#1e293b" } },
        axisLabel: { color: "#94a3b8" },
      },
      yAxis: {
        type: "category",
        data: features,
        axisLine: { lineStyle: { color: "#334155" } },
        axisLabel: { color: "#cbd5e1", fontSize: 11, fontWeight: "500" },
      },
      series: [
        {
          name: "Importance",
          type: "bar",
          data: values,
          itemStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 1,
              y2: 0,
              colorStops: [
                { offset: 0, color: "#ea580c" },
                { offset: 1, color: "#f97316" },
              ],
            },
            borderRadius: [0, 4, 4, 0],
          },
        },
      ],
    };
  }, [importanceData]);

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

