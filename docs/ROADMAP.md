# SRS → Implementation Roadmap

Decisions (2026-07-03): new repo · modular monolith v1 · MT5 first (Wine bridge on
Hetzner) · old `analyze` bot keeps running in parallel until BLACK LION is validated.

| Phase | SRS docs | Deliverable | Status |
|---|---|---|---|
| 1. Foundation | 01–05, 31–32 | Repo, configs, logging, event bus, docker-compose, Journal/SQLite ✅ | **done** |
| 2. Market Data | 06–08 | Source Protocol + Replay/Yahoo/MT5 sources ✅, indicators, validation, Runtime scan loop ✅ (Timescale store = v2) | **done (feed live); Timescale pending** |
| 3. Features & Structure | 09–14 | Market Structure ✅, Liquidity ✅, OB ✅, FVG ✅, ICT ✅, Feature Engineer ✅ (58 features/signal → journal, AI training set) | **done** |
| 4. Rule Engine | 15 | Confluence scoring + BUY/SELL/NO TRADE + signal pipeline ✅ | **done** |
| 5. AI + Probability | 16–17 | XGBoost/LightGBM ensemble, calibration, EV gate (needs ≥3–6 months of journalled outcomes to train on; ships after live signal history accumulates) | pending |
| 6. Risk Engine | 18 | Sizing, daily/weekly loss locks, exposure, correlation ✅ | **done** |
| 7. Execution | 19 | Broker Protocol + PaperBroker ✅, Execution Engine ✅ (validation/retry/slippage/partial/breakeven/sync), MT5 bridge adapter written (needs live terminal) | **done (paper); MT5 pending creds** |
| 8. Backtesting | 20–21 | Replay, walk-forward, Monte Carlo, optimizer | pending |
| 9. Reporting & Telegram | 22–23 | Telegram signals + outcomes + daily/weekly reports ✅, chat allowlist enforced ✅ (charts = optional next; separate BL_TELEGRAM_* bot) | **done (text); charts optional** |
| 10. Monitoring & Security | 24–25, 38–40 | Health monitor ✅ (liveness/feed/resources, rate-limited Telegram alerts, /health command). Security (audit/secrets) pending — low priority for single-op dry-run | **monitoring done; security pending** |
| 11. Dashboard | 32 frontend | Next.js dashboard | v2 |
| 12. Production | 29, 43 | Dry-run deploy ready: lean docker-compose (bot-only) + Dockerfile + docs/DEPLOY.md; live path validated on real Yahoo data ✅. New Hetzner server pending user | **deploy-ready** |

Deferred to v2+ (deliberately, single-server reality): Kubernetes, gRPC
microservice split, RabbitMQ/Kafka (in-process event bus first), multi-user
JWT/RBAC/MFA (single-operator token auth first), 10k-user scaling docs.

Carry-over lessons from the old `analyze` bot (do not repeat):
- Telegram poller MUST allowlist `TELEGRAM_CHAT_ID` (old bot accepted commands from anyone).
- Exchange-side SL must move to breakeven when the journal does, or journal must model full exit.
- Never block the asyncio loop with sync network calls — every I/O goes through executors.
- Market-hours gate must be DST-aware (use exchange calendars, not fixed UTC hours).
