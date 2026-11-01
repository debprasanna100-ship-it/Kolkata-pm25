"""Kolkata PM2.5 estimation and source attribution.

Layers:
    data      adapters + demo generator
    features  engineering (lags, cyclical, upwind fires, leakage guards)
    models    baselines, quantile GBDT, LSTM, validation
    explain   SHAP + rule-based source proxies
    app       Streamlit dashboard
"""

__version__ = "0.1.0"
