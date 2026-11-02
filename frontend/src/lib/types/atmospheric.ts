export type ForecastHorizon = 0 | 1 | 6 | 24;

export type Season = "winter" | "pre-monsoon" | "monsoon" | "post-monsoon";

export type SourceProxy = "biomass" | "dust" | "traffic" | "secondary" | "background";

export interface HourlyReading {
  time: string;
  station: string;
  pm25: number;
  pm10?: number;
  no2?: number;
  so2?: number;
  co?: number;
  o3?: number;
  temp?: number;
  rh?: number;
  ws?: number;
  wd?: number;
  pbl?: number;
  ventilation?: number;
  aod?: number;
  aod_missing: 0 | 1;
  fire_upwind?: number;
}

export interface ModelPrediction {
  time: string;
  station: string;
  y: number;
  pred: number;
  q10?: number;
  q90?: number;
  aod_missing: 0 | 1;
  horizon_h: ForecastHorizon;
}

export interface ModelMetrics {
  horizon_h: ForecastHorizon;
  rmse: number;
  mae: number;
  r2: number;
  bias: number;
  recall?: number;
  pi80_coverage?: number;
}

export interface ProxyAgreementItem {
  season: Season;
  proxy: SourceProxy;
  proxy_share: number;
  expected_drivers: string[];
  model_top_drivers: string[];
  supported: boolean;
}

export interface ScenarioSimulationParams {
  windSpeed: number;
  pblHeight: number;
  relativeHumidity: number;
  temperature: number;
  fireCount: number;
  hourOfDay: number;
  season: Season;
}

