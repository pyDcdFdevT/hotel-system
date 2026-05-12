from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app import models  # noqa: F401  (registra tablas en metadata)
from app.routers import (
    cuentas,
    gastos,
    habitaciones,
    inventario,
    pedidos,
    personal,
    productos,
    reportes,
    reservas,
    tasa,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"


def _create_tables() -> None:
    Base.metadata.create_all(bind=engine)


_create_tables()


app = FastAPI(
    title="Hotel System API",
    version="1.0.0",
    description="Sistema integral de gestión hotelera (habitaciones, reservas, POS, inventario, gastos).",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


api_routers = [
    tasa.router,
    habitaciones.router,
    reservas.router,
    productos.router,
    pedidos.router,
    inventario.router,
    gastos.router,
    personal.router,
    cuentas.router,
    reportes.router,
]
for router in api_routers:
    app.include_router(router, prefix="/api")


if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="static",
    )


@app.get("/", include_in_schema=False)
def root():
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return JSONResponse(
        {
            "service": "hotel-system",
            "status": "ok",
            "message": "Frontend no encontrado en static/index.html",
        }
    )


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "hotel-system"}
