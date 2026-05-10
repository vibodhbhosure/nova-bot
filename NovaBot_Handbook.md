# NovaBot Project Handbook
*Autonomous High-Frequency Crypto Micro-Trader*

---

## 1. System Architecture
NovaBot is built around an event-driven architecture designed to stream real-time telemetry to the browser while executing trading algorithms autonomously.

* **Backend Engine:** Python `FastAPI` providing high-performance REST APIs and real-time WebSockets.
* **Exchange Integrations:** `CCXT` handles asynchronous communication directly to Binance (both Testnet & Live Spot).
* **Analytics & Indicators:** `pandas` and `ta` strictly manage the market dataset processing (OHLCV candles & RSI).
* **Storage Layer:** SQLite3 (`nova.db`) maintains persistent tables for raw system logs and transaction ledgers.
* **Frontend Dashboard:** Pure vanilla HTML/CSS/JS communicating over WebSockets for instant, zero-reload telemetry sync.

## 2. Server Deployment
NovaBot is deployed to an **Oracle Cloud "Always Free" Ubuntu Linux Instance** to ensure 24/7 background operation without sleeping. 

### Specifications & Pathing
* **Public IP:** `80.225.216.191`
* **Operating System:** Ubuntu Linux 22/24.04
* **App Directory:** `/home/ubuntu/crypto-micro-bot/`
* **Port Mapping:** Exposes port `8000` via internal `iptables` and Oracle's Virtual Cloud Network (VCN) Ingress rules.

### Service Management (`systemd`)
The bot runs as a background service managed by Linux's native `systemd` daemon, meaning it will automatically restart itself if it crashes or if the server reboots.

You can interact with it via your local terminal SSH:
* **Check Status:** `ssh -i ~/Desktop/NovaBot/ssh-key-2026-05-10-2.key ubuntu@80.225.216.191 'sudo systemctl status novabot'`
* **Restart Bot:** `ssh -i ~/Desktop/NovaBot/ssh-key-2026-05-10-2.key ubuntu@80.225.216.191 'sudo systemctl restart novabot'`
* **Stop Bot:** `ssh -i ~/Desktop/NovaBot/ssh-key-2026-05-10-2.key ubuntu@80.225.216.191 'sudo systemctl stop novabot'`
* **View Live Logs:** `ssh -i ~/Desktop/NovaBot/ssh-key-2026-05-10-2.key ubuntu@80.225.216.191 'sudo journalctl -u novabot -f'`

## 3. The CI/CD Pipeline (Continuous Deployment)
NovaBot uses a continuous deployment pipeline via **GitHub Actions**. Any time you push a code change to the `main` branch, the cloud server automatically pulls the update and restarts the bot in seconds.

### How It Works:
1. You make a code change on your local computer.
2. You commit and push to GitHub: `git push origin main`
3. GitHub Actions triggers the `.github/workflows/deploy.yml` file.
4. An isolated runner securely SSH's into your Oracle VM using `rsync`.
5. It uploads *only* the files that changed (excluding your private `.env` and `nova.db` ledger so you never lose data).
6. It runs `sudo systemctl restart novabot` to immediately apply the fresh code.

### Required GitHub Secrets Setup:
For the pipeline to have permission to reach your server, you must provide it with the SSH keys. Go to your GitHub Repository -> **Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**.

Add these two secrets exactly:
1. `SERVER_IP` : `80.225.216.191`
2. `SERVER_SSH_KEY` : *(Paste the entire contents of your `ssh-key-2026-05-10-2.key` file, including the BEGIN and END lines).*

## 4. Security & Exclusions
* **Environment Variables (`.env`)**: Your email credentials are fully detached from the codebase via `python-dotenv`. Because `.env` is inside `.gitignore`, it will never be uploaded to GitHub.
* **Database (`nova.db`)**: Kept out of version control and excluded from the deployment sync to ensure your historic trade logs are never overwritten.
* **API Key Safety:** Binance Spot keys are passed exclusively to CCXT logic dynamically from the UI, and never hardcoded. You *must* whitelist your Oracle Server IP (`80.225.216.191`) in Binance to allow Live Trading.

## 5. Scaling or Debugging
If you want to move from Uvicorn to a true "Zero-Downtime" reverse proxy configuration in the future, you will install `Nginx` and `Gunicorn`. Nginx will proxy port 80/443 to Gunicorn, and Gunicorn can hot-reload its workers via a `SIGHUP` signal during the GitHub action, meaning users viewing the dashboard won't even notice the deployment restarting.
