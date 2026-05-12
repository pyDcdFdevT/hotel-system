/**
 * Pantalla de cocina con flujo por ítem.
 *
 * - Recarga automática cada 10s desde GET /api/pedidos/activos-cocina.
 * - Cada producto puede avanzar individualmente:
 *     pendiente → en_preparacion (botón 🔪 Iniciar)
 *     en_preparacion → listo     (botón ✅ Listo)
 * - Una vez todos los ítems están "listo" o "entregado", el pedido sale
 *   automáticamente del panel (el backend lo filtra).
 */
import {
  getToken,
  getUsuario,
  clearSession,
  redirectToLogin,
  formatTimeVE,
  nowVE,
} from "/static/js/api.js";

if (!getToken()) redirectToLogin();

const usuario = getUsuario();
document.getElementById("cocina-info").textContent = usuario
  ? `Sesión: ${usuario.nombre} · ${usuario.rol}`
  : "";

const REFRESH_MS = 10_000;
const HORA_TICK_MS = 30_000;
const INACTIVIDAD_MS = 30 * 60 * 1000;

const ESTADO_LABEL = {
  pendiente: "⏳ Pendiente",
  en_preparacion: "🔪 En preparación",
  listo: "✅ Listo",
  entregado: "✅✅ Entregado",
};

let ultimoPayload = [];

