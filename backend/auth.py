import os
import time
import logging
from typing import Optional, Dict, Any
import httpx
from fastapi import Header, HTTPException, Depends

try:
    from backend.config import SUPABASE_URL, SUPABASE_KEY
except ImportError:
    from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger("auth")

# In-memory cache for validated tokens: token -> (user_dict, expires_at_timestamp)
_TOKEN_CACHE: Dict[str, tuple[Dict[str, Any], float]] = {}
CACHE_TTL_SECONDS = 120  # Cache token verification for 2 minutes


async def verify_supabase_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a Supabase JWT token by querying the Supabase Auth API (/auth/v1/user).
    Includes in-memory TTL caching to guarantee near-instant responses.
    """
    if not token or not SUPABASE_URL or not SUPABASE_KEY:
        return None

    # Check cache first
    now = time.time()
    if token in _TOKEN_CACHE:
        cached_user, expiry = _TOKEN_CACHE[token]
        if now < expiry:
            return cached_user
        else:
            del _TOKEN_CACHE[token]

    # Verify directly with Supabase Auth endpoint
    auth_url = f"{SUPABASE_URL.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {token}"
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(auth_url, headers=headers)
            if resp.status_code == 200:
                user_data = resp.json()
                user_info = {
                    "id": user_data.get("id"),
                    "email": user_data.get("email"),
                    "role": user_data.get("role", "authenticated"),
                    "user_metadata": user_data.get("user_metadata", {}),
                    "created_at": user_data.get("created_at"),
                    "token": token
                }
                _TOKEN_CACHE[token] = (user_info, now + CACHE_TTL_SECONDS)
                return user_info
            else:
                logger.warning(f"Supabase auth check failed with status {resp.status_code}: {resp.text}")
                return None
    except Exception as e:
        logger.error(f"Error connecting to Supabase Auth endpoint: {e}")
        return None


async def get_current_user(authorization: Optional[str] = Header(None)) -> Optional[Dict[str, Any]]:
    """
    Optional dependency: extracts and verifies the Bearer token if present.
    Returns None if no Authorization header is provided.
    """
    if not authorization:
        return None

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    return await verify_supabase_token(token)


async def require_current_user(user: Optional[Dict[str, Any]] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Strict dependency: requires an authenticated user.
    Raises HTTP 401 if token is absent or invalid.
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please sign in to ProfFeb."
        )
    return user
