"""Seed inicial del sistema de hotel.

Idempotente: solo crea filas que no existen. Si la variable de entorno
``SEED_ONLY_IF_EMPTY=1`` está definida, salta si ya hay habitaciones cargadas.

Uso::

    python -m app.seed
"""

from __future__ import annotations

import os
from decimal import Decimal

from app.database import Base, SessionLocal, engine
from app.models import (
    CategoriaGasto,
    CuentaBanco,
    Habitacion,
    Producto,
    Receta,
    TasaCambio,
    today,
)


TASA_INICIAL = Decimal("405.35")


HABITACIONES_INICIALES = [
    {
        "numero": f"{numero}",
        "tipo": "standard",
        "precio_usd": Decimal("40.00"),
        "precio_bs": Decimal("16000.00"),
        "estado": "disponible",
    }
    for numero in range(101, 111)
]


CATEGORIAS_GASTO = [
    {"nombre": "Servicios", "tipo": "operativo", "descripcion": "Luz, agua, gas, internet"},
    {"nombre": "Insumos", "tipo": "operativo", "descripcion": "Compras menores para operación"},
    {"nombre": "Mantenimiento", "tipo": "operativo", "descripcion": "Reparaciones y mantenimiento"},
    {"nombre": "Nómina", "tipo": "personal", "descripcion": "Pago a empleados"},
    {"nombre": "Proveedores", "tipo": "inventario", "descripcion": "Compras a proveedores"},
    {"nombre": "Marketing", "tipo": "ventas", "descripcion": "Publicidad y promoción"},
    {"nombre": "Impuestos", "tipo": "tributario", "descripcion": "Impuestos municipales y nacionales"},
    {"nombre": "Otros", "tipo": "operativo", "descripcion": "Gastos varios"},
]


CUENTAS_INICIALES = [
    {"nombre": "BcoVen", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "BcoHLC", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "BcoP", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "BcoZ", "tipo": "banco", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "EfectivoBs", "tipo": "caja", "moneda": "BS", "saldo": Decimal("0")},
    {"nombre": "EfectivoUsd", "tipo": "caja", "moneda": "USD", "saldo": Decimal("0")},
]


PRODUCTOS_INICIALES = [
    {
        "nombre": "Polar",
        "categoria": "bebidas",
        "descripcion": "Cerveza Polar 222 ml",
        "precio_bs": Decimal("1000.00"),
        "precio_usd": Decimal("2.50"),
        "costo_bs": Decimal("600.00"),
        "stock_actual": Decimal("48"),
        "stock_minimo": Decimal("12"),
        "unidad": "botella",
        "es_para_venta": True,
    },
    {
        "nombre": "Agua",
        "categoria": "bebidas",
        "descripcion": "Botella de agua 500 ml",
        "precio_bs": Decimal("400.00"),
        "precio_usd": Decimal("1.00"),
        "costo_bs": Decimal("180.00"),
        "stock_actual": Decimal("60"),
        "stock_minimo": Decimal("20"),
        "unidad": "botella",
        "es_para_venta": True,
    },
    {
        "nombre": "Hamburguesa",
        "categoria": "comida",
        "descripcion": "Hamburguesa de la casa",
        "precio_bs": Decimal("3200.00"),
        "precio_usd": Decimal("8.00"),
        "costo_bs": Decimal("0.00"),
        "stock_actual": Decimal("0"),
        "stock_minimo": Decimal("0"),
        "unidad": "unidad",
        "es_para_venta": True,
    },
    {
        "nombre": "Pan hamburguesa",
        "categoria": "insumo",
        "descripcion": "Pan tipo brioche",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("250.00"),
        "stock_actual": Decimal("40"),
        "stock_minimo": Decimal("10"),
        "unidad": "unidad",
        "es_para_venta": False,
    },
    {
        "nombre": "Carne para hamburguesa",
        "categoria": "insumo",
        "descripcion": "Carne molida 150 g",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("900.00"),
        "stock_actual": Decimal("30"),
        "stock_minimo": Decimal("8"),
        "unidad": "unidad",
        "es_para_venta": False,
    },
    {
        "nombre": "Lechuga",
        "categoria": "insumo",
        "descripcion": "Hoja de lechuga",
        "precio_bs": Decimal("0"),
        "precio_usd": Decimal("0"),
        "costo_bs": Decimal("50.00"),
        "stock_actual": Decimal("80"),
        "stock_minimo": Decimal("20"),
        "unidad": "hoja",
        "es_para_venta": False,
    },
]


RECETA_HAMBURGUESA = [
    ("Pan hamburguesa", Decimal("1")),
    ("Carne para hamburguesa", Decimal("1")),
    ("Lechuga", Decimal("2")),
]


def _upsert(db, modelo, filtro: dict, defaults: dict):
    existente = db.query(modelo).filter_by(**filtro).first()
    if existente:
        return existente, False
    instancia = modelo(**{**filtro, **defaults})
    db.add(instancia)
    db.flush()
    return instancia, True


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if os.getenv("SEED_ONLY_IF_EMPTY") == "1" and db.query(Habitacion).first():
            print("Seed omitido: la base ya tiene datos.")
            return

        if not db.query(TasaCambio).filter(TasaCambio.fecha == today()).first():
            db.add(TasaCambio(fecha=today(), usd_a_ves=TASA_INICIAL))

        for cat in CATEGORIAS_GASTO:
            _upsert(db, CategoriaGasto, {"nombre": cat["nombre"]}, cat)

        for cuenta in CUENTAS_INICIALES:
            _upsert(db, CuentaBanco, {"nombre": cuenta["nombre"]}, cuenta)

        for hab in HABITACIONES_INICIALES:
            _upsert(db, Habitacion, {"numero": hab["numero"]}, hab)

        productos_por_nombre: dict[str, Producto] = {}
        for prod in PRODUCTOS_INICIALES:
            producto, _ = _upsert(db, Producto, {"nombre": prod["nombre"]}, prod)
            productos_por_nombre[prod["nombre"]] = producto

        hamburguesa = productos_por_nombre["Hamburguesa"]
        if not db.query(Receta).filter(Receta.producto_id == hamburguesa.id).first():
            for nombre_ingrediente, cantidad in RECETA_HAMBURGUESA:
                ingrediente = productos_por_nombre[nombre_ingrediente]
                db.add(
                    Receta(
                        producto_id=hamburguesa.id,
                        ingrediente_id=ingrediente.id,
                        cantidad=cantidad,
                    )
                )

        db.commit()
        print("Seed completado.")
    except Exception as exc:
        db.rollback()
        print(f"Error en seed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
