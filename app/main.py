from __future__ import annotations

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app import models  # noqa: F401  (registra tablas en metadata)
from app.routers import (
    auth,
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
from app.routers.auth import require_roles


STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_FILE = STATIC_DIR / "index.html"
LOGIN_FILE = STATIC_DIR / "login.html"
COCINA_FILE = STATIC_DIR / "cocina.html"


def _create_tables() -> None:
    Base.metadata.create_all(bind=engine)


_create_tables()


app = FastAPI(
    title="Hotel System API",
    version="1.0.0",
    description=(
        "Sistema integral de gestión hotelera (habitaciones, reservas, POS, "
        "inventario, gastos) con auth por PIN y roles."
    ),
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers + matriz de roles
# ---------------------------------------------------------------------------
# - auth: público (login) y sólo admin para administración de usuarios (las
#   restricciones específicas se aplican dentro del propio router).
# - tasa / habitaciones / pedidos / productos: cualquier usuario autenticado
#   (mesero y cocina necesitan leerlos). Endpoints de escritura se restringen
#   con dependencias adicionales dentro de cada router.
# - reservas / reportes: admin + recepción.
# - inventario / gastos / personal / cuentas: sólo admin.

_AUTH = [
    Depends(require_roles("admin", "recepcion", "mesero", "cocina", "barra"))
]
_RECEPCION = [Depends(require_roles("admin", "recepcion"))]
_ADMIN = [Depends(require_roles("admin"))]

app.include_router(auth.router, prefix="/api")
app.include_router(tasa.router, prefix="/api", dependencies=_AUTH)
app.include_router(habitaciones.router, prefix="/api", dependencies=_AUTH)
app.include_router(reservas.router, prefix="/api", dependencies=_RECEPCION)
app.include_router(productos.router, prefix="/api", dependencies=_AUTH)
app.include_router(pedidos.router, prefix="/api", dependencies=_AUTH)
app.include_router(inventario.router, prefix="/api", dependencies=_ADMIN)
app.include_router(gastos.router, prefix="/api", dependencies=_ADMIN)
app.include_router(personal.router, prefix="/api", dependencies=_ADMIN)
app.include_router(cuentas.router, prefix="/api", dependencies=_ADMIN)
app.include_router(reportes.router, prefix="/api", dependencies=_AUTH)


# ---------------------------------------------------------------------------
# Archivos estáticos y páginas
# ---------------------------------------------------------------------------
if STATIC_DIR.exists():
    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR), html=True),
        name="static",
    )


@app.get("/", include_in_schema=False)
def root():
    # La SPA se sirve siempre; el JS redirige a /login si no hay token.
    if INDEX_FILE.exists():
        return FileResponse(INDEX_FILE)
    return JSONResponse(
        {
            "service": "hotel-system",
            "status": "ok",
            "message": "Frontend no encontrado en static/index.html",
        }
    )


@app.get("/login", include_in_schema=False)
@app.get("/login.html", include_in_schema=False)
def login_page():
    if LOGIN_FILE.exists():
        return FileResponse(LOGIN_FILE)
    return JSONResponse({"error": "login.html no encontrado"}, status_code=404)


@app.get("/cocina", include_in_schema=False)
@app.get("/cocina.html", include_in_schema=False)
def cocina_page():
    if COCINA_FILE.exists():
        return FileResponse(COCINA_FILE)
    return JSONResponse({"error": "cocina.html no encontrado"}, status_code=404)


@app.get("/api/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "hotel-system"}
