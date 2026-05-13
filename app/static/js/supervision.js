import { del, formatFechaHoraVe, get, getUsuario, showToast } from "./api.js";

let intervaloRefresco = null;
let inicializado = false;

const els = {
  cocina: () => document.getElementById("supervision-cocina"),
  bar: () => document.getElementById("supervision-bar"),
  countCocina: () => document.getElementById("supervision-count-cocina"),
  countBar: () => document.getElementById("supervision-count-bar"),
  actualizado: () => document.getElementById("supervision-actualizado"),
  btnRefresh: () => document.getElementById("btn-supervision-refresh"),
};

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function badgeEstado(estado) {
  if (estado === "en_preparacion") {
    return `<span class="supervision-badge supervision-badge-prep">🔪 En preparación</span>`;
  }
  return `<span class="supervision-badge supervision-badge-pend">⏳ Pendiente</span>`;
}

function renderPedidoCard(pedido, area) {
  const ref = pedido.mesa
    ? `Mesa ${pedido.mesa}`
    : pedido.habitacion_numero
      ? `Hab. ${pedido.habitacion_numero}`
      : `Pedido #${pedido.id}`;
  const detalles = (pedido.detalles || [])
    .map(
      (d) => `
      <li class="supervision-item-row">
        <span><strong>${Number(d.cantidad || 0)}x</strong> ${escapeHtml(d.producto || "-")}</span>
        ${badgeEstado((d.estado || "pendiente").toLowerCase())}
      </li>
    `,
    )
    .join("");
  return `
    <article class="supervision-card supervision-card-${area}">
      <div class="supervision-card-head">
        <div>
          <p class="supervision-card-title">${escapeHtml(ref)}</p>
          <p class="text-xs text-slate-500">Pedido #${pedido.id}</p>
        </div>
        <span class="text-xs text-slate-500">${pedido.creado_en ? formatFechaHoraVe(pedido.creado_en) : "-"}</span>
      </div>
      <ul class="supervision-items">${detalles}</ul>
      <div class="supervision-card-foot">
        <span class="text-xs text-slate-600">Pendientes: ${Number(pedido.total_pendientes || 0)}</span>
        <button
          type="button"
          class="btn-supervision-cancel"
          data-id="${pedido.id}"
          title="Cancelar pedido"
        >🗑️ Cancelar pedido</button>
      </div>
    </article>
  `;
}

function renderArea(area, pedidos) {
  const cont = area === "cocina" ? els.cocina() : els.bar();
  if (!cont) return;
  if (!pedidos?.length) {
    cont.innerHTML = `<div class="empty-state">Sin pedidos activos en ${area}.</div>`;
    return;
  }
  cont.innerHTML = pedidos.map((p) => renderPedidoCard(p, area)).join("");
}

function bindCancelarHandlers() {
  document.querySelectorAll(".btn-supervision-cancel").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const pedidoId = Number(btn.dataset.id);
      if (!pedidoId) return;
      const motivo = window.prompt("Motivo de cancelación (opcional):", "") || "";
      if (!window.confirm(`¿Cancelar el pedido #${pedidoId}?`)) return;
      try {
        const qs = motivo.trim()
          ? `?motivo=${encodeURIComponent(motivo.trim())}`
          : "";
        await del(`/pedidos/${pedidoId}/cancelar${qs}`);
        showToast(`Pedido #${pedidoId} cancelado`, "success");
        await cargarDatos();
      } catch (error) {
        showToast(`Error cancelando pedido: ${error.message}`, "error");
      }
    });
  });
}

async function cargarDatos() {
  try {
    const data = await get("/pedidos/supervision");
    const cocina = data?.cocina || [];
    const bar = data?.bar || [];
    if (els.countCocina()) els.countCocina().textContent = String(cocina.length);
    if (els.countBar()) els.countBar().textContent = String(bar.length);
    renderArea("cocina", cocina);
    renderArea("bar", bar);
    bindCancelarHandlers();
    if (els.actualizado()) {
      els.actualizado().textContent = `Actualizado ${formatFechaHoraVe(new Date())}`;
    }
  } catch (error) {
    showToast(`Error cargando supervisión: ${error.message}`, "error");
    if (els.actualizado()) els.actualizado().textContent = "Error";
  }
}

function iniciarAutoRefresh() {
  if (intervaloRefresco) clearInterval(intervaloRefresco);
  intervaloRefresco = setInterval(cargarDatos, 30_000);
}

function detenerAutoRefresh() {
  if (intervaloRefresco) {
    clearInterval(intervaloRefresco);
    intervaloRefresco = null;
  }
}

export async function initSupervision() {
  const usuario = getUsuario();
  if (!usuario || usuario.rol !== "admin") return;
  if (!inicializado) {
    els.btnRefresh()?.addEventListener("click", async () => {
      await cargarDatos();
      showToast("Datos actualizados", "info");
    });
    window.addEventListener("beforeunload", () => {
      detenerAutoRefresh();
    });
    inicializado = true;
  }
  await cargarDatos();
  iniciarAutoRefresh();
}
