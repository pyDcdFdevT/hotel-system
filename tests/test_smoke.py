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
    agua = next(p for p in productos if p["nombre"] == "Agua Mineral")

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


def test_agregar_items_a_pedido_existente(client):
    productos = client.get("/api/productos/").json()
    p1 = next(p for p in productos if p["nombre"] == "Mojito")
    p2 = next(p for p in productos if p["nombre"] == "Tequeños")

    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "mesa": "Mesa 7",
              "items": [{"producto_id": p1["id"], "cantidad": 1}]},
    ).json()
    assert pedido["estado"] == "abierto"
    total_inicial = float(pedido["total_usd"])

    agregado = client.post(
        f"/api/pedidos/{pedido['id']}/agregar",
        json={"tipo": pedido["tipo"], "items": [{"producto_id": p2["id"], "cantidad": 2}]},
    )
    assert agregado.status_code == 200, agregado.text
    body = agregado.json()
    assert float(body["total_usd"]) > total_inicial
    # 2 detalles: Mojito + Tequeños
    assert len(body["detalles"]) == 2


def test_productos_favoritos(client):
    # Fuerza una venta para que aparezca en favoritos.
    productos = client.get("/api/productos/").json()
    cerveza = next(p for p in productos if p["nombre"] == "Cerveza Solera")
    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "bar", "mesa": "Barra",
              "items": [{"producto_id": cerveza["id"], "cantidad": 5}]},
    ).json()
    client.post(
        f"/api/pedidos/{pedido['id']}/pagar",
        json={"metodo_pago": "usd", "monto_usd": 7.5},
    )

    resp = client.get("/api/productos/favoritos?limit=5")
    assert resp.status_code == 200, resp.text
    favs = resp.json()
    assert len(favs) > 0
    nombres = [p["nombre"] for p in favs]
    assert "Cerveza Solera" in nombres


def test_pedidos_activos_agrupados(client):
    productos = client.get("/api/productos/").json()
    p1 = next(p for p in productos if p["nombre"] == "Papas Francesas")
    client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "mesa": "Mesa 1",
              "items": [{"producto_id": p1["id"], "cantidad": 1}]},
    )
    client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "mesa": "Mesa 2",
              "items": [{"producto_id": p1["id"], "cantidad": 1}]},
    )
    activos = client.get("/api/pedidos/activos").json()
    mesas = [p.get("mesa") for p in activos if p.get("estado") == "abierto"]
    assert "Mesa 1" in mesas
    assert "Mesa 2" in mesas


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
    hamburguesa = next(p for p in productos if p["nombre"] == "Hamburguesa Clásica")
    pan_stock_inicial = float(next(p for p in productos if p["nombre"] == "Pan hamburguesa")["stock_actual"])

    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "items": [{"producto_id": hamburguesa["id"], "cantidad": 2}]},
    ).json()
    # Hamburguesa Clásica cuesta USD 5 → 2 unidades = USD 10.
    assert float(pedido["total_usd"]) == 10.0

    pago = client.post(
        f"/api/pedidos/{pedido['id']}/pagar",
        json={"metodo_pago": "mixto", "monto_bs": 2000, "monto_usd": 6},
    )
    assert pago.status_code == 200, pago.text
    body = pago.json()
    assert body["estado"] == "pagado"

    productos2 = client.get("/api/productos/").json()
    pan_despues = float(next(p for p in productos2 if p["nombre"] == "Pan hamburguesa")["stock_actual"])
    assert pan_despues == pan_stock_inicial - 2


def test_ventas_por_area(client):
    productos = client.get("/api/productos/").json()
    mojito = next(p for p in productos if p["nombre"] == "Mojito")
    tequenos = next(p for p in productos if p["nombre"] == "Tequeños")

    pedido_bar = client.post(
        "/api/pedidos/",
        json={"tipo": "bar", "items": [{"producto_id": mojito["id"], "cantidad": 2}]},
    ).json()
    client.post(
        f"/api/pedidos/{pedido_bar['id']}/pagar",
        json={"metodo_pago": "usd", "monto_usd": 12},
    )

    pedido_cocina = client.post(
        "/api/pedidos/",
        json={"tipo": "restaurante", "items": [{"producto_id": tequenos["id"], "cantidad": 1}]},
    ).json()
    client.post(
        f"/api/pedidos/{pedido_cocina['id']}/pagar",
        json={"metodo_pago": "usd", "monto_usd": 6},
    )

    resp = client.get("/api/reportes/ventas-por-area")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    areas = {a["area"]: a for a in data["areas"]}
    # Bar incluye Mojito x2 (USD 12) más cualquier venta previa de otros tests.
    assert float(areas["bar"]["ventas_usd"]) >= 12.0
    assert float(areas["cocina"]["ventas_usd"]) >= 6.0
    assert float(data["total_usd"]) >= 18.0


def test_habitaciones_precio_actualizado(client):
    habs = client.get("/api/habitaciones/").json()
    assert all(float(h["precio_usd"]) == 20.0 for h in habs)


def test_menu_completo_seed(client):
    productos = client.get("/api/productos/").json()
    nombres = {p["nombre"] for p in productos}
    esperados = [
        "Tequeños",
        "Papas Francesas",
        "Sandwich",
        "Hamburguesa Clásica",
        "Parrilla de Lomito P1",
        "Parrilla de Lomito P2",
        "Mojito",
        "Whisky Black and White",
        "Ron Estelar 1L",
    ]
    for nombre in esperados:
        assert nombre in nombres, f"Falta producto del menú: {nombre}"
    # Verifica que el área del producto se haya seteado correctamente.
    mojito = next(p for p in productos if p["nombre"] == "Mojito")
    assert mojito["area"] == "bar"
    tequenos = next(p for p in productos if p["nombre"] == "Tequeños")
    assert tequenos["area"] == "cocina"
