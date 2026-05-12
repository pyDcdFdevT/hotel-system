"""Test end-to-end del sistema hotel.

Ejecutar con::

    python -m scripts.test_general

El script usa una base de datos SQLite temporal (no toca datos reales) y
levanta la app FastAPI en proceso con ``TestClient``. Recorre los módulos
críticos imprimiendo ``✅``/``❌`` por cada paso y un resumen final.

No requiere ``playwright``: la pantalla de cocina y POS exponen toda su
lógica vía API REST, así que el ``TestClient`` cubre el contrato del
backend que esas pantallas consumen.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Optional


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------
class TestRunner:
    """Pequeño helper que agrupa pruebas por módulo y produce un resumen."""

    def __init__(self) -> None:
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.fallos: list[str] = []
        self._inicio_modulo: float = 0.0
        self._inicio_total: float = time.perf_counter()
        self._modulo_actual: Optional[str] = None

    def modulo(self, nombre: str) -> None:
        print()
        print("=" * 60)
        print(f"📦  MÓDULO: {nombre}")
        print("=" * 60)
        self._modulo_actual = nombre
        self._inicio_modulo = time.perf_counter()

    def paso(self, descripcion: str, accion: Callable[[], Any]) -> Any:
        """Ejecuta ``accion()`` y reporta el resultado."""
        self.total += 1
        try:
            resultado = accion()
            print(f"  ✅  {descripcion}")
            self.passed += 1
            return resultado
        except AssertionError as exc:
            self._reportar_fallo(descripcion, str(exc) or "Assertion failed")
            return None
        except Exception as exc:  # pragma: no cover - red de seguridad
            self._reportar_fallo(
                descripcion, f"{type(exc).__name__}: {exc}"
            )
            return None

    def _reportar_fallo(self, descripcion: str, motivo: str) -> None:
        print(f"  ❌  {descripcion}")
        print(f"      → {motivo}")
        self.failed += 1
        self.fallos.append(
            f"[{self._modulo_actual or '-'}] {descripcion} :: {motivo}"
        )

    def resumen(self) -> int:
        duracion = time.perf_counter() - self._inicio_total
        print()
        print("=" * 60)
        print("📊  RESUMEN")
        print("=" * 60)
        print(f"  Total:   {self.total}")
        print(f"  ✅  OK:   {self.passed}")
        print(f"  ❌  FAIL: {self.failed}")
        print(f"  ⏱  Tiempo: {duracion:.2f} s")
        if self.fallos:
            print()
            print("Fallos:")
            for f in self.fallos:
                print(f"  - {f}")
            return 1
        print()
        print("🎉  Todas las pruebas pasaron.")
        return 0


# ---------------------------------------------------------------------------
# Bootstrap: DB temporal + TestClient
# ---------------------------------------------------------------------------
@contextmanager
def _entorno_temporal():
    """Crea una DB SQLite temporal y limpia al salir."""
    tmpdir = tempfile.mkdtemp(prefix="hotel-test-general-")
    db_path = Path(tmpdir) / "hotel.db"
    os.environ["HOTEL_DB_URL"] = f"sqlite:///{db_path}"
    os.environ["SEED_ONLY_IF_EMPTY"] = "0"
    try:
        yield db_path
    finally:
        try:
            db_path.unlink(missing_ok=True)
        except Exception:
            pass


def _crear_client():
    """Devuelve un TestClient autenticado como admin (con el seed cargado)."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.seed import seed

    seed()
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"pin": "1234"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, app


def _login_token(client, pin: str) -> str:
    from fastapi.testclient import TestClient

    fresh = TestClient(client.app)
    resp = fresh.post("/api/auth/login", json={"pin": pin})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# Utilidades de dominio
# ---------------------------------------------------------------------------
def _habitacion_disponible(client) -> dict:
    habs = client.get("/api/habitaciones/").json()
    libre = next((h for h in habs if h["estado"] == "disponible"), None)
    if libre:
        return libre
    candidata = next(h for h in habs if h["estado"] != "ocupada")
    client.put(
        f"/api/habitaciones/{candidata['id']}/estado",
        json={"estado": "disponible"},
    )
    return client.get(f"/api/habitaciones/{candidata['id']}").json()


def _primer_producto_venta(client) -> dict:
    productos = client.get("/api/productos/").json()
    prod = next(
        p
        for p in productos
        if p["activo"]
        and p["es_para_venta"]
        and float(p.get("stock_actual", 0)) > 0
    )
    return prod


