# Kolkata PM2.5 — Frontend Application

Modern scientific frontend for hourly $\text{PM}_{2.5}$ estimation, multi-horizon uncertainty forecasting, and causal source attribution in Kolkata.

## Architecture

This frontend is designed as a decoupled, high-performance web dashboard built with:
- **Next.js 15 / React 19 + TypeScript**: App Router architecture with server and client components.
- **DuckDB-Wasm**: In-browser analytical database querying Parquet artifacts with sub-3ms latency.
- **MapLibre GL + Deck.gl**: WebGL-accelerated geospatial visualization (CAAQMS station nodes, MAIAC AOD heatmaps, wind particle streamlines, upwind FIRMS fire cones).
- **Apache ECharts (`echarts-for-react`)**: Multi-horizon 80% prediction interval curves ($\text{PI}_{80} = [q_{10}, q_{90}]$), diurnal cycles, and SHAP attribution heatmaps.
- **Tailwind CSS + Radix UI (shadcn/ui)**: Clean, dense scientific UI with dark/light themes.
- **Zustand**: Fast, lightweight client-side state management.

## Directory Structure

```
frontend/
├── public/
│   ├── data/             # Parquet datasets & model metric artifacts
│   └── geo/              # Kolkata GeoJSON boundaries & station locations
├── src/
│   ├── app/              # App Router pages (Overview, Forecasts, Attribution, Simulator)
│   ├── components/
│   │   ├── charts/       # ECharts scientific visualizations
│   │   ├── map/          # Deck.gl & MapLibre map layers
│   │   ├── simulator/    # What-If scenario perturbation controls
│   │   ├── station/      # Station drawer & telemetry cards
│   │   └── ui/           # Radix / Tailwind UI primitives
│   ├── lib/
│   │   ├── constants/    # CPCB AQI standards, station coordinates
│   │   ├── duckdb/       # In-browser WebAssembly SQL client
│   │   ├── store/        # Zustand global UI state
│   │   └── types/        # TypeScript atmospheric & model schemas
│   └── styles/           # Global styles and Tailwind directives
├── package.json
└── tsconfig.json
```

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the application.

