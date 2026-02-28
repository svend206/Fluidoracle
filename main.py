from __future__ import annotations
"""
Fluidoracle — FastAPI Backend
==============================
Main application entry point. Defines app, lifespan, CORS, and includes
route modules. All route handlers live in core/routes/.
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, PlainTextResponse

from core.vertical_loader import load_platform

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")

PLATFORM_ID = os.getenv("PLATFORM_ID", "fps")

logger = logging.getLogger(f"fluidoracle-{PLATFORM_ID}")

# Database setup
import core.database as database

DATABASE_PATH = os.getenv("DATABASE_PATH", str(PROJECT_ROOT / "data" / "community.db"))
database.set_db_path(DATABASE_PATH)


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    print(f"Database initialized at: {DATABASE_PATH}")

    # Load platform and vertical config
    platform = load_platform(PLATFORM_ID)
    print(f"[startup] Platform: {platform.display_name} ({PLATFORM_ID})")
    print(f"[startup] Verticals: {list(platform.verticals.keys())}")

    # Initialize consultation and answer engines with the default vertical
    if platform.verticals:
        default_vertical_id = list(platform.verticals.keys())[0]
        default_vc = platform.verticals[default_vertical_id]

        import core.consultation_engine as ce
        import core.answer_engine as ae
        ce.init_vertical(default_vc)
        ae.init_vertical(default_vc)
        print(f"[startup] Default vertical: {default_vc.display_name} ({default_vertical_id})")

        # Pre-warm the RAG pipeline
        try:
            from core.retrieval.hybrid_search import search as _warmup_search
            warmup_query = default_vc.warmup_query or "test query"
            print("[startup] Pre-warming RAG pipeline (BM25 + cross-encoder + ChromaDB)...")
            _warmup_search(warmup_query, top_k=1, use_reranker=True)
            print("[startup] RAG pipeline warm.")
        except Exception as e:
            print(f"[startup] WARNING: RAG warmup failed: {e} — first request will be slow.")

    yield
    # Shutdown (nothing to clean up)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_platform_config = load_platform(PLATFORM_ID)

app = FastAPI(
    title=f"{_platform_config.display_name} — Fluidoracle",
    description=f"AI-powered engineering consultation for {_platform_config.display_name}",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health check (inline — too small for its own module)
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": f"{PLATFORM_ID}-platform", "platform": PLATFORM_ID}


@app.get("/api/config")
async def platform_config():
    """Return platform and vertical configuration for the frontend."""
    platform = load_platform(PLATFORM_ID)
    return {
        "platform_id": platform.platform_id,
        "platform_name": platform.display_name,
        "verticals": {
            vid: {
                "display_name": vc.display_name,
                "short_name": vc.short_name,
                "description": vc.description,
                "example_questions": vc.example_questions,
            }
            for vid, vc in platform.verticals.items()
        },
    }


# ---------------------------------------------------------------------------
# Include route modules
# ---------------------------------------------------------------------------

from core.routes.questions import router as questions_router
from core.routes.consultation import router as consultation_router
from core.routes.auth import router as auth_router
from core.routes.invention import router as invention_router
from core.routes.admin import router as admin_router

app.include_router(questions_router, tags=["Questions"])
app.include_router(consultation_router, tags=["Consultation"])
app.include_router(auth_router, tags=["Auth"])
app.include_router(invention_router, tags=["Invention"])
app.include_router(admin_router, tags=["Admin"])


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------

ROBOTS_TXT = """\
# AI training crawlers — blocked entirely
User-agent: GPTBot
Disallow: /

User-agent: ChatGPT-User
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: Google-Extended
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: Claude-Web
Disallow: /

User-agent: FacebookBot
Disallow: /api/

# All other crawlers — allow landing page, block app routes
User-agent: *
Allow: /$
Disallow: /api/
Disallow: /consult
Disallow: /ask
Disallow: /browse
Disallow: /invent
Disallow: /settings
"""


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt():
    return ROBOTS_TXT


# ---------------------------------------------------------------------------
# Static file serving (production — serves built frontend)
# ---------------------------------------------------------------------------

_frontend_dist = PROJECT_ROOT / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(_frontend_dist / "assets")), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Catch-all: serve the React app's index.html for client-side routing."""
        index = _frontend_dist / "index.html"
        if index.exists():
            return FileResponse(str(index))
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Frontend not built")
