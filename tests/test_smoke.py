from __future__ import annotations


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "hotel-system"}


# ---------------------------------------------------------------------------
# Auth / Roles
# ---------------------------------------------------------------------------
def test_login_correcto(anon_client):
    resp = anon_client.post("/api/auth/login", json={"pin": "1234"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["usuario"]["rol"] == "admin"
    assert body["token"]

    # /me funciona con ese token.
    me = anon_client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert me.status_code == 200
    assert me.json()["nombre"] == "Administrador"


def test_login_incorrecto(anon_client):
    resp = anon_client.post("/api/auth/login", json={"pin": "0000"})
    assert resp.status_code == 401
    # Log de intento fallido (lo lee admin).
    admin = anon_client.post("/api/auth/login", json={"pin": "1234"}).json()
    logs = anon_client.get(
        "/api/auth/logs",
        headers={"Authorization": f"Bearer {admin['token']}"},
    ).json()
    fallidos = [log for log in logs if log["accion"] == "login" and not log["exitoso"]]
    assert fallidos, "Esperaba al menos un log de login fallido"


def test_proteccion_rutas(anon_client):
    # Sin token: 401 en cualquier ruta protegida.
    sin_token = anon_client.get("/api/habitaciones/")
    assert sin_token.status_code == 401

    # Login como mesero.
    token = anon_client.post("/api/auth/login", json={"pin": "2222"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Mesero puede leer pedidos pero NO inventario.
    assert anon_client.get("/api/pedidos/activos", headers=headers).status_code == 200
    inv = anon_client.get("/api/inventario/movimientos", headers=headers)
    assert inv.status_code == 403

    # Mesero NO puede crear productos.
    nuevo = anon_client.post(
        "/api/productos/",
        json={
            "nombre": "Test Mesero",
            "categoria": "Otros",
            "precio_bs": 1,
            "precio_usd": 1,
        },
        headers=headers,
    )
    assert nuevo.status_code == 403


def test_cocina_pedidos(anon_client):
    # Admin crea un pedido con un producto de cocina.
    admin_token = anon_client.post("/api/auth/login", json={"pin": "1234"}).json()["token"]
    admin = {"Authorization": f"Bearer {admin_token}"}
    productos = anon_client.get("/api/productos/", headers=admin).json()
    pan = next(p for p in productos if p["nombre"] == "Tequeños")
    pedido = anon_client.post(
        "/api/pedidos/",
        json={
            "tipo": "restaurante",
            "mesa": "Cocina Test",
            "items": [{"producto_id": pan["id"], "cantidad": 1}],
        },
        headers=admin,
    ).json()
    assert pedido["estado_cocina"] == "pendiente"

    # Cocina lee la cola.
    cocina_token = anon_client.post("/api/auth/login", json={"pin": "3333"}).json()["token"]
    cocina = {"Authorization": f"Bearer {cocina_token}"}
    cola = anon_client.get("/api/pedidos/activos-cocina", headers=cocina)
    assert cola.status_code == 200
    ids = [p["id"] for p in cola.json()]
    assert pedido["id"] in ids

    # Cocina NO puede entrar a reportes (rol distinto).
    rep = anon_client.get("/api/reportes/resumen-dia", headers=cocina)
    assert rep.status_code == 403

    # Cocina marca el pedido como listo.
    listo = anon_client.put(
        f"/api/pedidos/{pedido['id']}/cocina-estado",
        json={"estado_cocina": "listo"},
        headers=cocina,
    )
    assert listo.status_code == 200
    assert listo.json()["estado_cocina"] == "listo"

    # Tras marcar listo, ya no aparece en pendientes.
    cola2 = anon_client.get("/api/pedidos/activos-cocina", headers=cocina).json()
    assert pedido["id"] not in [p["id"] for p in cola2]


def test_logout_invalida_token(anon_client):
    token = anon_client.post("/api/auth/login", json={"pin": "1234"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert anon_client.get("/api/auth/me", headers=headers).status_code == 200
    anon_client.post("/api/auth/logout", headers=headers)
    assert anon_client.get("/api/auth/me", headers=headers).status_code == 401


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


def test_habitaciones_24(client):
    habs = client.get("/api/habitaciones/").json()
    numeros = sorted(h["numero"] for h in habs)
    esperados = sorted(
        [str(n) for n in list(range(101, 112))
                        + list(range(201, 211))
                        + list(range(301, 304))]
    )
    assert len(habs) >= 24
    for numero in esperados:
        assert numero in numeros, f"Falta habitación {numero}"


def test_estados_habitaciones(client):
    habs = client.get("/api/habitaciones/").json()
    disponibles = {h["numero"] for h in habs if h["estado"] == "disponible"}
    inhabilitadas = {h["numero"] for h in habs if h["estado"] == "inhabilitada"}
    for n in range(101, 112):
        assert str(n) in disponibles
    for n in list(range(201, 211)) + list(range(301, 304)):
        assert str(n) in inhabilitadas

    # Cambiar estado vía PUT /habitaciones/{id}/estado
    objetivo = next(h for h in habs if h["numero"] == "101")
    resp = client.put(
        f"/api/habitaciones/{objetivo['id']}/estado",
        json={"estado": "limpieza"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["estado"] == "limpieza"

    # Devolver a disponible para no romper siguientes tests.
    client.put(
        f"/api/habitaciones/{objetivo['id']}/estado",
        json={"estado": "disponible"},
    )


def test_entradas_piscina_seed(client):
    productos = client.get("/api/productos/").json()
    piscina = [p for p in productos if p["categoria"] == "Piscina"]
    nombres = {p["nombre"]: p for p in piscina}
    assert "Entrada Piscina - Niño" in nombres
    assert "Entrada Piscina - Adulto" in nombres
    assert float(nombres["Entrada Piscina - Niño"]["precio_usd"]) == 3.00
    assert float(nombres["Entrada Piscina - Adulto"]["precio_usd"]) == 4.00
    # Stock virtual alto.
    for p in piscina:
        assert float(p["stock_actual"]) >= 999
        assert p["area"] == "bar"


def test_checkin_cotizacion(client):
    habs = client.get("/api/habitaciones/").json()
    libre = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "104")
    # 3 noches BCV.
    cot = client.get(
        f"/api/habitaciones/{libre['id']}/checkin-cotizacion",
        params={"noches": 3, "tasa_tipo": "bcv"},
    )
    assert cot.status_code == 200, cot.text
    body = cot.json()
    assert body["noches"] == 3
    assert float(body["precio_unit_usd"]) == 20.00
    assert float(body["total_usd"]) == 60.00
    # total_bs = 60 * tasa BCV
    assert float(body["total_bs"]) == round(60.00 * float(body["tasa_aplicada"]), 2)


def test_checkout_moneda_pago_usd_y_bs(client):
    # Reservar dos habitaciones distintas para evitar conflictos.
    habs = client.get("/api/habitaciones/").json()
    hab_usd = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "105")
    hab_bs = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "106")

    # ---- Caso 1: pago en USD (sin tasa) ----
    client.post(
        f"/api/habitaciones/{hab_usd['id']}/checkin",
        json={"huesped": "Pago Dólares", "noches": 1},
    )
    resp = client.post(
        f"/api/habitaciones/{hab_usd['id']}/checkout",
        json={"moneda_pago": "usd"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert float(body["total_usd"]) == 20.00
    # tasa_tipo se mantiene en bcv pero el cobro es 100% USD.

    # ---- Caso 2: pago en Bs con tasa paralelo ----
    client.post(
        f"/api/habitaciones/{hab_bs['id']}/checkin",
        json={"huesped": "Pago Bolívares", "noches": 2},
    )
    resp = client.post(
        f"/api/habitaciones/{hab_bs['id']}/checkout",
        json={"moneda_pago": "bs", "tasa_tipo": "paralelo"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tasa_tipo"] == "paralelo"
    # total_bs = 40 USD * tasa paralelo (415 según seed)
    esperado_bs = round(40.00 * float(body["tasa_aplicada"]), 2)
    assert float(body["total_bs"]) == esperado_bs


def test_checkin_checkout(client):
    habs = client.get("/api/habitaciones/").json()
    libre = next(
        h for h in habs if h["estado"] == "disponible" and h["numero"] == "102"
    )

    # Check-in con datos opcionales del vehículo.
    resp = client.post(
        f"/api/habitaciones/{libre['id']}/checkin",
        json={
            "huesped": "Pedro Pérez",
            "documento": "V-12345678",
            "noches": 2,
            "vehiculo_modelo": "Toyota Corolla",
            "vehiculo_color": "Blanco",
            "vehiculo_placa": "AB123CD",
        },
    )
    assert resp.status_code == 200, resp.text
    reserva = resp.json()
    assert reserva["estado"] == "activa"
    assert reserva["noches"] == 2
    assert reserva["vehiculo_modelo"] == "Toyota Corolla"
    assert reserva["vehiculo_color"] == "Blanco"
    assert reserva["vehiculo_placa"] == "AB123CD"

    # Habitación debe estar ocupada.
    detalle = client.get(f"/api/habitaciones/{libre['id']}").json()
    assert detalle["estado"] == "ocupada"

    # No se permite check-in duplicado.
    dup = client.post(
        f"/api/habitaciones/{libre['id']}/checkin",
        json={"huesped": "Otro", "noches": 1},
    )
    assert dup.status_code == 400

    # Crear un pedido contra la habitación para que tenga consumos.
    productos = client.get("/api/productos/").json()
    cerveza = next(p for p in productos if p["nombre"] == "Cerveza Solera")
    client.post(
        "/api/pedidos/",
        json={
            "tipo": "habitacion",
            "habitacion_numero": "102",
            "items": [{"producto_id": cerveza["id"], "cantidad": 2}],
        },
    )

    # Preview del checkout: debe incluir estadía + consumos.
    preview = client.get(f"/api/habitaciones/{libre['id']}/checkout-preview").json()
    assert float(preview["tarifa_usd"]) > 0
    assert float(preview["consumos_usd"]) > 0
    assert len(preview["pedidos"]) == 1

    # Check-out.
    resp_out = client.post(
        f"/api/habitaciones/{libre['id']}/checkout",
        json={"moneda_pago": "usd"},
    )
    assert resp_out.status_code == 200, resp_out.text

    # Habitación → limpieza, reserva cerrada, pedido pagado.
    assert (
        client.get(f"/api/habitaciones/{libre['id']}").json()["estado"] == "limpieza"
    )
    abiertos = client.get("/api/pedidos/por-habitacion/102").json()
    assert abiertos == []


def test_pedido_con_habitacion_numero(client):
    # Habitación inhabilitada NO acepta consumos.
    productos = client.get("/api/productos/").json()
    cerveza = next(p for p in productos if p["nombre"] == "Cerveza Solera")
    bloqueado = client.post(
        "/api/pedidos/",
        json={
            "tipo": "habitacion",
            "habitacion_numero": "201",  # inhabilitada
            "items": [{"producto_id": cerveza["id"], "cantidad": 1}],
        },
    )
    assert bloqueado.status_code == 400

    # Habitación disponible (sin check-in) sí acepta.
    resp = client.post(
        "/api/pedidos/",
        json={
            "tipo": "habitacion",
            "habitacion_numero": "103",
            "items": [{"producto_id": cerveza["id"], "cantidad": 1}],
        },
    )
    assert resp.status_code == 201, resp.text
    pedido = resp.json()
    assert pedido["habitacion_numero"] == "103"

    listado = client.get("/api/pedidos/por-habitacion/103").json()
    assert any(p["id"] == pedido["id"] for p in listado)


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
    assert len(data) >= 24
    numeros = {int(h["numero"]) for h in data}
    for n in list(range(101, 112)) + list(range(201, 211)) + list(range(301, 304)):
        assert n in numeros


def test_resumen_dia(client):
    response = client.get("/api/reportes/resumen-dia")
    assert response.status_code == 200
    body = response.json()
    assert body["habitaciones_totales"] >= 24
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


def test_checkin_hora_ingreso(client):
    """El check-in acepta hora_ingreso opcional y la persiste en la reserva."""
    habs = client.get("/api/habitaciones/").json()
    libre = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "109")
    resp = client.post(
        f"/api/habitaciones/{libre['id']}/checkin",
        json={
            "huesped": "Cliente Hora",
            "noches": 1,
            "hora_ingreso": "15:30",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["hora_ingreso"] == "15:30"


def test_checkout_horas_extra(client):
    """Salida 15:30 → 3 horas extra (ceil((2.5))) × $5 = $15 de recargo."""
    habs = client.get("/api/habitaciones/").json()
    hab = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "110")
    client.post(
        f"/api/habitaciones/{hab['id']}/checkin",
        json={"huesped": "Late Checkout", "noches": 1},
    )

    # Preview con hora_salida tarde.
    preview = client.get(
        f"/api/habitaciones/{hab['id']}/checkout-preview",
        params={"hora_salida": "15:30"},
    ).json()
    assert preview["horas_extra"] == 3
    assert float(preview["recarga_extra_usd"]) == 15.00
    # Total = tarifa $20 + recarga $15 = $35
    assert float(preview["total_usd"]) == 35.00

    # Preview con hora estándar: sin recargo.
    preview_std = client.get(
        f"/api/habitaciones/{hab['id']}/checkout-preview",
        params={"hora_salida": "13:00"},
    ).json()
    assert preview_std["horas_extra"] == 0
    assert float(preview_std["recarga_extra_usd"]) == 0
    assert float(preview_std["total_usd"]) == 20.00

    # Cierre con hora 14:00 (1h extra → $5).
    resp = client.post(
        f"/api/habitaciones/{hab['id']}/checkout",
        json={"opcion_pago": "efectivo_usd", "hora_salida": "14:00"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["horas_extra"] == 1
    assert float(body["recarga_extra_usd"]) == 5.00
    assert float(body["total_usd"]) == 25.00


def test_checkout_opcion_pago_unificada(client, anon_client):
    """El frontend envía ``opcion_pago``; backend mapea a moneda+método."""
    habs = client.get("/api/habitaciones/").json()
    # Opción "transferencia_bs" sobre la 107.
    hab_tx = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "107")
    client.post(
        f"/api/habitaciones/{hab_tx['id']}/checkin",
        json={"huesped": "Cliente Transf.", "noches": 1},
    )
    resp = client.post(
        f"/api/habitaciones/{hab_tx['id']}/checkout",
        json={"opcion_pago": "transferencia_bs", "tasa_tipo": "bcv"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tasa_tipo"] == "bcv"
    assert float(body["total_bs"]) > 0
    # Reserva queda con estado cerrada y método transferencia.
    # (Lo verificamos indirectamente por habitacion en limpieza.)
    assert (
        client.get(f"/api/habitaciones/{hab_tx['id']}").json()["estado"] == "limpieza"
    )

    # Opción "mixto" sobre la 108: paga $10 USD y el resto en Bs.
    hab_mix = next(h for h in habs if h["estado"] == "disponible" and h["numero"] == "108")
    client.post(
        f"/api/habitaciones/{hab_mix['id']}/checkin",
        json={"huesped": "Cliente Mixto", "noches": 2},
    )
    resp_mix = client.post(
        f"/api/habitaciones/{hab_mix['id']}/checkout",
        json={
            "opcion_pago": "mixto",
            "tasa_tipo": "paralelo",
            "monto_recibido_usd": 10,
        },
    )
    assert resp_mix.status_code == 200, resp_mix.text
    body_mix = resp_mix.json()
    # Total estadía = 2 * 20 = 40 USD. Recibió 10 USD → faltan 30 USD * paralelo.
    esperado_bs = round(30.00 * float(body_mix["tasa_aplicada"]), 2)
    assert float(body_mix["total_usd"]) == 10.00
    assert float(body_mix["total_bs"]) == esperado_bs


def test_ultimas_transacciones(client):
    # Generamos un pedido pagado para que aparezca en el historial.
    productos = client.get("/api/productos/").json()
    agua = next(p for p in productos if p["nombre"] == "Agua Mineral")
    pedido = client.post(
        "/api/pedidos/",
        json={"tipo": "bar", "mesa": "Test TX",
              "items": [{"producto_id": agua["id"], "cantidad": 1}]},
    ).json()
    client.post(
        f"/api/pedidos/{pedido['id']}/pagar",
        json={"metodo_pago": "usd", "monto_usd": 5},
    )

    resp = client.get("/api/reportes/ultimas-transacciones?limite=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) > 0
    fila = body[0]
    for key in ("id", "fecha", "concepto", "monto_usd", "monto_bs", "tipo", "usuario_nombre"):
        assert key in fila, f"Falta campo {key} en respuesta"


def test_ultimas_transacciones_mesero_accede(anon_client):
    """El mesero también consume el endpoint (lo usa el dashboard si tuviera acceso)."""
    token = anon_client.post("/api/auth/login", json={"pin": "2222"}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    resp = anon_client.get(
        "/api/reportes/ultimas-transacciones?limite=5", headers=headers
    )
    assert resp.status_code == 200, resp.text
    # En cambio, no puede ver resumen-dia.
    res = anon_client.get("/api/reportes/resumen-dia", headers=headers)
    assert res.status_code == 403


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
