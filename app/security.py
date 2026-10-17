import os
import hmac
import hashlib
import secrets
import json
import base64
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

# Secure secret key loaded strictly from environment variable or generated per process at runtime
ADMIN_JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET")
if not ADMIN_JWT_SECRET:
    ADMIN_JWT_SECRET = secrets.token_urlsafe(32)

ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("ADMIN_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours default


def hash_password(password: str) -> str:
    """
    Hashes a password using PBKDF2-HMAC-SHA256 with 600,000 iterations (OWASP recommendation).
    Returns string formatted as: pbkdf2_sha256$iterations$salt_hex$hash_hex
    """
    if not password:
        raise ValueError("Password cannot be empty")
    iterations = 600_000
    salt = secrets.token_bytes(16)
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${hash_bytes.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifies a plain password against its stored PBKDF2 hash using constant-time comparison.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        parts = hashed_password.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = bytes.fromhex(parts[2])
        expected_hash = parts[3]
        calculated_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations).hex()
        return hmac.compare_digest(calculated_hash, expected_hash)
    except Exception:
        return False


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _base64url_decode(s: str) -> bytes:
    padding = 4 - (len(s) % 4)
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates an HMAC-SHA256 cryptographically signed URL-safe JWT-compatible session token.
    """
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "iss": "ravi-genai-admin-auth"
    })
    
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(to_encode, separators=(",", ":")).encode("utf-8"))
    
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(ADMIN_JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
    sig_b64 = _base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{sig_b64}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and verifies an HMAC-SHA256 signed access token.
    Returns payload dictionary if valid, None if invalid or expired.
    """
    if not token or not isinstance(token, str):
        return None
    
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None
    
    header_b64, payload_b64, sig_b64 = parts
    try:
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(ADMIN_JWT_SECRET.encode("utf-8"), signing_input, hashlib.sha256).digest()
        provided_sig = _base64url_decode(sig_b64)
        
        if not hmac.compare_digest(expected_sig, provided_sig):
            return None
        
        payload_json = _base64url_decode(payload_b64).decode("utf-8")
        payload = json.loads(payload_json)
        
        # Expiration check
        exp = payload.get("exp")
        if exp and datetime.utcnow().timestamp() > exp:
            return None
        
        return payload
    except Exception:
        return None