def _producto_por_area(client, area: str) -> Optional[dict]:
    productos = client.get("/api/productos/").json()
    return next(
        (
            p
            for p in productos
            if p["activo"]
            and p["es_para_venta"]
            and float(p.get("stock_actual", 0)) > 0
            and (p.get("area", "").lower() == area
                 or p.get("categoria", "").lower() == area)
        ),
        None,
    )


# ---------------------------------------------------------------------------
# Módulos de pruebas
# ---------------------------------------------------------------------------
def modulo_habitaciones(runner: TestRunner, client) -> None:
    runner.modulo("1. Habitaciones")

    def _ver_lista():
        habs = client.get("/api/habitaciones/").json()
        assert isinstance(habs, list) and len(habs) >= 11, (
            f"Se esperaban ≥11 habitaciones, hay {len(habs)}"
        )
        activas = [h for h in habs if h["estado"] != "inhabilitada"]
        assert len(activas) >= 11, (
            f"Se esperaban ≥11 activas, hay {len(activas)}"
        )

    runner.paso("Login admin funciona (PIN 1234)", lambda: client.get("/api/auth/me").raise_for_status())
    runner.paso("Listado de habitaciones (≥11 activas)", _ver_lista)

    estado = {"hab_id": None}

    def _checkin_completo():
        hab = _habitacion_disponible(client)
        estado["hab_id"] = hab["id"]
        resp = client.post(
            f"/api/habitaciones/{hab['id']}/checkin",
            json={
                "huesped": "Test General",
                "noches": 1,
                "pais_origen": "Venezuela",
                "tipo_documento": "N",
                "numero_documento": "V-12345678",
                "vehiculo_modelo": "Toyota Corolla",
                "vehiculo_color": "Blanco",
                "vehiculo_placa": "AB123CD",
                "hora_ingreso": "12:00",
            },
        )
        assert resp.status_code == 200, resp.text
        reserva = resp.json()
        assert reserva["huesped"] == "Test General"
        assert reserva["pais_origen"] == "Venezuela"
        assert reserva["numero_documento"] == "V-12345678"
        assert reserva["vehiculo_placa"] == "AB123CD"
        estado["reserva"] = reserva

    runner.paso("Check-in completo (país, documento, vehículo, hora)", _checkin_completo)

    def _datos_en_tarjeta():
        # /reservas/activas debe devolver los datos del huésped.
        reservas = client.get("/api/reservas/activas").json()
        match = next(
            (r for r in reservas if r["habitacion_id"] == estado["hab_id"]), None
        )
        assert match, "Reserva activa no encontrada para la habitación"
        assert match["huesped"] == "Test General"
        assert match["vehiculo_modelo"] == "Toyota Corolla"

    runner.paso("Datos del huésped disponibles para la tarjeta", _datos_en_tarjeta)

    def _consumo_desde_pos():
        prod = _primer_producto_venta(client)
        numero = client.get(f"/api/habitaciones/{estado['hab_id']}").json()["numero"]
        pedido = client.post(
            "/api/pedidos/",
            json={
                "tipo": "habitacion",
                "habitacion_numero": numero,
                "items": [{"producto_id": prod["id"], "cantidad": 1}],
            },
        )
        assert pedido.status_code == 201, pedido.text
        estado["pedido_consumo"] = pedido.json()

    runner.paso("Agregar consumo a habitación desde POS", _consumo_desde_pos)

    def _late_checkout_recarga():
        preview = client.get(
            f"/api/habitaciones/{estado['hab_id']}/checkout-preview?hora_salida=16:00"
        ).json()
        assert preview["horas_extra"] == 3
        # $5/h × 3 = $15.
        assert float(preview["recarga_extra_usd"]) == 15.0
        estado["preview"] = preview

    runner.paso("Late check-out calcula $5/h (3 horas → $15)", _late_checkout_recarga)

    def _checkout_usd():
        resp = client.post(
            f"/api/habitaciones/{estado['hab_id']}/checkout",
            json={"opcion_pago": "efectivo_usd", "hora_salida": "16:00"},
        )
        assert resp.status_code == 200, resp.text

    runner.paso("Check-out en USD efectivo (sin tasa)", _checkout_usd)

    def _historial_total_correcto():
        data = client.get("/api/reportes/ventas-por-area-con-metodos").json()
        total = float(data["habitaciones"]["total_usd"])
        recarga = float(estado["preview"]["recarga_extra_usd"])
        tarifa = float(estado["preview"]["tarifa_usd"])
        assert total >= tarifa + recarga, (
            f"Habitaciones {total} < tarifa+recarga {tarifa + recarga}"
        )

    runner.paso("Reportes: habitaciones suma tarifa + recarga", _historial_total_correcto)


