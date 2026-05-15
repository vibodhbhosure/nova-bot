import ccxt.async_support as ccxt
import asyncio
import logging
import uuid
from typing import List
import pandas as pd
import ta
import sqlite3
import smtplib
import os
from dotenv import load_dotenv
from email.message import EmailMessage

load_dotenv()
logging.basicConfig(level=logging.INFO)

class RiskEngine:
    def __init__(self):
        self.blacklisted_symbols = ["PEPE/USDT", "SHIB/USDT"] 
        self.max_trade_amount_usdt = 15.0 # Emulating micro-transactions
        self.take_profit_pct = 0.5
        self.stop_loss_pct = 2.0
        self.rsi_threshold = 45.0
        self.candle_timeframe = "1m"

    def can_trade(self, symbol, current_price, spread):
        if symbol in self.blacklisted_symbols:
            return False, "Blacklisted"
        if spread / current_price > 0.005:
            return False, "Spread too wide"
        return True, "Passed"

class CryptoBotManager:
    def __init__(self, api_key: str = "", secret_key: str = "", testnet=True):
        self.is_testnet = testnet
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'warnOnFetchOpenOrdersWithoutSymbol': False
            }
        })
        if testnet:
            self.exchange.set_sandbox_mode(True)
            
        self.is_running = False
        self.risk_engine = RiskEngine()
        self.active_tasks = []
        self.logs = []
        self.trades = []
        self.threads = {}
        self.total_pnl_usdt = 0.0
        
        # SQLite Persistence Engine
        self.db_conn = sqlite3.connect('nova.db', check_same_thread=False)
        self.db_cursor = self.db_conn.cursor()
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS sys_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, msg TEXT)''')
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS ledger_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, symbol TEXT, amount REAL, price REAL, status TEXT)''')
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS sys_settings (key TEXT PRIMARY KEY, value TEXT)''')
        self.db_cursor.execute('''CREATE TABLE IF NOT EXISTS webauthn_credentials (id BLOB PRIMARY KEY, public_key BLOB, sign_count INTEGER)''')
        self.db_conn.commit()

        # Email Notification Configuration
        self.email_config = {
            "enabled": os.getenv("EMAIL_ENABLED", "False").lower() == "true",
            "smtp_server": os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
            "smtp_port": int(os.getenv("EMAIL_SMTP_PORT", "587")),
            "username": os.getenv("EMAIL_USERNAME", ""),
            "password": os.getenv("EMAIL_PASSWORD", ""),
            "recipient": os.getenv("EMAIL_RECIPIENT", "")
        }

    def _send_email_sync(self, subject, body):
        if not self.email_config.get("enabled"):
            return
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg['Subject'] = subject
            msg['From'] = self.email_config["username"]
            msg['To'] = self.email_config["recipient"]

            server = smtplib.SMTP(self.email_config["smtp_server"], self.email_config["smtp_port"])
            server.starttls()
            server.login(self.email_config["username"], self.email_config["password"])
            server.send_message(msg)
            server.quit()
            print(f"[EMAIL] Sent: {subject}")
        except Exception as e:
            print(f"[EMAIL] Failed to send email: {e}")

    async def send_email(self, subject, body):
        await asyncio.to_thread(self._send_email_sync, subject, body)

    def log(self, msg: str):
        print(f"[BOT] {msg}")
        self.db_cursor.execute("INSERT INTO sys_logs (msg) VALUES (?)", (msg,))
        self.db_conn.commit()
        
    def get_logs(self):
        self.db_cursor.execute("SELECT msg FROM sys_logs ORDER BY id DESC LIMIT 100")
        return [row[0] for row in reversed(self.db_cursor.fetchall())]
        
    def get_trades(self):
        self.db_cursor.execute("SELECT action, symbol, amount, price, status FROM ledger_trades ORDER BY id DESC LIMIT 50")
        rows = self.db_cursor.fetchall()
        return [{"action": r[0], "symbol": r[1], "amount": r[2], "price": r[3], "status": r[4]} for r in rows]

    def save_setting(self, key, value):
        self.db_cursor.execute("INSERT OR REPLACE INTO sys_settings (key, value) VALUES (?, ?)", (key, str(value)))
        self.db_conn.commit()

    async def hydrate_settings(self):
        self.db_cursor.execute("SELECT key, value FROM sys_settings")
        rows = self.db_cursor.fetchall()
        settings = {r[0]: r[1] for r in rows}
        
        if "tp" in settings: self.risk_engine.take_profit_pct = float(settings["tp"])
        if "sl" in settings: self.risk_engine.stop_loss_pct = float(settings["sl"])
        if "rsi" in settings: self.risk_engine.rsi_threshold = float(settings["rsi"])
        if "tf" in settings: self.risk_engine.candle_timeframe = settings["tf"]
        
        saved_api = settings.get("api_key", "")
        saved_secret = settings.get("secret_key", "")
        saved_testnet = settings.get("testnet", "true").lower() == "true"
        
        if saved_api and saved_secret:
            await self.apply_credentials(saved_api, saved_secret, saved_testnet)
        else:
            try:
                self.log("Connecting to exchange...")
                await self.exchange.load_markets()
                self.log(f"Markets loaded. Connected to: {self.exchange.urls['api']['public']}")
            except Exception as e:
                self.log(f"Failed to initialize: {e}")

    async def initialize(self):
        await self.hydrate_settings()

    async def apply_credentials(self, api_key: str, secret_key: str, is_testnet: bool):
        self.log(f"Switching credentials. Testnet Mode: {is_testnet}")
        was_running = self.is_running
        if self.is_running:
            await self.turn_off()
            await asyncio.sleep(0.5)
            
        try:
            await self.exchange.close()
        except Exception:
            pass
        
        self.is_testnet = is_testnet
        self.exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
                'warnOnFetchOpenOrdersWithoutSymbol': False
            }
        })
        if is_testnet:
            self.exchange.set_sandbox_mode(True)
        else:
            self.exchange.set_sandbox_mode(False)
            
        self.save_setting("api_key", api_key)
        self.save_setting("secret_key", secret_key)
        self.save_setting("testnet", str(is_testnet).lower())
        
        try:
            self.log("Connecting to exchange...")
            await self.exchange.load_markets()
            self.log(f"Markets loaded. Connected to: {self.exchange.urls['api']['public']}")
        except Exception as e:
            self.log(f"Failed to initialize: {e}")
            
        if was_running:
            await self.turn_on()

    async def turn_on(self):
        if self.is_running:
            return
            
        self.active_tasks.clear()
        self.threads.clear()
        
        self.is_running = True
        self.log("Master switch ON. Triggering autonomous trading operations.")
        # Start the Auto-Screener Hunter Engine
        self.active_tasks.append(asyncio.create_task(self.hunter_routine(str(uuid.uuid4())[:8])))
        
    async def turn_off(self):
        if not self.is_running:
            return
        self.is_running = False
        self.log("Master switch OFF. Emergency cancelling all routines.")
        for task in self.active_tasks:
            task.cancel()

    async def create_trade(self, action, symbol, amount, price):
        success = True
        
        if self.is_testnet:
            self.log(f"[SIMULATION] Proposing {action}: {amount:,.4f} {symbol} @ {price:,.2f}")
        else:
            try:
                if action == "BUY":
                    balance = await self.exchange.fetch_balance()
                    usdt_balance = balance.get('USDT', {}).get('free', 0)
                    required_usdt = amount * price
                    if usdt_balance < required_usdt:
                        self.log(f"[ERROR] INSUFFICIENT FUNDS: Wallet holds ${usdt_balance:,.2f}, Trade requires ${required_usdt:,.2f}")
                        success = False
                    else:
                        order = await self.exchange.create_limit_buy_order(symbol, amount, price)
                        self.log(f"LIVE BUY EXECUTED: Order ID {order.get('id')}")
                elif action == "SELL":
                    base_coin = symbol.split('/')[0]
                    balance = await self.exchange.fetch_balance()
                    coin_balance = balance.get(base_coin, {}).get('free', 0)
                    if coin_balance < amount:
                        self.log(f"[WARNING] INSUFFICIENT {base_coin}: Wallet holds {coin_balance}, Trade expects {amount}. Adjusting output to maximum possible...")
                        amount = coin_balance
                    
                    if amount > 0:
                        order = await self.exchange.create_limit_sell_order(symbol, amount, price)
                        self.log(f"LIVE SELL EXECUTED: Order ID {order.get('id')}")
                    else:
                        self.log(f"[ERROR] ZERO BALANCE: Cannot sell 0 {base_coin}.")
                        success = False
            except Exception as e:
                self.log(f"[ERROR] LIVE {action} REJECTED BY BINANCE API: {e}")
                success = False

        if success:
            status_val = "SIMULATION" if self.is_testnet else "LIVE"
            self.db_cursor.execute("INSERT INTO ledger_trades (action, symbol, amount, price, status) VALUES (?, ?, ?, ?, ?)", 
                                   (action, symbol, amount, price, status_val))
            self.db_conn.commit()
            
        return success

    async def get_open_orders(self):
        try:
            if self.is_testnet:
                return [] # Local paper environment shouldn't scan fake endpoints for global state 
            orders = await self.exchange.fetch_open_orders()
            # Return specific dicts payload back to the visual router so it can be JSON structured perfectly
            return [{"id": o["id"], "symbol": o["symbol"], "amount": o["amount"], "price": o["price"], "side": o["side"]} for o in orders]
        except Exception as e:
            self.log(f"Failed to pull active Binance orders: {e}")
            return []
            
    async def cancel_order(self, order_id: str, symbol: str):
        try:
            if self.is_testnet:
                return False, "Cannot execute payload kill in sandbox"
            res = await self.exchange.cancel_order(order_id, symbol)
            self.log(f"Successfully vaporized hovering limit {order_id} on {symbol}")
            return True, res
        except Exception as e:
            self.log(f"Failed terminating order {order_id}: {e}")
            return False, str(e)

    async def blacklist_coin(self, symbol):
        if symbol not in self.risk_engine.blacklisted_symbols:
            self.risk_engine.blacklisted_symbols.append(symbol)
            self.log(f"Added {symbol} to Blacklist.")
            
    async def unblacklist_coin(self, symbol):
        if symbol in self.risk_engine.blacklisted_symbols:
            self.risk_engine.blacklisted_symbols.remove(symbol)
            self.log(f"Removed {symbol} from Blacklist.")

    async def hunter_routine(self, thread_id: str):
        self.log(f"Started Hunter Screener {thread_id}")
        self.threads[thread_id] = {
            "id": thread_id,
            "symbol": "HUNTER-SRCH",
            "status": "Initializing Data Models",
            "pnl": 0.0,
            "cycles": 0
        }
        
        target_assets = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]
        
        try:
            while self.is_running:
                # Phase 1: Scanning Market
                self.threads[thread_id]["symbol"] = "HUNTER-SRCH"
                self.threads[thread_id]["status"] = "Scanning Top 6 Assets..."
                
                target_acquired = None
                target_price = 0.0
                
                for symbol in target_assets:
                    if not self.is_running: break
                    if symbol in self.risk_engine.blacklisted_symbols:
                        continue
                        
                    try:
                        self.threads[thread_id]["status"] = f"Assessing {symbol} RSI"
                        ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe=self.risk_engine.candle_timeframe, limit=50)
                        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        if df.empty or len(df) < 15:
                            continue
                            
                        # Calculate Math RSI using ta
                        rsi = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
                        latest_rsi = rsi.iloc[-1]
                        
                        if pd.isna(latest_rsi):
                             continue
                             
                        self.log(f"[HUNTER] {symbol} RSI: {latest_rsi:.2f}")
                        
                        # Trigger condition utilizing dynamic UI threshold
                        if latest_rsi < self.risk_engine.rsi_threshold:
                            target_acquired = symbol
                            target_price = df['close'].iloc[-1]
                            self.log(f"[HUNTER] MATCH ACQUIRED: {symbol} at {target_price} (RSI {latest_rsi:.2f})")
                            
                            # Send Email Alert
                            asyncio.create_task(self.send_email(
                                subject=f"Hunter Alert: {symbol} RSI Reached ({latest_rsi:.2f})",
                                body=f"Symbol: {symbol}\nPrice: {target_price}\nRSI: {latest_rsi:.2f}\nThreshold: {self.risk_engine.rsi_threshold}"
                            ))
                            break
                            
                    except Exception as e:
                        self.log(f"[HUNTER] API limit or error fetching {symbol} candlesticks: {e}")
                        await asyncio.sleep(2)
                        
                if not self.is_running: break
                
                if target_acquired is None:
                    self.threads[thread_id]["status"] = "Watching Market (No Dips)"
                    await asyncio.sleep(10)
                    continue
                    
                # Phase 2: Dynamic Execution
                symbol = target_acquired
                self.threads[thread_id]["symbol"] = symbol
                self.threads[thread_id]["status"] = "Pre-Trade Validation"
                
                # Dynamic Wallet Sizing
                if self.is_testnet:
                    trade_usdt = self.risk_engine.max_trade_amount_usdt
                else:
                    balance = await self.exchange.fetch_balance()
                    free_usdt = float(balance.get('USDT', {}).get('free', 0))
                    if free_usdt < 10.5:
                        self.threads[thread_id]["status"] = "BALANCE LOW < 10.5 USDT"
                        self.log(f"[{symbol}] Hunter halted: Wallet has {free_usdt:,.2f} USDT. Minimum 10.5 required.")
                        await asyncio.sleep(10)
                        continue
                    trade_usdt = free_usdt * 0.99 # Use 99% safely to bypass native Binance precision deductions
                
                amount_coin = trade_usdt / target_price
                    
                self.threads[thread_id]["status"] = "Executing Buy"
                buy_success = await self.create_trade("BUY", symbol, amount_coin, target_price)
                
                if not buy_success:
                    self.threads[thread_id]["status"] = "Trade Aborted"
                    self.log(f"[{symbol}] Transaction denied. Restarting Hunter scan.")
                    await asyncio.sleep(4)
                    continue
                    
                # Phase 3: Live Trailing Market
                self.threads[thread_id]["status"] = "Trailing Market"
                self.log(f"[{symbol}] Held position, engaging LIVE trailing exit target...")
                
                buy_price = target_price
                sell_price = target_price
                
                while self.is_running:
                        await asyncio.sleep(1.5) # Poll binance every 1.5s
                        
                        target_profit_price = buy_price * (1 + (self.risk_engine.take_profit_pct / 100))
                        stop_loss_price = buy_price * (1 - (self.risk_engine.stop_loss_pct / 100))
                        
                        live_ticker = await self.exchange.fetch_ticker(symbol)
                        live_price = live_ticker.get('last')
                        if live_price is None:
                            continue
                            
                        # Project dynamic data onto the frontend ledger UI
                        self.threads[thread_id]["live_price"] = live_price
                        self.threads[thread_id]["target_price"] = target_profit_price
                        self.threads[thread_id]["stop_loss_price"] = stop_loss_price
                        
                        if live_price >= target_profit_price:
                            self.threads[thread_id]["status"] = "Target Executed"
                            sell_price = live_price
                            
                            # Send Email Alert
                            asyncio.create_task(self.send_email(
                                subject=f"Hunter Alert: {symbol} Target Profit Reached",
                                body=f"Symbol: {symbol}\nBuy Price: {buy_price}\nSell Price: {sell_price}\nTarget Price: {target_profit_price}"
                            ))
                            break
                        elif live_price <= stop_loss_price:
                            self.threads[thread_id]["status"] = "Stop Loss Hit"
                            sell_price = live_price
                            self.log(f"[{symbol}] EMERGENCY DUMP! Stop loss hit at ${live_price:,.2f}")
                            break
                            
                if not self.is_running: 
                    self.log(f"[{symbol}] Halting detected! Forcing position closure...")

                # Phase 4: Execute exit order
                self.threads[thread_id]["status"] = "Executing Sell"
                sell_success = await self.create_trade("SELL", symbol, amount_coin, sell_price)
                
                # Cleanup UI vars back to null while empty searching
                self.threads[thread_id]["live_price"] = None
                self.threads[thread_id]["target_price"] = None
                self.threads[thread_id]["stop_loss_price"] = None
                
                if sell_success:
                    profit = (sell_price * amount_coin) - (buy_price * amount_coin)
                    self.total_pnl_usdt += profit
                    self.threads[thread_id]["pnl"] += profit
                    self.threads[thread_id]["cycles"] += 1
                    self.threads[thread_id]["status"] = "Cycle Complete"
                else:
                    self.threads[thread_id]["status"] = "SELL FAILED - MANUAL FIX REQUIRED"
                    self.log(f"[{symbol}] Critical sell failure! Position may remain open.")
                    await asyncio.sleep(10)
                
                self.log(f"[HUNTER] Cycle complete on {symbol}. Waiting 10s before next scan.")
                await asyncio.sleep(10)
                
        except asyncio.CancelledError:
            self.threads[thread_id]["status"] = "Hunter Terminated"
            self.log(f"Hunter worker {thread_id} terminated.")
        except Exception as e:
            self.log(f"Critical error in Hunter worker: {e}")

    async def close(self):
        await self.exchange.close()
