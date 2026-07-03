# BLACK LION AI

AI-assisted, risk-first trading platform. Built from the 50-document BLACK LION AI
SRS (see `docs/ROADMAP.md` for the SRS → implementation mapping).

**v1 architecture: modular monolith.** Every engine from the SRS is an isolated,
unit-tested module inside one Python process; infrastructure is one
`docker-compose` stack (bot + PostgreSQL/TimescaleDB + Redis + MT5 bridge).
Engines communicate through typed interfaces and an in-process event bus, so any
module can later be split into its own service without rewriting logic (SRS doc 02,
"Every module must be replaceable").

## Decision pipeline (SRS docs 06–19)

```
MT5 / Binance market data
  → Data Validation (07)  → Normalizer (08)   → Feature Engineering (09)
  → Market Structure (10) → Liquidity (11)    → Order Block (12) → FVG (13) → ICT (14)
  → Rule Engine (15, deterministic confluence)
  → AI Decision Engine (16, ensemble — phase 5)
  → Probability Engine (17, calibrated P + EV>0)
  → Risk Engine (18, position sizing / daily loss / exposure)
  → Execution Engine (19, MT5 first) → Journal → Analytics → Learning
```

The AI never places trades. Execution always passes Rule → Probability → Risk.

## Local development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Deployment (Hetzner)

```bash
cp .env.example .env   # fill in
docker compose up -d --build
```

MT5 on Linux runs inside the `mt5` container (MetaTrader 5 under Wine with an
rpyc bridge on port 8001). The bot talks to it through
`blacklion/execution/mt5/bridge.py`; the same adapter runs natively on Windows.
