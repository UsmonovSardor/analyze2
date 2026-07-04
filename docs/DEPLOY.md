# BLACK LION AI — Hetzner Deploy (v1 dry-run)

New dedicated server, alongside (not touching) the old `analyze` bot.

## 1. Create the server (Hetzner Console)
- **Add Server** → Location: Falkenstein/Nuremberg (EU) → Image: **Ubuntu 24.04**
- Type: **CPX21** (3 vCPU / 4 GB) is plenty for the dry-run; CX22 also fine
- Add your **SSH key** → Create.
- Note the new server's public IP.

## 2. First login + Docker
```bash
ssh root@<NEW_SERVER_IP>
apt update && apt install -y docker.io docker-compose-plugin git
systemctl enable --now docker
```

## 3. Clone the repo
```bash
cd /root
git clone https://github.com/UsmonovSardor/analyze2.git blacklion
cd blacklion
```

## 4. Create the .env (NOT from git — secrets live only on the server)
```bash
cat > .env <<'EOF'
BL_TELEGRAM_BOT_TOKEN=<your new bot token>
BL_TELEGRAM_CHAT_ID=<your new group id>
BL_ENV=production
BL_CONFIG_DIR=configs
BL_BALANCE=10000
BL_SCAN_INTERVAL=1800
BL_OUTCOME_INTERVAL=300
BL_COOLDOWN_HOURS=3
BL_DIGEST_HOUR_UTC=16
DB_PATH=/data/journal.db
MT5_LOGIN=
MT5_PASSWORD=
MT5_SERVER=
EOF
```

## 5. Build + run (dry-run: PaperBroker + Yahoo feed)
```bash
docker compose up -d --build
docker compose logs -f bot        # watch the boot + first scan
```
You should see `Boot ... broker=paper connected=True` and, every 30 min,
`ScanDone signals=N`. Real signals post to your Telegram group.

## 6. Update after new commits
```bash
cd /root/blacklion && git pull && docker compose up -d --build
```

## Notes
- The journal (SQLite) persists on the `bl_data` docker volume across restarts.
- MT5 live trading: fill MT5_* in .env, switch to `docker compose -f
  docker-compose.full.yml up -d` (adds the MT5 Wine bridge), log the terminal
  in once via noVNC. Until then everything runs on the PaperBroker (no real orders).
