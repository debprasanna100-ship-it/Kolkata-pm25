"use client";

import React, { useState, useMemo } from "react";
import { getAQICategory } from "@/lib/constants/aqi";
import { Sliders, Wind, CloudSun, Flame, Gauge, ArrowRight, RefreshCw, Car } from "lucide-react";

export const SimulatorView: React.FC = () => {
  // Scenario perturbation state
  const [windSpeed, setWindSpeed] = useState<number>(2.2);
  const [pblHeight, setPblHeight] = useState<number>(450);
  const [relativeHumidity, setRelativeHumidity] = useState<number>(75);
  const [temperature, setTemperature] = useState<number>(21);
  const [fireCount, setFireCount] = useState<number>(65);
  const [hour, setHour] = useState<number>(21);
  const [distRoad, setDistRoad] = useState<number>(0.4);

  // Reset to typical winter evening baseline
  const handleReset = () => {
    setWindSpeed(2.2);
    setPblHeight(450);
    setRelativeHumidity(75);
    setTemperature(21);
    setFireCount(65);
    setHour(21);
    setDistRoad(0.4);
  };

  // Live atmospheric proxy model calculation (simulating GBDT quantile inference)
  const { pred, q10, q90, ventilation } = useMemo(() => {
    // Ventilation coefficient = wind speed * PBL height
    const vent = windSpeed * pblHeight;

    // Atmospheric dispersion factor (lower ventilation = higher concentration)
    const dispersionPenalty = Math.max(10, 18000 / (vent + 200));

    // Moisture / secondary aerosol formation factor
    const moistureBoost = relativeHumidity > 70 ? (relativeHumidity - 70) * 0.9 : 0;

    // Upwind regional fire plume contribution
    const fireContrib = fireCount * 0.42;

    // Road proximity rush-hour boost
    const isRush = (hour >= 8 && hour <= 11) || (hour >= 18 && hour <= 22);
    const trafficBoost = isRush ? Math.max(5, (1.5 - distRoad) * 16) : 4;

    // Baseline seasonal urban background
    const baseline = 28;

    const estimatedPM = baseline + dispersionPenalty + moistureBoost + fireContrib + trafficBoost;

    // Quantile spread (intervals widen with higher humidity and extreme fires)
    const spread = 12 + estimatedPM * 0.18 + (relativeHumidity / 100) * 8;
    const q10Val = Math.max(5, estimatedPM - spread * 0.9);
    const q90Val = estimatedPM + spread * 1.1;

    return {
      pred: estimatedPM,
      q10: q10Val,
      q90: q90Val,
      ventilation: vent,
    };
  }, [windSpeed, pblHeight, relativeHumidity, temperature, fireCount, hour, distRoad]);

  const aqi = getAQICategory(pred);

  return (
    <div className="space-y-6">
      {/* Title Card */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-5 shadow-sm">
        <div>
          <div className="flex items-center gap-2">
            <Sliders className="h-5 w-5 text-accent" />
            <h2 className="text-base font-bold text-white">
              Interactive "What-If" Scenario Simulator
            </h2>
          </div>
          <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
            Perturb environmental, meteorological, and transport variables to observe immediate changes in predicted surface PM2.5 and uncertainty intervals.
          </p>
          <div className="mt-2 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-[11px] text-yellow-200">
            <strong>⚠️ Disclaimer:</strong> This is a <em>heuristic physics-inspired approximation</em> for
            interactive exploration. It does <strong>not</strong> invoke the trained GBDT model. For research-grade
            predictions, use the pipeline output from <code className="text-accent">python -m pm25.cli train</code>.
          </div>
        </div>
        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-muted/60 px-3 py-1.5 text-xs font-medium text-gray-300 hover:bg-muted hover:text-white transition-colors"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Reset Baseline
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Controls Column */}
        <div className="lg:col-span-7 space-y-4 rounded-xl border border-border bg-card p-5 shadow-sm">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground border-b border-border pb-2">
            Meteorological & Transport Parameters
          </h3>

          {/* Wind Speed */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                <Wind className="h-3.5 w-3.5 text-teal-400" /> Wind Speed (10m):
              </span>
              <span className="font-mono font-bold text-teal-400">{windSpeed.toFixed(1)} m/s</span>
            </div>
            <input
              type="range"
              min="0.5"
              max="10.0"
              step="0.1"
              value={windSpeed}
              onChange={(e) => setWindSpeed(parseFloat(e.target.value))}
              className="w-full accent-teal-500 h-1.5 bg-muted rounded cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>0.5 m/s (Stagnant)</span>
              <span>10.0 m/s (Breezy)</span>
            </div>
          </div>

          {/* Planetary Boundary Layer Height */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                <CloudSun className="h-3.5 w-3.5 text-yellow-400" /> Boundary Layer Height (PBL):
              </span>
              <span className="font-mono font-bold text-yellow-400">{pblHeight} m</span>
            </div>
            <input
              type="range"
              min="150"
              max="2200"
              step="25"
              value={pblHeight}
              onChange={(e) => setPblHeight(parseInt(e.target.value))}
              className="w-full accent-yellow-500 h-1.5 bg-muted rounded cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>150 m (Winter Inversion)</span>
              <span>2,200 m (Convective Summer)</span>
            </div>
          </div>

          {/* Relative Humidity */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                Relative Humidity (RH):
              </span>
              <span className="font-mono font-bold text-blue-400">{relativeHumidity}%</span>
            </div>
            <input
              type="range"
              min="20"
              max="98"
              step="1"
              value={relativeHumidity}
              onChange={(e) => setRelativeHumidity(parseInt(e.target.value))}
              className="w-full accent-blue-500 h-1.5 bg-muted rounded cursor-pointer"
            />
          </div>

          {/* Upwind Fire Detections */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                <Flame className="h-3.5 w-3.5 text-orange-400" /> Upwind Fire Count (FIRMS):
              </span>
              <span className="font-mono font-bold text-orange-400">{fireCount} fires</span>
            </div>
            <input
              type="range"
              min="0"
              max="250"
              step="5"
              value={fireCount}
              onChange={(e) => setFireCount(parseInt(e.target.value))}
              className="w-full accent-orange-500 h-1.5 bg-muted rounded cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-muted-foreground">
              <span>0 (No burning)</span>
              <span>250 (Intense crop residue burning)</span>
            </div>
          </div>

          {/* Hour of Day */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                Hour of Day (Local Time):
              </span>
              <span className="font-mono font-bold text-purple-400">{hour}:00 hrs</span>
            </div>
            <input
              type="range"
              min="0"
              max="23"
              step="1"
              value={hour}
              onChange={(e) => setHour(parseInt(e.target.value))}
              className="w-full accent-purple-500 h-1.5 bg-muted rounded cursor-pointer"
            />
          </div>

          {/* Highway Proximity */}
          <div className="space-y-1.5">
            <div className="flex justify-between text-xs">
              <span className="flex items-center gap-1.5 text-gray-300">
                <Car className="h-3.5 w-3.5 text-emerald-400" /> Highway Distance:
              </span>
              <span className="font-mono font-bold text-emerald-400">{distRoad.toFixed(2)} km</span>
            </div>
            <input
              type="range"
              min="0.2"
              max="2.0"
              step="0.05"
              value={distRoad}
              onChange={(e) => setDistRoad(parseFloat(e.target.value))}
              className="w-full accent-emerald-500 h-1.5 bg-muted rounded cursor-pointer"
            />
          </div>
        </div>

        {/* Live Output Gauge Column */}
        <div className="lg:col-span-5 space-y-4">
          <div className="rounded-xl border border-border bg-card p-6 shadow-sm text-center">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Predicted Surface PM2.5
            </span>

            <div className="my-4">
              <div
                className="inline-block rounded-2xl px-6 py-4 shadow-lg text-white"
                style={{ backgroundColor: aqi.color }}
              >
                <div className="text-4xl font-black font-mono tracking-tight">
                  {pred.toFixed(1)}
                  <span className="text-lg font-normal ml-1">µg/m³</span>
                </div>
                <div className="text-xs font-bold uppercase tracking-wider mt-1 opacity-90">
                  {aqi.name}
                </div>
              </div>
            </div>

            <div className="text-xs text-muted-foreground">
              {aqi.advisory}
            </div>

            {/* Prediction Interval Spread */}
            <div className="mt-6 rounded-lg bg-muted/40 p-3 border border-border">
              <div className="text-xs font-semibold text-gray-300 mb-1">
                80% Confidence Interval Spread [q10 — q90]
              </div>
              <div className="flex items-center justify-center gap-3 font-mono text-sm font-bold text-accent">
                <span>{q10.toFixed(1)} µg</span>
                <ArrowRight className="h-4 w-4 text-muted-foreground" />
                <span>{q90.toFixed(1)} µg</span>
              </div>
              <div className="text-[11px] text-muted-foreground mt-1">
                Interval Width: {(q90 - q10).toFixed(1)} µg/m³
              </div>
            </div>

            {/* Derived Physical Indicators */}
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded bg-muted/30 p-2 border border-border/50 text-left">
                <span className="text-muted-foreground text-[10px]">Ventilation Coeff:</span>
                <div className="font-mono font-bold text-white">{ventilation.toFixed(0)} m²/s</div>
              </div>
              <div className="rounded bg-muted/30 p-2 border border-border/50 text-left">
                <span className="text-muted-foreground text-[10px]">Inversion Strength:</span>
                <div className="font-mono font-bold text-white">
                  {pblHeight < 400 ? "Severe Ground Inversion" : "Moderate Mixing"}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