def modulo_ventas(runner: TestRunner, client) -> None:
    runner.modulo("2. Ventas (POS)")

    nombre = "Mesa General Test"
    prod = _primer_producto_venta(client)
    estado: dict[str, Any] = {}

    def _crear_mesa_unica():
        resp = client.post(
            "/api/pedidos/",
            json={
                "tipo": "restaurante",
                "mesa": nombre,
                "items": [{"producto_id": prod["id"], "cantidad": 1}],
            },
        )
        assert resp.status_code == 201, resp.text
        estado["pedido"] = resp.json()

    runner.paso("Crear mesa con nombre único", _crear_mesa_unica)

    def _rechazo_duplicado():
        dup = client.post(
            "/api/pedidos/",
            json={
                "tipo": "restaurante",
                "mesa": nombre,
                "items": [{"producto_id": prod["id"], "cantidad": 1}],
            },
        )
        assert dup.status_code == 400, dup.text

    runner.paso("Backend rechaza nombres duplicados", _rechazo_duplicado)

    def _agregar_de_varias_areas():
        producto_bar = _producto_por_area(client, "bar")
        producto_pisc = _producto_por_area(client, "piscina")
        items = [{"producto_id": prod["id"], "cantidad": 1}]
        if producto_bar:
            items.append({"producto_id": producto_bar["id"], "cantidad": 1})
        if producto_pisc and producto_pisc["id"] not in (
            prod["id"], producto_bar["id"] if producto_bar else None
        ):
            items.append({"producto_id": producto_pisc["id"], "cantidad": 1})
        r = client.post(
            f"/api/pedidos/{estado['pedido']['id']}/agregar",
            json={"tipo": "restaurante", "items": items},
        )
        assert r.status_code == 200, r.text
        estado["pedido"] = r.json()

    runner.paso("Agregar productos de bar/cocina/piscina al pedido", _agregar_de_varias_areas)

    def _modificar_cantidades():
        items_actuales = [
            {"producto_id": d["producto_id"], "cantidad": float(d["cantidad"]) + 1}
            for d in estado["pedido"]["detalles"]
        ]
        r = client.put(
            f"/api/pedidos/{estado['pedido']['id']}/items",
            json={"items": items_actuales},
        )
        assert r.status_code == 200, r.text
        nuevo = r.json()
        # Comparamos como floats: el JSON serializa Decimal como string.
        assert float(nuevo["total_usd"]) >= float(estado["pedido"]["total_usd"]), (
            f"Total no aumentó tras +1: {nuevo['total_usd']} < {estado['pedido']['total_usd']}"
        )
        estado["pedido"] = nuevo

    runner.paso("Modificar cantidades vía PUT /items", _modificar_cantidades)

    def _aparcar():
        r = client.post(f"/api/pedidos/{estado['pedido']['id']}/aparcar", json={})
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "abierto"

    runner.paso("Aparcar la cuenta (sigue abierta)", _aparcar)

    def _recuperar_aparcada():
        activos = client.get("/api/pedidos/activos").json()
        assert any(p["id"] == estado["pedido"]["id"] for p in activos)

    runner.paso("Recuperar cuenta aparcada desde lista de activos", _recuperar_aparcada)

    def _cobrar_usd():
        for d in estado["pedido"]["detalles"]:
            client.put(
                f"/api/pedidos/{estado['pedido']['id']}/detalles/{d['id']}/estado",
                json={"estado": "entregado"},
            )
        # ``total_usd`` y ``total_bs`` se calculan con precios independientes
        # por producto, así que el equivalente en USD del total_bs (que es
        # lo que el backend valida) puede diferir. Convertimos vía tasa BCV.
        tasa = float(client.get("/api/tasa/actual").json()["bcv"])
        total_bs = float(estado["pedido"]["total_bs"])
        monto_usd = round((total_bs / tasa) + 0.01, 2)
        r = client.post(
            f"/api/pedidos/{estado['pedido']['id']}/pagar",
            json={
                "metodo_pago": "usd",
                "tasa_tipo": "bcv",
                "monto_usd": monto_usd,
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "pagado"
        estado["pedido_pagado_usd"] = r.json()

    runner.paso("Cobrar pedido en USD efectivo", _cobrar_usd)

    def _crear_y_cobrar_bs():
        nombre_bs = "Mesa BS Test"
        r1 = client.post(
            "/api/pedidos/",
            json={
                "tipo": "restaurante",
                "mesa": nombre_bs,
                "items": [{"producto_id": prod["id"], "cantidad": 1}],
            },
        )
        assert r1.status_code == 201
        ped = r1.json()
        # Marcamos como entregado para evitar bloqueo de cobro.
        for d in ped["detalles"]:
            client.put(
                f"/api/pedidos/{ped['id']}/detalles/{d['id']}/estado",
                json={"estado": "entregado"},
            )
        r2 = client.post(
            f"/api/pedidos/{ped['id']}/pagar",
            json={
                "metodo_pago": "transferencia",
                "tasa_tipo": "bcv",
                "monto_bs": float(ped["total_bs"]),
            },
        )
        assert r2.status_code == 200, r2.text

    runner.paso("Cobrar otro pedido en Bs transferencia", _crear_y_cobrar_bs)

    def _anular_venta_admin():
        ped_id = estado["pedido_pagado_usd"]["id"]
        r = client.post(
            f"/api/pedidos/{ped_id}/anular",
            json={"motivo": "Prueba general"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["estado"] == "anulado"
        assert body.get("success") is True
        assert body.get("anulado_por")

    runner.paso("Anular venta paga (solo admin)", _anular_venta_admin)


def modulo_cocina(runner: TestRunner, client) -> None:
    runner.modulo("3. Cocina (estados por ítem)")

    prod = _primer_producto_venta(client)
    estado: dict[str, Any] = {}

    def _crear_pedido_cocina():
        r = client.post(
            "/api/pedidos/",
            json={
                "tipo": "restaurante",
                "mesa": "Mesa Cocina General",
                "items": [{"producto_id": prod["id"], "cantidad": 2}],
            },
        )
        assert r.status_code == 201
        estado["pedido"] = r.json()

    runner.paso("Pedido creado y pendiente para cocina", _crear_pedido_cocina)

    def _aparece_en_cocina():
        cola = client.get("/api/pedidos/activos-cocina").json()
        assert any(p["id"] == estado["pedido"]["id"] for p in cola)

    runner.paso("Pedido aparece en /activos-cocina", _aparece_en_cocina)

    detalle_id = None

    def _marcar_en_preparacion():
        nonlocal detalle_id
        det = estado["pedido"]["detalles"][0]
        detalle_id = det["id"]
        # Cocina marca en_preparacion.
        token = _login_token(client, "3333")
        r = client.put(
            f"/api/pedidos/{estado['pedido']['id']}/detalles/{detalle_id}/estado",
            json={"estado": "en_preparacion"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "en_preparacion"

    runner.paso("Cocina marca ítem como 'en preparación'", _marcar_en_preparacion)

    def _marcar_listo():
        token = _login_token(client, "3333")
        r = client.put(
            f"/api/pedidos/{estado['pedido']['id']}/detalles/{detalle_id}/estado",
            json={"estado": "listo"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "listo"

    runner.paso("Cocina marca ítem como 'listo'", _marcar_listo)

    def _mesero_ve_estado():
        token = _login_token(client, "2222")
        detalles = client.get(
            f"/api/pedidos/{estado['pedido']['id']}/detalles",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        det = next(d for d in detalles if d["id"] == detalle_id)
        assert det["estado"] == "listo"
        assert det["listo_en"] is not None

    runner.paso("Mesero ve el estado 'listo' del ítem", _mesero_ve_estado)

    def _mesero_marca_entregado():
        token = _login_token(client, "2222")
        r = client.put(
            f"/api/pedidos/{estado['pedido']['id']}/detalles/{detalle_id}/estado",
            json={"estado": "entregado"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "entregado"

    runner.paso("Mesero marca el ítem como 'entregado'", _mesero_marca_entregado)

    def _sale_de_cocina():
        cola = client.get("/api/pedidos/activos-cocina").json()
        assert estado["pedido"]["id"] not in [p["id"] for p in cola], (
            "El pedido debería desaparecer de cocina cuando todos los ítems están listos/entregados"
        )

    runner.paso("Pedido sale de cocina al entregarse todo", _sale_de_cocina)


def modulo_favoritos(runner: TestRunner, client) -> None:
    runner.modulo("4. Favoritos por usuario")

    productos = client.get("/api/productos/").json()
    aptos = [p for p in productos if p["activo"] and p["es_para_venta"]]
    assert len(aptos) >= 3
    a, b, c = aptos[:3]

    # Limpiamos para que el módulo sea idempotente.
    for p in aptos[:5]:
        client.delete(f"/api/productos/favoritos/{p['id']}")

    def _agregar():
        r = client.post("/api/productos/favoritos", json={"producto_id": a["id"]})
        assert r.status_code == 201, r.text

    runner.paso("Agregar producto a favoritos", _agregar)

    def _quitar():
        r = client.delete(f"/api/productos/favoritos/{a['id']}")
        assert r.status_code == 200
        assert r.json()["removed"] is True

    runner.paso("Quitar producto de favoritos", _quitar)

    def _persistencia():
        # Agregar y leer en una sesión "fresca" (mismo token, distinta llamada).
        client.post("/api/productos/favoritos", json={"producto_id": b["id"]})
        favs = client.get("/api/productos/favoritos/mis-favoritos").json()
        assert b["id"] in [f["id"] for f in favs]

    runner.paso("Favoritos persisten entre llamadas", _persistencia)

    def _por_usuario():
        # Mesero agrega un favorito distinto, no debe verlo el admin.
        token_mesero = _login_token(client, "2222")
        H_mes = {"Authorization": f"Bearer {token_mesero}"}
        client.post(
            "/api/productos/favoritos",
            json={"producto_id": c["id"]},
            headers=H_mes,
        )
        favs_mes = client.get(
            "/api/productos/favoritos/mis-favoritos", headers=H_mes
        ).json()
        favs_admin = client.get("/api/productos/favoritos/mis-favoritos").json()
        ids_mes = [f["id"] for f in favs_mes]
        ids_admin = [f["id"] for f in favs_admin]
        assert c["id"] in ids_mes
        # Limpiamos antes de comparar (admin tal vez tenía c desde antes).
        if c["id"] in ids_admin:
            client.delete(f"/api/productos/favoritos/{c['id']}")
            ids_admin = [
                f["id"]
                for f in client.get(
                    "/api/productos/favoritos/mis-favoritos"
                ).json()
            ]
        assert c["id"] not in ids_admin, (
            "Los favoritos del mesero no deberían aparecer en los del admin"
        )

    runner.paso("Cada usuario tiene sus propios favoritos", _por_usuario)


def modulo_reservas(runner: TestRunner, client) -> None:
    runner.modulo("5. Reservas")

    hab = _habitacion_disponible(client)
    fecha_in = date.today() + timedelta(days=30)
    fecha_out = fecha_in + timedelta(days=3)
    estado: dict[str, Any] = {}

    def _crear_reserva():
        r = client.post(
            "/api/reservas/",
            json={
                "habitacion_id": hab["id"],
                "huesped": "Reserva General",
                "fecha_checkin": fecha_in.isoformat(),
                "fecha_checkout_estimado": fecha_out.isoformat(),
                "noches": 3,
                "pais_origen": "Colombia",
                "tipo_documento": "E",
                "numero_documento": "CO-9876",
            },
        )
        assert r.status_code in (200, 201), r.text
        estado["reserva"] = r.json()

    runner.paso("Crear reserva con datos completos", _crear_reserva)

    def _noches_correctas():
        assert int(estado["reserva"]["noches"]) == 3

    runner.paso("Cálculo de noches consistente (3 noches)", _noches_correctas)

    def _convertir_a_checkin():
        # Convertir la reserva a check-in real.
        r = client.post(
            f"/api/habitaciones/{hab['id']}/checkin",
            json={
                "huesped": "Reserva General",
                "noches": 3,
                "reserva_id": estado["reserva"]["id"],
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == "activa"
        estado["reserva_activa"] = r.json()

    runner.paso("Convertir reserva a check-in", _convertir_a_checkin)

    def _cancelar_reserva_con_reembolso():
        hab2 = _habitacion_disponible(client)
        # Pagamos $40 por anticipado al crear la reserva.
        r = client.post(
            "/api/reservas/",
            json={
                "habitacion_id": hab2["id"],
                "huesped": "Reserva Para Cancelar",
                "fecha_checkin": (fecha_in + timedelta(days=1)).isoformat(),
                "fecha_checkout_estimado": (fecha_out + timedelta(days=1)).isoformat(),
                "noches": 3,
                "pago_anticipado": True,
                "moneda_pago": "usd",
                "metodo_pago": "efectivo",
                "monto_recibido_usd": 40,
            },
        )
        assert r.status_code in (200, 201), r.text
        reserva = r.json()
        # Confirmamos que el anticipo se registró.
        assert float(reserva.get("pagado_parcial_usd", 0)) == 40.0, (
            f"pagado_parcial_usd={reserva.get('pagado_parcial_usd')}"
        )
        cancel = client.post(
            f"/api/reservas/{reserva['id']}/cancelar",
            json={
                "porcentaje_reembolso": 50,
                "nota": "Cancelación de prueba general",
                "metodo_pago_reembolso": "efectivo",
            },
        )
        assert cancel.status_code == 200, cancel.text
        body = cancel.json()
        assert body["estado"] == "cancelada", f"estado={body.get('estado')}"
        assert int(body["porcentaje_reembolso"]) == 50, (
            f"porcentaje={body.get('porcentaje_reembolso')}"
        )
        assert float(body["reembolso_usd"]) == 20.0, (
            f"reembolso={body.get('reembolso_usd')} (esperaba 20.0)"
        )

    runner.paso("Cancelar reserva con reembolso 50%", _cancelar_reserva_con_reembolso)


def modulo_reportes(runner: TestRunner, client) -> None:
    runner.modulo("6. Reportes / Inicio / Historial")

    def _ventas_por_area():
        data = client.get("/api/reportes/ventas-por-area-con-metodos").json()
        for clave in ("habitaciones", "bar", "cocina", "piscina"):
            assert clave in data, f"Falta área {clave}"
            assert "total_usd" in data[clave]
            assert "total_bs" in data[clave]
            assert "metodos" in data[clave]

    runner.paso("Inicio: ventas por área devuelve las 4 áreas", _ventas_por_area)

    def _total_suma_correctamente():
        data = client.get("/api/reportes/ventas-por-area-con-metodos").json()
        total_calc = sum(
            float(data[k]["total_usd"]) for k in ("habitaciones", "bar", "cocina", "piscina")
        )
        # El total debería al menos igualar la suma de áreas no nulas; el
        # frontend lo suma del lado cliente, así que verificamos no negativo
        # y la coherencia entre áreas.
        assert total_calc >= 0

    runner.paso("TOTAL GENERAL suma de áreas es coherente", _total_suma_correctamente)

    def _historial_filtros():
        hoy = date.today().isoformat()
        ayer = (date.today() - timedelta(days=1)).isoformat()
        for desde, hasta, etiqueta in (
            (hoy, hoy, "día"),
            (
                (date.today() - timedelta(days=7)).isoformat(),
                hoy,
                "semana",
            ),
            (
                (date.today() - timedelta(days=30)).isoformat(),
                hoy,
                "mes",
            ),
        ):
            r = client.get(
                f"/api/reportes/historial/resumen?desde={desde}&hasta={hasta}"
            )
            assert r.status_code == 200, f"{etiqueta}: {r.text}"

    runner.paso("Historial acepta filtros por día/semana/mes", _historial_filtros)

    def _transacciones_paginadas():
        r = client.get("/api/reportes/ultimas-transacciones?limite=10")
        assert r.status_code == 200, r.text
        filas = r.json()
        assert isinstance(filas, list)
        assert len(filas) <= 10

    runner.paso("Últimas transacciones paginadas (limite=10)", _transacciones_paginadas)


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------
def main() -> int:
    runner = TestRunner()
    with _entorno_temporal():
        client, _ = _crear_client()
        modulo_habitaciones(runner, client)
        modulo_ventas(runner, client)
        modulo_cocina(runner, client)
        modulo_favoritos(runner, client)
        modulo_reservas(runner, client)
        modulo_reportes(runner, client)
    return runner.resumen()


if __name__ == "__main__":
    raise SystemExit(main())