async function authFetch(url, options = {}) {
  const res = await fetch(url, {
    ...options,
    headers: {
      Authorization: `Bearer ${getToken()}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("No autenticado");
  }
  return res;
}

async function cargarPedidos() {
  try {
    const res = await authFetch("/api/pedidos/activos-cocina");
    if (!res.ok) {
      console.warn("Error cargando pedidos", res.status);
      return;
    }
    ultimoPayload = await res.json();
    renderPedidos(ultimoPayload);
  } catch (err) {
    console.warn("Error en cocina:", err);
  }
}

function renderPedidos(pedidos) {
  const cont = document.getElementById("pedidos-container");
  const vacio = document.getElementById("vacio");
  const resumen = document.getElementById("cocina-resumen");

  if (!pedidos.length) {
    cont.innerHTML = "";
    vacio.classList.remove("hidden");
    if (resumen) resumen.textContent = "Sin pendientes";
    return;
  }
  vacio.classList.add("hidden");

  const totalDetalles = pedidos.reduce(
    (acc, p) => acc + (p.detalles?.length || 0),
    0,
  );
  const enPrep = pedidos.reduce(
    (acc, p) =>
      acc + (p.detalles || []).filter((d) => d.estado === "en_preparacion").length,
    0,
  );
  if (resumen) {
    resumen.textContent = `${pedidos.length} pedido${
      pedidos.length === 1 ? "" : "s"
    } · ${totalDetalles} ítem${totalDetalles === 1 ? "" : "s"} · ${enPrep} en preparación`;
  }

  cont.innerHTML = pedidos.map(renderPedidoCard).join("");

  cont.querySelectorAll(".btn-cocina").forEach((btn) =>
    btn.addEventListener("click", () => {
      const pedidoId = Number(btn.dataset.pedidoId);
      const detalleId = Number(btn.dataset.detalleId);
      const estado = btn.dataset.estado;
      if (pedidoId && detalleId && estado) {
        marcarDetalle(pedidoId, detalleId, estado, btn);
      }
    }),
  );
}

function renderPedidoCard(p) {
  const titulo = p.mesa
    ? `Mesa ${p.mesa}`
    : p.habitacion_numero
      ? `🏨 Hab ${p.habitacion_numero}`
      : `#${p.id}`;
  // Color por tipo / categoría: si hay algún ítem de piscina lo destacamos.
  const tienePiscina = (p.detalles || []).some(
    (d) => (d.categoria || "").toLowerCase() === "piscina",
  );
  const cls = tienePiscina
    ? "piscina"
    : p.tipo === "bar"
      ? "bar"
      : "cocina";
  const filas = (p.detalles || []).map((d) => renderDetalle(p.id, d)).join("");
  return `
    <article class="ticket ${cls} rounded-lg shadow p-4">
      <div class="flex justify-between items-start mb-2">
        <div>
          <p class="text-lg font-bold">${escapeHtml(titulo)}</p>
          <p class="text-xs uppercase opacity-70">
            ${escapeHtml(p.tipo)} · ${escapeHtml(p.estado_cocina || "pendiente")}
          </p>
        </div>
        <p class="text-xs">${p.fecha ? formatTimeVE(p.fecha) : ""}</p>
      </div>
      <div class="text-sm">${filas}</div>
    </article>
  `;
}

function renderDetalle(pedidoId, d) {
  const estado = d.estado || "pendiente";
  // "entregado" no aparece en cocina (el backend lo filtra a nivel de pedido),
  // pero por seguridad lo mostramos opaco si llega aquí.
  if (estado === "entregado") return "";

  const acciones = [];
  if (estado === "pendiente") {
    acciones.push(
      `<button class="btn-cocina btn-iniciar"
         data-pedido-id="${pedidoId}"
         data-detalle-id="${d.id}"
         data-estado="en_preparacion">🔪 Iniciar</button>`,
    );
    acciones.push(
      `<button class="btn-cocina btn-listo"
         data-pedido-id="${pedidoId}"
         data-detalle-id="${d.id}"
         data-estado="listo">✅ Listo</button>`,
    );
  } else if (estado === "en_preparacion") {
    acciones.push(
      `<button class="btn-cocina btn-listo"
         data-pedido-id="${pedidoId}"
         data-detalle-id="${d.id}"
         data-estado="listo">✅ Listo</button>`,
    );
  }

  const meta =
    d.area && d.area !== "general"
      ? ` <span class="text-xs text-slate-500">(${escapeHtml(d.area)})</span>`
      : "";
  return `
    <div class="detalle-row estado-${estado}">
      <div>
        <div>
          <strong>${formatCantidad(d.cantidad)}× ${escapeHtml(d.producto_nombre)}</strong>${meta}
        </div>
        <span class="detalle-estado badge-${estado}">
          ${ESTADO_LABEL[estado] || estado}
        </span>
      </div>
      <div class="flex gap-1 flex-wrap justify-end">${acciones.join("")}</div>
    </div>
  `;
}

async function marcarDetalle(pedidoId, detalleId, estado, btn) {
  btn.disabled = true;
  try {
    const res = await authFetch(
      `/api/pedidos/${pedidoId}/detalles/${detalleId}/estado`,
      {
        method: "PUT",
        body: JSON.stringify({ estado }),
      },
    );
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      console.warn("Error marcando detalle", res.status, body);
    }
  } catch (err) {
    console.warn(err);
  } finally {
    btn.disabled = false;
  }
  await cargarPedidos();
}

function formatCantidad(c) {
  const n = Number(c || 0);
  if (Number.isInteger(n)) return String(n);
  return n.toFixed(2);
}

function escapeHtml(v) {
  if (v == null) return "";
  return String(v)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

document.getElementById("btn-logout").addEventListener("click", () => {
  fetch("/api/auth/logout", {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
  }).finally(() => {
    clearSession();
    redirectToLogin();
  });
});

function tickHora() {
  document.getElementById("cocina-hora").textContent = nowVE();
}

cargarPedidos();
tickHora();
setInterval(cargarPedidos, REFRESH_MS);
setInterval(tickHora, HORA_TICK_MS);

// Auto-logout por inactividad.
let inactividadTimer;
function resetInactividad() {
  clearTimeout(inactividadTimer);
  inactividadTimer = setTimeout(() => {
    clearSession();
    redirectToLogin();
  }, INACTIVIDAD_MS);
}
["click", "mousemove", "keypress", "touchstart"].forEach((evt) =>
  document.addEventListener(evt, resetInactividad, { passive: true }),
);
resetInactividad();
