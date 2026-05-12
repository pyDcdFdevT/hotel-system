"""Autenticación por PIN + roles para el hotel.

Diseño:

* Las sesiones son tokens opacos almacenados en memoria del proceso
  (suficiente para una sucursal pequeña; si se escala a múltiples instancias,
  bastará con cambiar el dict por Redis manteniendo la misma firma).
* PINs se almacenan con SHA-256 + sal estática del servidor. No es PBKDF2 ni
  bcrypt, pero protege ante un volcado accidental del archivo SQLite.
* La autorización por rol se aplica vía dependencias FastAPI
  (`Depends(require_roles("admin", "recepcion"))`).
* Las acciones críticas se registran en ``logs_acceso``.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Callable, Iterable, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LogAcceso, Usuario, caracas_now
from app.schemas import (
    LogAccesoOut,
    LoginRequest,
    LoginResponse,
    UsuarioCreate,
    UsuarioOut,
    UsuarioPublico,
    UsuarioUpdate,
)


router = APIRouter(prefix="/auth", tags=["auth"])


SESSION_HOURS = 8
PIN_SALT = os.getenv("HOTEL_PIN_SALT", "hotel-system-default-salt")


# token -> {"usuario_id": int, "rol": str, "expira": datetime UTC}
sesiones_activas: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------
def hash_pin(pin: str) -> str:
    salt = PIN_SALT.encode("utf-8")
    return hashlib.sha256(salt + pin.encode("utf-8")).hexdigest()


def verificar_pin(pin: str, pin_hash: str) -> bool:
    if not pin or not pin_hash:
        return False
    return secrets.compare_digest(hash_pin(pin), pin_hash)


def generar_token() -> str:
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Utilidades de sesión y auditoría
# ---------------------------------------------------------------------------
def _registrar_log(
    db: Session,
    *,
    usuario_id: Optional[int],
    nombre: Optional[str],
    accion: str,
    detalle: str,
    ip: str,
    exitoso: bool,
) -> None:
    log = LogAcceso(
        usuario_id=usuario_id,
        usuario_nombre=nombre,
        accion=accion,
        detalle=detalle,
        ip=ip,
        exitoso=exitoso,
    )
    db.add(log)
    db.commit()


def _ip(request: Request) -> str:
    return request.client.host if request.client else "desconocida"


def _extraer_token(request: Request) -> Optional[str]:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    # También permitir ?token=... y header X-Auth-Token (útil para EventSource).
    qs_token = request.query_params.get("token")
    if qs_token:
        return qs_token
    alt = request.headers.get("X-Auth-Token")
    return alt or None


def _purgar_sesion_expirada(token: str) -> None:
    sesion = sesiones_activas.get(token)
    if sesion and sesion["expira"] < datetime.now(UTC):
        sesiones_activas.pop(token, None)


# ---------------------------------------------------------------------------
# Dependencias FastAPI
# ---------------------------------------------------------------------------
def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> Usuario:
    token = _extraer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="No autenticado")
    _purgar_sesion_expirada(token)
    sesion = sesiones_activas.get(token)
    if not sesion:
        raise HTTPException(status_code=401, detail="Sesión inválida o expirada")
    usuario = db.query(Usuario).filter(Usuario.id == sesion["usuario_id"]).first()
    if not usuario or not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario no activo")
    return usuario


def require_roles(*roles: str) -> Callable[..., Usuario]:
    """Genera una dependencia que exige que el usuario tenga uno de los roles."""

    permitidos = set(roles)

    def _dep(usuario: Usuario = Depends(get_current_user)) -> Usuario:
        if usuario.rol not in permitidos:
            raise HTTPException(
                status_code=403,
                detail=f"Acceso denegado. Se requiere uno de: {sorted(permitidos)}",
            )
        return usuario

    return _dep


# ---------------------------------------------------------------------------
# Endpoints públicos / autenticación
# ---------------------------------------------------------------------------
@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _ip(request)
    usuarios = db.query(Usuario).filter(Usuario.activo.is_(True)).all()
    usuario: Optional[Usuario] = None
    for u in usuarios:
        if verificar_pin(req.pin, u.pin_hash):
            usuario = u
            break

    if not usuario:
        _registrar_log(
            db,
            usuario_id=None,
            nombre="desconocido",
            accion="login",
            detalle=f"PIN incorrecto (prefijo {req.pin[:2]}***)",
            ip=ip,
            exitoso=False,
        )
        raise HTTPException(status_code=401, detail="PIN incorrecto")

    usuario.ultimo_acceso = caracas_now()

    token = generar_token()
    sesiones_activas[token] = {
        "usuario_id": usuario.id,
        "rol": usuario.rol,
        "expira": datetime.now(UTC) + timedelta(hours=SESSION_HOURS),
    }

    _registrar_log(
        db,
        usuario_id=usuario.id,
        nombre=usuario.nombre,
        accion="login",
        detalle=f"Login exitoso desde {ip}",
        ip=ip,
        exitoso=True,
    )

    return LoginResponse(
        success=True,
        usuario=UsuarioPublico(id=usuario.id, nombre=usuario.nombre, rol=usuario.rol),
        token=token,
        mensaje=f"Bienvenido {usuario.nombre}",
    )


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = _extraer_token(request)
    if token and token in sesiones_activas:
        usuario_id = sesiones_activas[token]["usuario_id"]
        del sesiones_activas[token]
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        _registrar_log(
            db,
            usuario_id=usuario_id,
            nombre=usuario.nombre if usuario else None,
            accion="logout",
            detalle="Cierre de sesión",
            ip=_ip(request),
            exitoso=True,
        )
    return {"success": True}


@router.get("/me", response_model=UsuarioPublico)
def me(usuario: Usuario = Depends(get_current_user)):
    return UsuarioPublico(id=usuario.id, nombre=usuario.nombre, rol=usuario.rol)


# ---------------------------------------------------------------------------
# Gestión de usuarios (solo admin)
# ---------------------------------------------------------------------------
@router.get("/usuarios", response_model=List[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("admin")),
):
    return db.query(Usuario).order_by(Usuario.nombre.asc()).all()


@router.post("/usuarios", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def crear_usuario(
    data: UsuarioCreate,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(require_roles("admin")),
):
    from app.models import ROLES_VALIDOS

    if data.rol not in ROLES_VALIDOS:
        raise HTTPException(
            status_code=400, detail=f"Rol inválido. Use: {list(ROLES_VALIDOS)}"
        )
    if db.query(Usuario).filter(Usuario.nombre == data.nombre).first():
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese nombre")

    usuario = Usuario(
        nombre=data.nombre,
        pin_hash=hash_pin(data.pin),
        rol=data.rol,
        activo=data.activo,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    _registrar_log(
        db,
        usuario_id=actor.id,
        nombre=actor.nombre,
        accion="usuario_crear",
        detalle=f"Creó usuario {usuario.nombre} ({usuario.rol})",
        ip="local",
        exitoso=True,
    )
    return usuario


@router.put("/usuarios/{usuario_id}", response_model=UsuarioOut)
def actualizar_usuario(
    usuario_id: int,
    data: UsuarioUpdate,
    db: Session = Depends(get_db),
    actor: Usuario = Depends(require_roles("admin")),
):
    from app.models import ROLES_VALIDOS

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    payload = data.model_dump(exclude_unset=True)
    if "rol" in payload and payload["rol"] not in ROLES_VALIDOS:
        raise HTTPException(
            status_code=400, detail=f"Rol inválido. Use: {list(ROLES_VALIDOS)}"
        )
    if "pin" in payload and payload["pin"]:
        usuario.pin_hash = hash_pin(payload.pop("pin"))
    elif "pin" in payload:
        payload.pop("pin")
    for key, value in payload.items():
        setattr(usuario, key, value)
    db.commit()
    db.refresh(usuario)
    _registrar_log(
        db,
        usuario_id=actor.id,
        nombre=actor.nombre,
        accion="usuario_editar",
        detalle=f"Actualizó usuario #{usuario.id} ({usuario.nombre})",
        ip="local",
        exitoso=True,
    )
    return usuario


@router.get("/logs", response_model=List[LogAccesoOut])
def listar_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles("admin")),
):
    return (
        db.query(LogAcceso)
        .order_by(LogAcceso.id.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )


# ---------------------------------------------------------------------------
# Helpers re-exportables
# ---------------------------------------------------------------------------
__all__: Iterable[str] = (
    "router",
    "sesiones_activas",
    "hash_pin",
    "verificar_pin",
    "generar_token",
    "get_current_user",
    "require_roles",
)
