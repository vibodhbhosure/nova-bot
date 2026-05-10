import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
import sqlite3
import hashlib
import secrets

router = APIRouter()

db = sqlite3.connect('nova.db', check_same_thread=False)
cursor = db.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS master_auth (id INTEGER PRIMARY KEY, password_hash TEXT, salt TEXT)")
db.commit()

class SetupRequest(BaseModel):
    password: str

class LoginRequest(BaseModel):
    password: str

def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

@router.get("/api/auth/status")
async def auth_status(req: Request):
    is_authenticated = req.cookies.get("novabot_auth") == "authenticated"
    cursor.execute("SELECT COUNT(*) FROM master_auth")
    has_password = cursor.fetchone()[0] > 0
    return {"authenticated": is_authenticated, "has_passkey": has_password}

@router.post("/api/auth/register/verify")
async def register_password(req: SetupRequest):
    cursor.execute("SELECT COUNT(*) FROM master_auth")
    if cursor.fetchone()[0] > 0:
        raise HTTPException(status_code=403, detail="Master password already set.")
    
    salt = secrets.token_hex(16)
    p_hash = hash_password(req.password, salt)
    
    cursor.execute("INSERT INTO master_auth (password_hash, salt) VALUES (?, ?)", (p_hash, salt))
    db.commit()
    return {"status": "ok"}

@router.post("/api/auth/login/verify")
async def login_password(req: LoginRequest, response: Response):
    cursor.execute("SELECT password_hash, salt FROM master_auth LIMIT 1")
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="No master password set.")
        
    p_hash, salt = row
    if hash_password(req.password, salt) != p_hash:
        raise HTTPException(status_code=401, detail="Incorrect password.")
        
    response.set_cookie(key="novabot_auth", value="authenticated", max_age=86400*30)
    return {"status": "ok"}

reset_otp_store = {}

@router.post("/api/auth/reset/request")
async def request_device_reset():
    import random
    from main import bot
    otp = str(random.randint(100000, 999999))
    reset_otp_store['current'] = otp
    try:
        await bot.send_email(
            "NovaBot Master Reset OTP", 
            f"Your OTP to reset the master password is: {otp}\nIf you did not request this, please ignore this email."
        )
        return {"status": "ok"}
    except Exception as e:
        bot.log(f"Failed to send reset OTP: {e}")
        raise HTTPException(status_code=500, detail="Failed to send OTP via email. Check server logs.")

class OTPVerifyRequest(BaseModel):
    otp: str

@router.post("/api/auth/reset/verify")
async def verify_device_reset(req: OTPVerifyRequest):
    if 'current' not in reset_otp_store or reset_otp_store['current'] != req.otp.strip():
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    cursor.execute("DELETE FROM master_auth")
    db.commit()
    
    del reset_otp_store['current']
    return {"status": "ok"}

@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("novabot_auth")
    return {"status": "ok"}
