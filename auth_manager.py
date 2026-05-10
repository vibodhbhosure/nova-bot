import os
from fastapi import APIRouter, HTTPException, Response, Request
from pydantic import BaseModel
from webauthn import generate_registration_options, verify_registration_response, generate_authentication_options, verify_authentication_response, options_to_json
from webauthn.helpers.structs import RegistrationCredential, AuthenticationCredential, PublicKeyCredentialDescriptor
from webauthn.helpers import base64url_to_bytes
import sqlite3
import json

router = APIRouter()
RP_NAME = "NovaBot Secure Terminal"
USER_ID = b"admin_user_id_12345"

db = sqlite3.connect('nova.db', check_same_thread=False)
cursor = db.cursor()

# Simple in-memory session for the challenge
current_challenge = ""

class RegisterResponse(BaseModel):
    response: dict

@router.get("/api/auth/register/generate")
async def register_generate(req: Request):
    global current_challenge
    # Generate options
    options = generate_registration_options(
        rp_id=req.url.hostname,
        rp_name=RP_NAME,
        user_id=USER_ID,
        user_name="admin",
    )
    current_challenge = options.challenge
    return json.loads(options_to_json(options))

@router.post("/api/auth/register/verify")
async def register_verify(req: Request):
    global current_challenge
    body = await req.json()
    try:
        verification = verify_registration_response(
            credential=body,
            expected_challenge=current_challenge,
            expected_origin=f"http://{req.url.hostname}:8000",
            expected_rp_id=req.url.hostname,
        )
        
        # Save credential
        cursor.execute("INSERT OR REPLACE INTO webauthn_credentials (id, public_key, sign_count) VALUES (?, ?, ?)",
            (verification.credential_id, verification.credential_public_key, verification.sign_count))
        db.commit()
        
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/auth/login/generate")
async def login_generate(req: Request):
    global current_challenge
    cursor.execute("SELECT id FROM webauthn_credentials")
    rows = cursor.fetchall()
    if not rows:
        raise HTTPException(status_code=400, detail="No credentials registered.")
        
    options = generate_authentication_options(
        rp_id=req.url.hostname,
        allow_credentials=[PublicKeyCredentialDescriptor(id=r[0]) for r in rows]
    )
    current_challenge = options.challenge
    return json.loads(options_to_json(options))

@router.post("/api/auth/login/verify")
async def login_verify(req: Request, response: Response):
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
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=current_challenge,
            expected_origin=f"http://{req.url.hostname}:8000",
            expected_rp_id=req.url.hostname,
            credential_public_key=row[0],
            credential_current_sign_count=row[1]
        )
        
        cursor.execute("UPDATE webauthn_credentials SET sign_count=? WHERE id=?", (verification.new_sign_count, raw_id))
        db.commit()
        
        # Set authenticated cookie
        response.set_cookie(key="novabot_auth", value="authenticated", max_age=86400*30)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/api/auth/status")
async def auth_status(req: Request):
    if req.cookies.get("novabot_auth") == "authenticated":
        return {"authenticated": True}
    
    cursor.execute("SELECT COUNT(*) FROM webauthn_credentials")
    count = cursor.fetchone()[0]
    return {"authenticated": False, "has_passkey": count > 0}
