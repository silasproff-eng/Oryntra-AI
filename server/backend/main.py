import sqlite3
import json
import os
import re
from html import escape
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .database import init_db, get_app_counter
from .market_cache import start_market_cache_worker, status as market_cache_status
from .routes import analysis, watchlist, paper_trading, ai_explain, backtest, patterns, auth, dev_tools, pro, intelligence

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
LEGAL_DIR = os.path.join(FRONTEND_DIR, "legal")

APP_VERSION = "0.9.1-market-intelligence"
PUBLIC_ENGINE = "official"
PUBLIC_ENGINE_LABEL = "V7 Official Momentum with server-side derived analysis"

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

AD_PLACEMENTS = [
    {"key": "home_top", "label": "Home top banner", "web_format": "horizontal", "flutter_format": "banner"},
    {"key": "scanner_top", "label": "Scanner top banner", "web_format": "horizontal", "flutter_format": "banner"},
    {"key": "results_side", "label": "Desktop result rectangle", "web_format": "rectangle", "flutter_format": "medium_rectangle"},
    {"key": "results_inline", "label": "Inline result banner", "web_format": "horizontal", "flutter_format": "banner"},
    {"key": "watchlist_inline", "label": "Watchlist banner", "web_format": "horizontal", "flutter_format": "banner"},
    {"key": "paper_bottom", "label": "Paper trading footer banner", "web_format": "horizontal", "flutter_format": "banner"},
    {"key": "mobile_bottom", "label": "Mobile bottom banner", "web_format": "mobile_anchor", "flutter_format": "anchored_adaptive_banner"},
]

def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

def ad_slot_env(prefix: str) -> dict:
    return {item["key"]: os.getenv(f"{prefix}_{item['key'].upper()}", "").strip() for item in AD_PLACEMENTS}

DEFAULT_ADSENSE_CLIENT_ID = "ca-pub-7922098561896578"

def adsense_client_id() -> str:
    raw = os.getenv("ADSENSE_CLIENT_ID", DEFAULT_ADSENSE_CLIENT_ID).strip()
    if re.fullmatch(r"ca-pub-\d{16}", raw):
        return raw
    return DEFAULT_ADSENSE_CLIENT_ID

def adsense_publisher_id() -> str:
    raw = os.getenv("ADSENSE_PUBLISHER_ID", "").strip()
    if re.fullmatch(r"pub-\d{16}", raw):
        return raw
    client = adsense_client_id()
    return client.removeprefix("ca-") if client else ""

def public_site_url() -> str:
    return os.getenv("ADSENSE_SITE_URL", os.getenv("PUBLIC_BASE_URL", "")).strip().rstrip("/")

def adsense_head_markup() -> str:
    client = adsense_client_id()
    if not env_bool("ADSENSE_VERIFY_ENABLED", True):
        return ""
    meta = f'<meta name="google-adsense-account" content="{escape(client)}">'
    script = (
        '<script async src="https://pagead2.googlesyndication.com/pagead/js/'
        f'adsbygoogle.js?client={escape(client)}" crossorigin="anonymous"></script>'
    )
    return meta + "\n  " + script

def inject_adsense_head(html: str) -> str:
    markup = adsense_head_markup()
    if not markup or "pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=" in html:
        return html
    if "<!-- ADSENSE_HEAD -->" in html:
        return html.replace("<!-- ADSENSE_HEAD -->", markup, 1)
    return html.replace("</head>", f"  {markup}\n</head>", 1)

def ads_diagnostics() -> dict:
    client = adsense_client_id()
    publisher = adsense_publisher_id()
    slots = ad_slot_env("ADSENSE_SLOT")
    configured = [key for key, value in slots.items() if value]
    missing = [key for key, value in slots.items() if not value]
    preview = env_bool("ADS_PREVIEW_MODE", True)
    web_enabled = env_bool("WEB_ADS_ENABLED", False)
    return {
        "site_url": public_site_url(),
        "client_id_valid": bool(client),
        "publisher_id_valid": bool(publisher),
        "verification_enabled": env_bool("ADSENSE_VERIFY_ENABLED", True),
        "verification_ready": bool(client and env_bool("ADSENSE_VERIFY_ENABLED", True)),
        "preview_mode": preview,
        "web_ads_enabled": web_enabled,
        "auto_ads_enabled": env_bool("ADSENSE_AUTO_ADS_ENABLED", False),
        "configured_slots": configured,
        "missing_slots": missing,
        "manual_ads_ready": bool(client and web_enabled and not preview and configured),
        "ads_txt_ready": bool(publisher),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    print("✅ Oryntra DB initialized")
    market_worker = start_market_cache_worker() if env_bool("ORYNTRA_PRIVATE_RESEARCH_ROUTES", False) else None
    try:
        yield
    finally:
        if market_worker is not None:
            market_worker.stop()
        print("🔴 Oryntra shutting down")


_private_research = env_bool("ORYNTRA_PRIVATE_RESEARCH_ROUTES", False)
_public_scanner_website = env_bool(
    "ORYNTRA_PUBLIC_SCANNER_WEBSITE",
    _private_research,
)

app = FastAPI(
    title="Oryntra AI API",
    description="Oryntra derived market-intelligence API with a strict raw-data boundary",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if _private_research else None,
    redoc_url="/redoc" if _private_research else None,
    openapi_url="/openapi.json" if _private_research else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("ORYNTRA_CORS_ORIGINS", "*").split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Oryntra-Session"],
)

app.add_middleware(
    GZipMiddleware,
    minimum_size=1000,
    compresslevel=5,
)


@app.middleware("http")
async def oryntra_release_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Oryntra-Version"] = APP_VERSION
    response.headers["X-Oryntra-Public-Engine"] = PUBLIC_ENGINE
    if (
        request.url.path == "/"
        or request.url.path.startswith("/static/")
        or request.url.path.startswith("/legal/")
    ):
        response.headers.update(NO_CACHE_HEADERS)
    return response

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(intelligence.router, prefix="/api/intelligence", tags=["Market Intelligence"])
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["Watchlist"])
app.include_router(paper_trading.router, prefix="/api/paper", tags=["Paper Trading"])
app.include_router(ai_explain.router, prefix="/api/ai", tags=["AI Explanation"])


if _private_research:
    app.include_router(analysis.router, prefix="/api/analysis", tags=["Private Analysis"])
    app.include_router(backtest.router, prefix="/api/backtest", tags=["Private Backtesting"])
    app.include_router(patterns.router, prefix="/api/patterns", tags=["Private Patterns"])
    app.include_router(dev_tools.router, prefix="/api/dev", tags=["Private Developer Tools"])
    app.include_router(pro.router, prefix="/api/pro", tags=["Private Oryntra Pro"])

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(FRONTEND_DIR, "static")),
    name="static",
)


@app.get("/", include_in_schema=False)
async def serve_frontend():
    if not _public_scanner_website:
        return JSONResponse(
            {
                "service": "oryntra-ai-api",
                "status": "online",
                "version": APP_VERSION,
                "market_data": "server-side analysis; public raw market data disabled",
                "public_scanner_website": "offline",
            },
            headers=NO_CACHE_HEADERS,
        )
    path = os.path.join(FRONTEND_DIR, "index.html")
    with open(path, "r", encoding="utf-8") as handle:
        html = inject_adsense_head(handle.read())
    return HTMLResponse(html, headers=NO_CACHE_HEADERS)


@app.get("/legal/{page_name}", include_in_schema=False)
async def serve_legal_page(page_name: str):
    legal_pages = {
        "terms": "terms.html",
        "privacy": "privacy.html",
        "refund": "refund.html",
        "risk-disclaimer": "risk-disclaimer.html",
        "contact": "contact.html",
        "methodology": "methodology.html",
    }
    filename = legal_pages.get(page_name)
    if not filename:
        raise HTTPException(status_code=404, detail="Legal page not found")
    path = os.path.join(LEGAL_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Legal page not found")
    with open(path, "r", encoding="utf-8") as handle:
        html = inject_adsense_head(handle.read())
    return HTMLResponse(html, headers=NO_CACHE_HEADERS)


@app.get("/health")
async def health_check():
    return {"status": "ok", "version": APP_VERSION, "public_engine": PUBLIC_ENGINE, "public_engine_label": PUBLIC_ENGINE_LABEL}


@app.get("/api/app/version")
async def app_version():
    return {
        "version": APP_VERSION,
        "public_engine": PUBLIC_ENGINE,
        "public_engine_label": PUBLIC_ENGINE_LABEL,
        "public_scanner_website": _public_scanner_website,
        "private_research_routes": _private_research,
        "market_data_provider": "server_side_configured_provider",
        "public_raw_market_data": False,
        "chart_provider": "TradingView",
    }


@app.get("/api/app/stats")
async def app_public_stats():
    return {"total_stock_searches": get_app_counter("stock_searches")}


@app.get("/api/app/market-cache")
async def app_market_cache_status():
    if not env_bool("ORYNTRA_PRIVATE_RESEARCH_ROUTES", False):
        raise HTTPException(status_code=404, detail="Not found")
    return market_cache_status()

@app.get("/api/app/ads")
async def app_ads():
    web_slots = ad_slot_env("ADSENSE_SLOT")
    android_slots = ad_slot_env("ADMOB_ANDROID")
    ios_slots = ad_slot_env("ADMOB_IOS")
    diagnostics = ads_diagnostics()
    return {
        "ads_enabled": env_bool("ADS_ENABLED", False),
        "placements": AD_PLACEMENTS,
        "web": {
            "provider": "adsense",
            "enabled": diagnostics["web_ads_enabled"],
            "client": adsense_client_id(),
            "preview_mode": diagnostics["preview_mode"],
            "auto_ads_enabled": diagnostics["auto_ads_enabled"],
            "slots": web_slots,
        },
        "flutter": {
            "provider": "admob",
            "enabled": env_bool("FLUTTER_ADS_ENABLED", False),
            "android_app_id": os.getenv("ADMOB_ANDROID_APP_ID", "").strip(),
            "ios_app_id": os.getenv("ADMOB_IOS_APP_ID", "").strip(),
            "android_units": android_slots,
            "ios_units": ios_slots,
        },
        "diagnostics": diagnostics,
    }

@app.get("/api/app/ads/diagnostics")
async def app_ads_diagnostics():
    return ads_diagnostics()

@app.get("/ads.txt", include_in_schema=False)
async def ads_txt():
    publisher = adsense_publisher_id()
    if not publisher:
        raise HTTPException(status_code=404, detail="AdSense publisher ID is not configured")
    line = f"google.com, {publisher}, DIRECT, f08c47fec0942fa0\n"
    return PlainTextResponse(line, headers={"Cache-Control": "public, max-age=3600"})

@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    site = public_site_url()
    lines = ["User-agent: *", "Allow: /"]
    if site:
        lines.append(f"Sitemap: {site}/sitemap.xml")
    return PlainTextResponse("\n".join(lines) + "\n")

@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    site = public_site_url()
    if not site:
        raise HTTPException(status_code=404, detail="Public site URL is not configured")
    paths = ["/", "/legal/terms", "/legal/privacy", "/legal/risk-disclaimer", "/legal/methodology", "/legal/contact"]
    urls = "".join(f"<url><loc>{escape(site + path)}</loc></url>" for path in paths)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(content=xml, media_type="application/xml")

