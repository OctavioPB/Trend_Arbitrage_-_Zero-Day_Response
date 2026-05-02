"""Auth router — token issuance and API key lifecycle management.

POST /auth/token      — OAuth2 password grant; returns JWT Bearer token
GET  /auth/keys       — list API keys for the authenticated owner
POST /auth/keys       — generate a new scoped API key (plain key shown once)
DELETE /auth/keys/{id} — revoke an API key

All key management endpoints require a valid JWT Bearer token.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import psycopg2.extras
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from api.auth import (
    ADMIN_PASSWORD,
    ADMIN_USER,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    SCOPES,
    _KEY_PREFIX_LEN,
    create_access_token,
    generate_api_key,
    require_scope,
)
from api.db import get_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_VALID_SCOPES = set(SCOPES.keys())


# ── Models ────────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ApiKeyCreate(BaseModel):
    owner: str
    scopes: list[str]
    expires_days: int | None = None


class ApiKeyResponse(BaseModel):
    id: str
    key_prefix: str
    owner: str
    scopes: list[str]
    created_at: str
    expires_at: str | None
    last_used_at: str | None
    revoked: bool


class ApiKeyCreated(ApiKeyResponse):
    plain_key: str  # returned ONCE at creation — not stored, not retrievable again


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/token", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Exchange admin credentials for a short-lived JWT access token."""
    if not ADMIN_PASSWORD:
        raise HTTPException(
            status_code=503,
            detail="API_ADMIN_PASSWORD is not configured on this server",
        )
    if form_data.username != ADMIN_USER or form_data.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(
        subject=form_data.username,
        scopes=list(SCOPES.keys()),
    )
    logger.info("Token issued for user=%r", form_data.username)
    return TokenResponse(
        access_token=token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.get("/keys", response_model=list[ApiKeyResponse])
def list_api_keys(
    _subject: str = Depends(require_scope("write:alerts")),
) -> list[ApiKeyResponse]:
    """List all non-revoked API keys."""
    sql = """
        SELECT id::text, key_prefix, owner, scopes, created_at,
               expires_at, last_used_at, revoked
        FROM api_keys
        ORDER BY created_at DESC
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]

    return [_row_to_response(r) for r in rows]


@router.post("/keys", response_model=ApiKeyCreated, status_code=201)
def create_api_key(
    body: ApiKeyCreate,
    _subject: str = Depends(require_scope("write:alerts")),
) -> ApiKeyCreated:
    """Generate a new scoped API key. The plain key is shown once and never stored."""
    invalid = [s for s in body.scopes if s not in _VALID_SCOPES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid scopes: {invalid}. Valid: {sorted(_VALID_SCOPES)}",
        )
    if not body.scopes:
        raise HTTPException(status_code=422, detail="At least one scope is required")

    plain_key, key_hash = generate_api_key()
    key_prefix = plain_key[:_KEY_PREFIX_LEN]

    expires_at = None
    if body.expires_days is not None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=body.expires_days)

    sql = """
        INSERT INTO api_keys (key_prefix, key_hash, owner, scopes, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id::text, key_prefix, owner, scopes, created_at,
                  expires_at, last_used_at, revoked
    """
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                sql,
                (key_prefix, key_hash, body.owner, body.scopes, expires_at),
            )
            row = dict(cur.fetchone())
        conn.commit()

    logger.info(
        "API key created: owner=%r scopes=%s prefix=%s",
        body.owner,
        body.scopes,
        key_prefix,
    )
    resp = _row_to_response(row)
    return ApiKeyCreated(**resp.model_dump(), plain_key=plain_key)


@router.delete("/keys/{key_id}", status_code=204)
def revoke_api_key(
    key_id: str,
    _subject: str = Depends(require_scope("write:alerts")),
) -> None:
    """Revoke an API key by ID. Revoked keys return 401 on all subsequent requests."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE api_keys SET revoked = true WHERE id = %s::uuid RETURNING id",
                (key_id,),
            )
            found = cur.fetchone() is not None
        conn.commit()

    if not found:
        raise HTTPException(status_code=404, detail="API key not found")

    logger.info("API key revoked: id=%s", key_id)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _row_to_response(row: dict) -> ApiKeyResponse:
    def _iso(v) -> str | None:
        if v is None:
            return None
        return v.isoformat() if isinstance(v, datetime) else str(v)

    return ApiKeyResponse(
        id=row["id"],
        key_prefix=row["key_prefix"],
        owner=row["owner"],
        scopes=list(row["scopes"] or []),
        created_at=_iso(row["created_at"]) or "",
        expires_at=_iso(row.get("expires_at")),
        last_used_at=_iso(row.get("last_used_at")),
        revoked=bool(row["revoked"]),
    )
