export interface AQICategory {
  name: string;
  min: number;
  max: number;
  color: string;
  textColor: string;
  advisory: string;
}

export const CPCB_PM25_CATEGORIES: AQICategory[] = [
  {
    name: "Good",
    min: 0,
    max: 30,
    color: "#10b981",
    textColor: "#ffffff",
    advisory: "Minimal impact on health."
  },
  {
    name: "Satisfactory",
    min: 30.1,
    max: 60,
    color: "#84cc16",
    textColor: "#1f2937",
    advisory: "Minor breathing discomfort to sensitive people."
  },
  {
    name: "Moderate",
    min: 60.1,
    max: 90,
    color: "#eab308",
    textColor: "#1f2937",
    advisory: "Breathing discomfort to people with lungs, asthma and heart diseases."
  },
  {
    name: "Poor",
    min: 90.1,
    max: 120,
    color: "#f97316",
    textColor: "#ffffff",
    advisory: "Breathing discomfort to most people on prolonged exposure."
  },
  {
    name: "Very Poor",
    min: 120.1,
    max: 250,
    color: "#ef4444",
    textColor: "#ffffff",
    advisory: "Respiratory illness on prolonged exposure."
  },
  {
    name: "Severe",
    min: 250.1,
    max: 1000,
    color: "#7f1d1d",
    textColor: "#ffffff",
    advisory: "Affects healthy people and seriously impacts those with existing diseases."
  }
];

export function getAQICategory(pm25: number): AQICategory {
  if (pm25 <= 0) return CPCB_PM25_CATEGORIES[0];
  for (const cat of CPCB_PM25_CATEGORIES) {
    if (pm25 <= cat.max) return cat;
  }
  return CPCB_PM25_CATEGORIES[CPCB_PM25_CATEGORIES.length - 1];
}

