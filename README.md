# NovaBot: Autonomous Crypto Micro-Trading Framework

NovaBot is a high-speed, autonomous cryptocurrency micro-trading bot built to execute quick, small trades (scalping/grid trading) while strictly enforcing rigid risk thresholds. It features a completely decoupled architecture utilizing a Python/FastAPI backend and a premium, zero-dependency glassmorphism UI.

## 🏗 System Architecture

The application is split into three main layers:

1. **Exchange Connector (`ccxt`)**: Handles asynchronous, non-blocking communication with the Binance Spot exchange.
2. **Bot Engine (`bot_manager.py`)**: The brain of the operation. It generates isolated concurrent workers for each cryptocurrency pair to ensure parallel trading without "traffic jams".
3. **Web Dashboard (`FastAPI` + `Vanilla JS/CSS`)**: A beautiful frontend interface served locally. It connects to the Python backend via WebSockets to give you real-time terminal logs, trade ledgers, and control without needing page reloads or heavy Node.js frameworks.

---

## 🚦 Installation and Launching

### Prerequisites
- Python 3.9+ 
- A Binance Account (API Keys required for real trading, defaults to Testnet)

### Launching the Dashboard

1. Navigate to the bot's repository in your terminal.
2. Activate your Virtual Environment:
   ```bash
   source venv/bin/activate
   ```
3. Boot the server:
   ```bash
   python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```
4. Open your browser and navigate to `http://localhost:8000/`.

---

## 📈 How It Works: Strategy & Execution

This bot utilizes a **Dynamic Grid Scalping** strategy combined with minor **Mean Reversion**. Because humans cannot react to micro-seconds of spread gaps, the bot is constantly polling "Tickers" asynchronously.

### The Trade Lifecycle:
1. **Target Identification**: A parallel background worker monitors an asset (e.g., `BTC/USDT`).
2. **Proactive Safety Validation**: Before any trade is executed, the `RiskEngine` calculates the current Bid/Ask spread and checks if it mathematically allows for your required minimum profit margin (factoring in Binance's standard 0.1% fees).
3. **Entry Execution**: If the risk check passes, the bot buys a minor fraction of the coin.
4. **Target Seeking**: It calculates a predetermined exit target (e.g. entry price × 1.002 to catch a 0.2% jump).
5. **Exit Execution**: The bot sells as soon as the target is hit, then waits for a cooling-off period before looking for the next dip.

---

## 🛡 Risk Management Estimates

Traditional bots buy blindly. NovaBot utilizes **Proactive Pre-estimation**. 

In `bot_manager.py`, the `RiskEngine` dictates the rules of engagement:

- **Spread Calculation:** `spread = ask - bid`. If the spread is too wide, the bot refuses to trade, as the slippage would instantly result in a loss.
- **Profit Margins:** Governed by `self.min_profit_margin = 1.002`. This forces the bot to mathematically estimate that it will clear a 0.2% gain *after* the exchange takes its fee toll.
- **Micro-Boundaries:** `self.max_trade_amount_usdt` enforces that the bot only puts a small fractional exposure ($10-$15 per trade) into the market at any given time.

### The Master Control Switch
The dashboard includes an immediate Master Switch. Toggling this "Off" triggers a global shutdown hook in all python workers. They immediately drop their current routines, cancel their trackers, and stop generating new API keys. 

### Exclusion Protocol (Blacklisting)
If you notice a coin is experiencing extreme, unpredictable volatility (e.g. a "meme" coin pumping and dumping maliciously), type its ticker (e.g. `SHIB/USDT`) into the UI's Exclusion table. The UI sends a REST payload to the `RiskEngine`, which instantly skips all signals generated for that coin.

---

## ⚠️ Important Live Deployment Warning
By default, the engine is set to `testnet=True`. It simulates paper trading against the Binance Future Testnet endpoints. 

When you are ready to trade actual capital:
1. Open `main.py`
2. Change `bot = CryptoBotManager(testnet=True)` to `testnet=False`
3. Provide your real Binance `api_key` and `secret_key` into the initialization parameters.
4. ENSURE YOUR BINANCE API KEYS HAVE **WITHDRAWALS DISABLED**.
