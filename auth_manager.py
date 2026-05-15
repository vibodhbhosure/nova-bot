import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from webauthn import generate_registration_options, verify_registration_response, generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import RegistrationCredential, AuthenticationCredential, PublicKeyCredentialDescriptor
from webauthn.helpers import base64url_to_bytes
import sqlite3
import hashlib
import secrets
import json

router = APIRouter()
RP_NAME = "NovaBot Secure Terminal"
USER_ID = b"admin_user_id_12345"

db = sqlite3.connect('nova.db', check_same_thread=False)
cursor = db.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS webauthn_credentials (id BLOB PRIMARY KEY, public_key BLOB, sign_count INTEGER)")
cursor.execute("CREATE TABLE IF NOT EXISTS master_auth (id INTEGER PRIMARY KEY, password_hash TEXT, salt TEXT)")
db.commit()

# Simple in-memory session for the challenge
current_challenge = ""

class RegisterResponse(BaseModel):
    response: dict

@router.get("/api/auth/register/generate")
async def register_generate(req: Request):
    global current_challenge
    
    cursor.execute("SELECT COUNT(*) FROM webauthn_credentials")
    if cursor.fetchone()[0] > 0:
        raise HTTPException(status_code=403, detail="Passkey already registered.")

    # Generate options
    options = generate_registration_options(
        rp_id=req.url.hostname,
        rp_name=RP_NAME,
        user_id=USER_ID,
        user_name="admin",
    )
    current_challenge = options.challenge
    return json.loads(options_to_json(options))

@router.post("/api/auth/register/verify_passkey")
async def register_verify_passkey(req: Request):
    global current_challenge
    
    cursor.execute("SELECT COUNT(*) FROM webauthn_credentials")
    if cursor.fetchone()[0] > 0:
        raise HTTPException(status_code=403, detail="Passkey already registered.")

    body = await req.json()
    try:
        origin = f"http://localhost:8000" if req.url.hostname == "localhost" else f"https://{req.url.hostname}"
        verification = verify_registration_response(
            credential=body,
            expected_challenge=current_challenge,
            expected_origin=origin,
            expected_rp_id=req.url.hostname,
        )
        
        # Save credential
        cursor.execute("INSERT OR REPLACE INTO webauthn_credentials (id, public_key, sign_count) VALUES (?, ?, ?)",
            (verification.credential_id, verification.credential_public_key, verification.sign_count))
        db.commit()
        cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
            ("AUTH", "PASSKEY_REGISTERED", "New passkey device registered", "SUCCESS"))
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
            ("AUTH", "PASSKEY_REGISTER_FAILED", str(e), "DANGER"))
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/auth/register/verify_password")
async def register_password(req: Request):
    cursor.execute("SELECT COUNT(*) FROM master_auth")
    if cursor.fetchone()[0] > 0:
        raise HTTPException(status_code=403, detail="Password already set.")
    
    data = await req.json()
    password = data.get("password")
    if not password:
        raise HTTPException(status_code=400, detail="Password required")
        
    salt = secrets.token_hex(16)
    password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    
    cursor.execute("INSERT INTO master_auth (password_hash, salt) VALUES (?, ?)", (password_hash, salt))
    db.commit()
    cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
        ("AUTH", "MASTER_PASSWORD_SET", "Master password configured", "SUCCESS"))
    db.commit()
    return {"status": "ok"}

@router.get("/api/auth/login/generate")
async def login_generate(req: Request):
    global current_challenge
    cursor.execute("SELECT id FROM webauthn_credentials")
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail="No passkey registered.")
        
    options = generate_authentication_options(
        rp_id=req.url.hostname,
        allow_credentials=[PublicKeyCredentialDescriptor(id=r[0]) for r in rows]
    )
    current_challenge = options.challenge
    return json.loads(options_to_json(options))

@router.post("/api/auth/login/verify_passkey")
async def login_verify_passkey(req: Request, response: Response):
    global current_challenge
    body = await req.json()
    
    cred_id = body.get("id")
    if not cred_id:
        raise HTTPException(status_code=400, detail="Invalid credential format")
        
    try:
        raw_id = base64url_to_bytes(cred_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid credential ID encoding")
        
    cursor.execute("SELECT public_key, sign_count FROM webauthn_credentials WHERE id=?", (raw_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Credential not found")
        
    try:
        origin = f"http://localhost:8000" if req.url.hostname == "localhost" else f"https://{req.url.hostname}"
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=current_challenge,
            expected_origin=origin,
            expected_rp_id=req.url.hostname,
            credential_public_key=row[0],
            credential_current_sign_count=row[1]
        )
        
        cursor.execute("UPDATE webauthn_credentials SET sign_count=? WHERE id=?", (verification.new_sign_count, raw_id))
        db.commit()
        
        # Set authenticated cookie
        response.set_cookie(key="novabot_auth", value="authenticated", max_age=86400*30)
        cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
            ("AUTH", "PASSKEY_LOGIN_SUCCESS", "Authenticated via passkey", "SUCCESS"))
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
            ("AUTH", "PASSKEY_LOGIN_FAILED", str(e), "DANGER"))
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/api/auth/login/verify_password")
async def login_verify_password(req: Request, response: Response):
    data = await req.json()
    password = data.get("password")
    
    cursor.execute("SELECT password_hash, salt FROM master_auth")
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="No password configured")
        
    password_hash, salt = row
    if hashlib.sha256((password + salt).encode()).hexdigest() == password_hash:
        response.set_cookie(key="novabot_auth", value="authenticated", max_age=86400*30)
        cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
            ("AUTH", "PASSWORD_LOGIN_SUCCESS", "Authenticated via master password", "SUCCESS"))
        db.commit()
        return {"status": "ok"}
    cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
        ("AUTH", "PASSWORD_LOGIN_FAILED", "Invalid master password attempt", "DANGER"))
    db.commit()
    raise HTTPException(status_code=401, detail="Invalid password")

@router.get("/api/auth/status")
async def auth_status(req: Request):
    is_authenticated = req.cookies.get("novabot_auth") == "authenticated"
    cursor.execute("SELECT COUNT(*) FROM master_auth")
    has_password = cursor.fetchone()[0] > 0
    cursor.execute("SELECT COUNT(*) FROM webauthn_credentials")
    has_passkey = cursor.fetchone()[0] > 0
    return {"authenticated": is_authenticated, "has_passkey": has_passkey, "has_password": has_password}

@router.post("/api/auth/logout")
async def logout(response: Response):
    response.delete_cookie("novabot_auth")
    cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
        ("AUTH", "LOGOUT", "User logged out", "INFO"))
    db.commit()
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
            f"Your OTP to reset the master auth is: {otp}\nIf you did not request this, please ignore this email."
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
    cursor.execute("DELETE FROM webauthn_credentials")
    db.commit()
    cursor.execute("INSERT INTO audit_log (category, action, detail, severity) VALUES (?, ?, ?, ?)",
        ("AUTH", "CREDENTIALS_RESET", "All passkeys and master password wiped via OTP", "DANGER"))
    db.commit()
    
    del reset_otp_store['current']
    return {"status": "ok"}
