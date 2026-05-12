# Hotel Management System

Sistema integral de gestión hotelera construido con FastAPI + SQLAlchemy + SQLite.

## Funcionalidades

- **Habitaciones**: CRUD, control de estado (disponible / ocupada / limpieza / mantenimiento / bloqueada).
- **Reservas**: check-in, check-out con factura final (tarifa + consumos en Bs y USD).
- **POS (restaurante / bar / habitación)**: pedidos con descuento automático de inventario por recetas, pago en Bs / USD / mixto con cálculo de vuelto, o "cargo a habitación".
- **Inventario**: productos con stock, recetas (producto compuesto descuenta sus ingredientes), movimientos auditables, alertas de bajo stock.
- **Gastos**: registro por categoría, afectación automática de saldo de cuenta banco.
- **Personal**: empleados y pagos de nómina.
- **Cuentas banco**: BcoVen, BcoHLC, BcoP, BcoZ, EfectivoBs, EfectivoUsd con histórico de movimientos.
- **Reportes**: `GET /api/reportes/resumen-dia` (ventas, gastos, ocupación, bajo stock).
- **Tasa de cambio**: USD↔Bs por fecha; fallback 405.35.

## Tecnologías

- Python 3.12 · FastAPI 0.115 · SQLAlchemy 2 · Pydantic 2
- SQLite por defecto (con soporte opcional para Postgres vía `HOTEL_DB_URL`)
- Frontend SPA con Tailwind CDN servido desde `/static`

## Estructura

```
hotel-system/
├── app/
│   ├── main.py             FastAPI + montaje de routers y /static
│   ├── database.py         SQLAlchemy engine + get_db()
│   ├── models.py           16 tablas (habitaciones, reservas, pedidos, ...)
│   ├── schemas.py          Pydantic v2
│   ├── seed.py             Datos iniciales (idempotente)
│   ├── routers/            10 routers (/api/...)
│   ├── services/           inventario_service, tasa_service
│   └── static/             index.html, css/, js/
├── tests/                  pytest smoke tests
├── prestart.sh             create_all + seed condicional
├── railway.toml            build + start + healthcheck
├── requirements.txt
└── .env.example
```

## Desarrollo local

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

Abre http://localhost:8000

## Tests

```bash
pytest -q
```

## Despliegue en Railway

1. Crea un proyecto y conéctalo a este repo.
2. Railway leerá `railway.toml`. Verifica que:
   - `startCommand` ejecute `prestart.sh` antes de uvicorn (ya configurado).
   - `healthcheckPath` apunte a `/api/health` (ya configurado).
3. Para que la base sobreviva reinicios, añade un **Volume** montado en `/data` y crea la variable `HOTEL_DB_URL=sqlite:////data/hotel.db`.
4. (Opcional) Para producción, agrega un servicio Postgres en Railway y usa su `DATABASE_URL` como `HOTEL_DB_URL` (recuerda añadir `psycopg2-binary` a `requirements.txt`).

## Variables de entorno

Ver `.env.example`:

| Variable | Default | Descripción |
|---|---|---|
| `HOTEL_DB_URL` | `sqlite:///./hotel.db` | URL de SQLAlchemy. |
| `SEED_ONLY_IF_EMPTY` | `0` | Si vale `1`, el seed no toca una BD que ya tenga habitaciones. |
| `PORT` | `8000` | Puerto del servidor uvicorn. |

## Endpoints principales

- `GET /api/health`
- `GET /api/tasa/actual`
- `GET|POST|PUT|DELETE /api/habitaciones/...`
- `POST /api/reservas/`, `PUT /api/reservas/{id}/checkout`, `GET /api/reservas/activas`
- `POST /api/pedidos/`, `POST /api/pedidos/{id}/pagar`, `PUT /api/pedidos/{id}/cargo-habitacion`, `GET /api/pedidos/activos`
- `GET /api/inventario/movimientos`, `GET /api/inventario/bajo-stock`, `POST /api/inventario/movimientos`
- `GET|POST /api/gastos/`, `GET /api/gastos/categorias`
- `GET /api/reportes/resumen-dia`

Swagger interactivo en `/docs`.
