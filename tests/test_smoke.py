from __future__ import annotations


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hotel-system"}


def test_tasa_default(client):
    response = client.get("/api/tasa/actual")
    assert response.status_code == 200
    body = response.json()
    assert float(body["usd_a_ves"]) > 0


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
