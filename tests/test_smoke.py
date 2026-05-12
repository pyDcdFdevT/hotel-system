from __future__ import annotations


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hotel-system"}


def test_tasa_default(client):
    response = client.get("/api/tasa/actual")
    assert response.status_code == 200
    body = response.json()
    assert float(body["bcv"]) > 0
    assert float(body["paralelo"]) > 0


def test_tasa_actualizar_bcv_y_paralelo(client):
    resp_bcv = client.post("/api/tasa/bcv", json={"usd_a_ves": 410.5})
    assert resp_bcv.status_code == 201, resp_bcv.text
    assert resp_bcv.json()["tipo"] == "bcv"

    resp_par = client.post("/api/tasa/paralelo", json={"usd_a_ves": 421.75})
    assert resp_par.status_code == 201, resp_par.text
    assert resp_par.json()["tipo"] == "paralelo"

    actual = client.get("/api/tasa/actual").json()
    assert float(actual["bcv"]) == 410.5
    assert float(actual["paralelo"]) == 421.75


def test_pago_movil_paga_pedido(client):
    productos = client.get("/api/productos/").json()
    agua = next(p for p in productos if p["nombre"] == "Agua")

    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "items": [{"producto_id": agua["id"], "cantidad": 1}]},
    ).json()
    assert pedido["estado"] == "abierto"

    pago = client.post(
        f"/api/pedidos/{pedido['id']}/pagar",
        json={"metodo_pago": "pagomovil", "tasa_tipo": "bcv"},
    )
    assert pago.status_code == 200, pago.text
    body = pago.json()
    assert body["estado"] == "pagado"
    assert body["metodo_pago"] == "pagomovil"


def test_productos_crud_editar_y_eliminar(client):
    creado = client.post(
        "/api/productos/",
        json={
            "nombre": "Producto Test CRUD",
            "categoria": "general",
            "precio_bs": 100,
            "precio_usd": 1,
        },
    )
    assert creado.status_code == 201, creado.text
    pid = creado.json()["id"]

    actualizado = client.put(
        f"/api/productos/{pid}",
        json={"precio_bs": 200, "precio_usd": 2},
    )
    assert actualizado.status_code == 200
    assert float(actualizado.json()["precio_bs"]) == 200

    eliminado = client.delete(f"/api/productos/{pid}")
    assert eliminado.status_code == 200
    payload = eliminado.json()
    assert payload["borrado"] is True


def test_bancos_renombrados_en_seed(client):
    cuentas = client.get("/api/cuentas/").json()
    nombres = {c["nombre"] for c in cuentas}
    for esperado in ["Banco HLC", "Banco Z", "Efectivo Bs", "Efectivo USD"]:
        assert esperado in nombres, f"Falta banco {esperado} en {nombres}"


def test_habitaciones_seed(client):
    response = client.get("/api/habitaciones/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    numeros = sorted(int(h["numero"]) for h in data)
    assert numeros == list(range(101, 111))


def test_resumen_dia(client):
    response = client.get("/api/reportes/resumen-dia")
    assert response.status_code == 200
    body = response.json()
    assert body["habitaciones_totales"] == 10
    assert body["habitaciones_ocupadas"] == 0


def test_flujo_pedido_con_receta_y_pago_mixto(client):
    productos = client.get("/api/productos/").json()
    hamburguesa = next(p for p in productos if p["nombre"] == "Hamburguesa")
    pan_stock_inicial = float(next(p for p in productos if p["nombre"] == "Pan hamburguesa")["stock_actual"])

    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "items": [{"producto_id": hamburguesa["id"], "cantidad": 2}]},
    ).json()
    assert float(pedido["total_usd"]) == 16.0

    pago = client.post(
        f"/api/pedidos/{pedido['id']}/pagar",
        json={"metodo_pago": "mixto", "monto_bs": 2000, "monto_usd": 12},
    )
    assert pago.status_code == 200, pago.text
    body = pago.json()
    assert body["estado"] == "pagado"

    productos2 = client.get("/api/productos/").json()
    pan_despues = float(next(p for p in productos2 if p["nombre"] == "Pan hamburguesa")["stock_actual"])
    assert pan_despues == pan_stock_inicial - 2
