from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import asyncio
from bot_manager import CryptoBotManager
import json
import random
from fastapi import Request, Depends, HTTPException
from auth_manager import router as auth_router

app = FastAPI(title="Crypto Micro-Bot Auto-Trader")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(auth_router)

def check_auth(req: Request):
    if req.cookies.get("novabot_auth") != "authenticated":
        raise HTTPException(status_code=401, detail="Unauthorized")

bot = CryptoBotManager(testnet=True)

class BlacklistRequest(BaseModel):
    symbol: str
    
class SettingsRequest(BaseModel):
    apiKey: str
    secretKey: str
    isTestnet: bool

class PhysicsRequest(BaseModel):
    takeProfitPct: float
    stopLossPct: float
    rsiThreshold: float
    candleTimeframe: str

class CancelOrderRequest(BaseModel):
    orderId: str
    symbol: str

@app.on_event("startup")
async def startup_event():
    await bot.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    # Force emergency halt safely to prevent dangling tasks
    await bot.turn_off()
    # Wait for cancel payload to ripple through executing threads
    await asyncio.sleep(0.5)
    # Explicity close CCXT networking resources
    await bot.close()

@app.post("/api/settings", dependencies=[Depends(check_auth)])
async def update_settings(req: SettingsRequest):
    await bot.apply_credentials(req.apiKey, req.secretKey, req.isTestnet)
    return {"status": "reconnected"}

@app.post("/api/physics", dependencies=[Depends(check_auth)])
async def update_physics(req: PhysicsRequest):
    bot.risk_engine.take_profit_pct = req.takeProfitPct
    bot.risk_engine.stop_loss_pct = req.stopLossPct
    bot.risk_engine.rsi_threshold = req.rsiThreshold
    bot.risk_engine.candle_timeframe = req.candleTimeframe.strip()
    
    bot.save_setting("tp", req.takeProfitPct)
    bot.save_setting("sl", req.stopLossPct)
    bot.save_setting("rsi", req.rsiThreshold)
    bot.save_setting("tf", req.candleTimeframe.strip())
    
    bot.log(f"Updated HFT Physics: TP {req.takeProfitPct}% | SL {req.stopLossPct}% | RSI {req.rsiThreshold} | TF {req.candleTimeframe}")
    return {"status": "updated"}

@app.get("/api/orders", dependencies=[Depends(check_auth)])
async def get_orders():
    orders = await bot.get_open_orders()
    return {"orders": orders}

@app.post("/api/orders/cancel", dependencies=[Depends(check_auth)])
async def cancel_order(req: CancelOrderRequest):
    success, res = await bot.cancel_order(req.orderId, req.symbol)
    if success:
        return {"status": "success", "result": res}
    return {"status": "error", "message": res}

# API Endpoints
@app.get("/api/state", dependencies=[Depends(check_auth)])
async def get_state():
    # Utilizing SQLite bindings directly for safe hydration
    return {
        "status": "RUNNING" if bot.is_running else "IDLE",
        "total_pnl": bot.total_pnl_usdt,
        "logs": bot.get_logs(),
        "trades": bot.get_trades(),
        "threads": list(bot.threads.values()),
        "physics": {
            "takeProfitPct": bot.risk_engine.take_profit_pct,
            "stopLossPct": bot.risk_engine.stop_loss_pct,
            "rsiThreshold": bot.risk_engine.rsi_threshold,
            "candleTimeframe": bot.risk_engine.candle_timeframe
        },
        "blacklisted": bot.risk_engine.blacklisted_symbols
    }

@app.post("/api/start", dependencies=[Depends(check_auth)])
async def start_bot():
    await bot.turn_on()
    return {"status": "started"}

@app.post("/api/stop", dependencies=[Depends(check_auth)])
async def stop_bot():
    await bot.turn_off()
    return {"status": "stopped"}

@app.post("/api/blacklist/add", dependencies=[Depends(check_auth)])
async def add_blacklist(req: BlacklistRequest):
    await bot.blacklist_coin(req.symbol)
    return {"status": "added", "blacklisted": bot.risk_engine.blacklisted_symbols}

@app.post("/api/blacklist/remove", dependencies=[Depends(check_auth)])
async def remove_blacklist(req: BlacklistRequest):
    await bot.unblacklist_coin(req.symbol)
    return {"status": "removed", "blacklisted": bot.risk_engine.blacklisted_symbols}

# WebSockets for real-time dashboard data
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if websocket.cookies.get("novabot_auth") != "authenticated":
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            # Broadcast state every 1 second
            payload = {
                "is_running": bot.is_running,
                "total_pnl": bot.total_pnl_usdt,
                "logs": bot.get_logs(),
                "trades": bot.get_trades(),
                "blacklisted": bot.risk_engine.blacklisted_symbols,
                "threads": list(bot.threads.values())
            }
            await websocket.send_text(json.dumps(payload))
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
        
@app.get("/")
async def root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())
