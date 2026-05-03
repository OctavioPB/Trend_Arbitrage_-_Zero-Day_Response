"""FastAPI application — REST endpoints + WebSocket /ws/heatmap."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth import decode_token
from api.db import close_pool
from api.middleware.rate_limit import RateLimitMiddleware
from api.routers import alerts, auth, history, mpi, performance, playbooks, segments, signals

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    close_pool()


app = FastAPI(
    title="Trend Arbitrage API",
    version="0.1.0",
    description="Real-time marketing intelligence — signals, MPI, and golden records.",
    lifespan=lifespan,
    openapi_url="/openapi.json",
)

app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(signals.router)
app.include_router(mpi.router)
app.include_router(segments.router)
app.include_router(alerts.router)
app.include_router(history.router)
app.include_router(playbooks.router)
app.include_router(performance.router)


# ── health ────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


# ── WebSocket /ws/heatmap ─────────────────────────────────────────────────────


@app.websocket("/ws/heatmap")
async def heatmap_ws(websocket: WebSocket, token: str | None = None) -> None:
    """Push MPI heat map grid to connected clients every 60 seconds.

    Requires a valid JWT passed as ?token=<jwt> query parameter.
    Close codes: 4001 = missing/invalid token, 4003 = insufficient scope.
    """
    # Authenticate before accepting the connection
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        payload = decode_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    if "read:signals" not in payload.get("scopes", []):
        await websocket.close(code=4003, reason="Insufficient scope")
        return

    await websocket.accept()
    logger.info(
        "WebSocket client connected to /ws/heatmap (sub=%s)", payload.get("sub")
    )

    try:
        while True:
            try:
                grid = await asyncio.to_thread(mpi.build_mpi_grid_dict, 60)
            except Exception as exc:
                logger.error("MPI grid computation failed: %s", exc)
                grid = {
                    "error": "Data temporarily unavailable",
                    "cells": [],
                    "topic_clusters": [],
                    "time_buckets": [],
                }
            await websocket.send_json(grid)
            await asyncio.sleep(60)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected from /ws/heatmap")
    except asyncio.CancelledError:
        logger.info("WebSocket task cancelled for /ws/heatmap")


# ── error handlers ────────────────────────────────────────────────────────────
# Prevent internal details (stack traces, DSN, API keys) from leaking to clients.


@app.exception_handler(Exception)
async def generic_exception_handler(request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled exception on %s: %s", request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )
