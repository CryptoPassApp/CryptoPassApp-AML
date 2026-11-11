from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bot.database import init_db
from bot.services.stars_payment import PLANS

from api.routes import admin, demo, passport, scan, user

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="CryptoPassApp API",
    version="1.0.0",
    description="Web3 security toolkit for TON: AML Scanner, Trust Passport, P2P Radar",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    await init_db()


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/scan-test.html", include_in_schema=False)
async def scan_test() -> FileResponse:
    return FileResponse(STATIC_DIR / "scan-test.html")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "plans": list(PLANS.keys())}


app.include_router(scan.router)
app.include_router(passport.router)
app.include_router(user.router)
app.include_router(demo.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
