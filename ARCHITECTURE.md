# CivicOS Architecture

```text
Citizen / Mobile Browser
        |
        | Report + SOS + GPS + Evidence
        v
Flask Application Layer
        |
        +--> Validation / Recovery / Notifications
        +--> Smart Routing + Priority + SLA
        +--> Worker Queue + Reserve Capacity Guard
        +--> Timeline / Proof of Resolution
        |
        v
SQLite Operational Store
        |
        +------------------------------+
        |                              |
        v                              v
Civic Intelligence Engine          Dashboard APIs
(civicos_intelligence.py)              |
        |                              v
        +--> Civic Memory         Admin/Public/Worker UI
        +--> Causal Clusters            |
        +--> Blind Spots                 +--> Leaflet live map
        +--> Risk Forecast               +--> Offline-safe map fallback
        +--> Civic Debt                  +--> Chart.js / CSS fallback charts
        +--> Cascade Simulation
        +--> Service Equity
        +--> Chronic Failure
        +--> Public Value Optimizer
        +--> Route Batching
        +--> Sweep Suggestions
        +--> Proof Verification
```

## Why the intelligence engine is separate
`civicos_intelligence.py` contains deterministic, testable decision logic. Flask routes remain responsible for web requests and operational workflow. `civicos_config.py` keeps departments, field teams, skills and routing rules editable without rewriting the application.

## AI design principle
Optional LLM classification can improve natural-language routing when an API key is configured. Core priority, SLA, causal/risk/debt/optimizer/proof calculations continue to work without an LLM or internet connection. This makes the hackathon demo reliable and keeps numerical evidence explainable.

## Production upgrade path
For production municipal use, the current prototype scoring should be calibrated with real asset/GIS records, population/service coverage, weather data, validated cost models and historical repair outcomes. SQLite can then be replaced with PostgreSQL/PostGIS; authentication should be role-based; background jobs should handle escalation/notifications; and causal/risk models should be independently evaluated before operational deployment.
