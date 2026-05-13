import {
  get,
  post,
  formatBs,
  formatUsd,
  formatFechaHoraVe,
  showToast,
  getUsuario,
} from "./api.js";

// -----------------------------------------------------------------------------
// Estado interno del historial
// -----------------------------------------------------------------------------
const state = {
  desde: null, // yyyy-mm-dd
  hasta: null, // yyyy-mm-dd
  limite: 50,
  offset: 0,
  total: 0,
  cargando: false,
  area: "todas",
  estadoPedido: "todos",
};

const TX_BADGES = {
  checkout: { etiqueta: "Check-out", clase: "badge-info" },
  habitaciones: { etiqueta: "Habitaciones", clase: "badge-info" },
  habitacion: { etiqueta: "Consumo hab.", clase: "badge-warning" },
  piscina: { etiqueta: "Piscina", clase: "badge-success" },
  bar: { etiqueta: "Bar", clase: "badge-info" },
  restaurante: { etiqueta: "Cocina", clase: "badge-success" },
  cocina: { etiqueta: "Cocina", clase: "badge-success" },
};

const METODO_LABELS = {
  efectivo_usd: "💵 Efectivo USD",
  efectivo_bs: "💴 Efectivo Bs",
  transferencia_bs: "💳 Transferencia Bs",
  pagomovil_bs: "📱 Pago Móvil Bs",
  mixto: "💵+💴 Mixto",
  otros: "Otros",
};

// -----------------------------------------------------------------------------
// Helpers de fechas (en hora local Venezuela)
// -----------------------------------------------------------------------------
const VE_TZ = "America/Caracas";

function isoFecha(d) {
  // Devuelve "yyyy-mm-dd" en zona Venezuela (sin desfase UTC).
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: VE_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(d);
  const y = parts.find((p) => p.type === "year").value;
  const m = parts.find((p) => p.type === "month").value;
  const day = parts.find((p) => p.type === "day").value;
  return `${y}-${m}-${day}`;
}

function rangoHoy() {
  const hoy = isoFecha(new Date());
  return { desde: hoy, hasta: hoy };
}

function rangoSemana() {
  // Lunes → Domingo de la semana actual (zona Venezuela).
  const hoyStr = isoFecha(new Date());
  const hoy = new Date(`${hoyStr}T12:00:00`);
  const dow = hoy.getDay(); // 0 = domingo, 1 = lunes, ...
  const offsetLunes = dow === 0 ? -6 : 1 - dow;
  const lunes = new Date(hoy);
  lunes.setDate(hoy.getDate() + offsetLunes);
  const domingo = new Date(lunes);
  domingo.setDate(lunes.getDate() + 6);
  return { desde: isoFecha(lunes), hasta: isoFecha(domingo) };
}

function rangoMes() {
  const hoyStr = isoFecha(new Date());
  const hoy = new Date(`${hoyStr}T12:00:00`);
  const primero = new Date(hoy.getFullYear(), hoy.getMonth(), 1, 12, 0, 0);
  const ultimo = new Date(hoy.getFullYear(), hoy.getMonth() + 1, 0, 12, 0, 0);
  return { desde: isoFecha(primero), hasta: isoFecha(ultimo) };
}

function rangoAno() {
  const hoyStr = isoFecha(new Date());
  const hoy = new Date(`${hoyStr}T12:00:00`);
  return {
    desde: `${hoy.getFullYear()}-01-01`,
    hasta: `${hoy.getFullYear()}-12-31`,
  };
}

const RANGOS = {
  dia: rangoHoy,
  semana: rangoSemana,
  mes: rangoMes,
  ano: rangoAno,
};

// -----------------------------------------------------------------------------
// Elementos del DOM (lazy bind por si la pestaña aún no fue insertada)
// -----------------------------------------------------------------------------
function $(id) {
  return document.getElementById(id);
}

// -----------------------------------------------------------------------------
// Render helpers
// -----------------------------------------------------------------------------
function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function renderResumen(data) {
  setText("hist-ventas-usd", formatUsd(data.total_ventas_usd));
  setText("hist-ventas-bs", formatBs(data.total_ventas_bs));
  setText("hist-gastos-usd", formatUsd(data.total_gastos_usd));
  setText("hist-gastos-bs", formatBs(data.total_gastos_bs));
  setText("hist-neto-usd", formatUsd(data.ganancia_neta_usd));
  setText("hist-neto-bs", formatBs(data.ganancia_neta_bs));
}

function renderAreas(data) {
  const map = {
    "hist-area-habs": data.habitaciones,
    "hist-area-bar": data.bar,
    "hist-area-cocina": data.cocina,
    "hist-area-piscina": data.piscina,
  };
  for (const [prefijo, monto] of Object.entries(map)) {
    setText(`${prefijo}-usd`, formatUsd(monto.usd));
    setText(`${prefijo}-bs`, formatBs(monto.bs));
  }
}

function renderMetodos(data) {
  const cont = $("hist-metodos");
  if (!cont) return;
  const claves = [
    "efectivo_usd",
    "efectivo_bs",
    "transferencia_bs",
    "pagomovil_bs",
    "mixto",
    "otros",
  ];
  const lineas = claves.map((clave) => {
    const m = data[clave] || { usd: 0, bs: 0 };
    const usd = Number(m.usd || 0);
    const bs = Number(m.bs || 0);
    if (usd === 0 && bs === 0) return null;
    const partes = [];
    if (usd > 0) partes.push(formatUsd(usd));
    if (bs > 0) partes.push(formatBs(bs));
    return `<li class="flex justify-between border-b last:border-b-0 py-1">
      <span>${METODO_LABELS[clave] || clave}</span>
      <span class="font-medium">${partes.join(" · ")}</span>
    </li>`;
  });
  const visibles = lineas.filter(Boolean);
  cont.innerHTML = visibles.length
    ? visibles.join("")
    : `<li class="text-slate-500 text-xs">Sin pagos registrados en el período.</li>`;
}

function esAdmin() {
  const u = getUsuario();
  return u && u.rol === "admin";
}

function renderTabla(data) {
  const tbody = $("hist-tabla-tx");
  if (!tbody) return;
  state.total = data.total || 0;
  if (!data.items?.length) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state">Sin transacciones en este período.</div></td></tr>`;
    setText("hist-paginacion-info", "0 de 0");
    return;
  }
  const admin = esAdmin();
  tbody.innerHTML = data.items
    .map((tx) => {
      const fecha = tx.fecha ? formatFechaHoraVe(tx.fecha) : "-";
      const badge = TX_BADGES[tx.tipo] || {
        etiqueta: tx.tipo || "venta",
        clase: "badge-info",
      };
      // Sólo permitimos anular pedidos pagados/cargados; los check-outs no.
      const puedeAnular = admin && tx.tipo !== "checkout";
      const accion = puedeAnular
        ? `<button data-id="${tx.id}" data-concepto="${(tx.concepto || "").replace(/"/g, "&quot;")}" class="btn-anular-venta px-2 py-0.5 text-xs rounded bg-red-100 text-red-700">Anular</button>`
        : "";
      const area = tx.area || tx.tipo || "-";
      const estado = (tx.estado || "pagado").toLowerCase();
      const estadoLabel =
        estado === "anulado"
          ? "Anulado"
          : estado === "cancelado"
            ? "Cancelado"
            : "Pagado";
      const estadoClase =
        estado === "anulado"
          ? "badge-danger"
          : estado === "cancelado"
            ? "badge-warning"
            : "badge-success";
      return `
        <tr>
          <td class="text-xs whitespace-nowrap">${fecha}</td>
          <td><span class="badge ${badge.clase}">${badge.etiqueta}</span></td>
          <td>${area}</td>
          <td><span class="badge ${estadoClase}">${estadoLabel}</span></td>
          <td>${tx.concepto || "-"}</td>
          <td class="text-right">${formatUsd(tx.monto_usd)}</td>
          <td class="text-right">${formatBs(tx.monto_bs)}</td>
          <td class="text-xs text-slate-500">${tx.usuario_nombre || "-"}</td>
          <td class="text-right">${accion}</td>
        </tr>
      `;
    })
    .join("");
  tbody.querySelectorAll(".btn-anular-venta").forEach((btn) =>
    btn.addEventListener("click", () =>
      anularVenta(Number(btn.dataset.id), btn.dataset.concepto || ""),
    ),
  );
  const desde_idx = state.offset + 1;
  const hasta_idx = Math.min(state.offset + data.items.length, state.total);
  setText(
    "hist-paginacion-info",
    `${desde_idx}–${hasta_idx} de ${state.total}`,
  );
}

async function anularVenta(pedidoId, concepto) {
  const motivo = window.prompt(
    `Indique el motivo de la anulación de "${concepto || `Pedido #${pedidoId}`}"`,
    "",
  );
  if (motivo === null) return;
  const trim = motivo.trim();
  if (trim.length < 2) {
    showToast("Debe indicar un motivo válido", "error");
    return;
  }
  if (
    !confirm(
      "¿Anular esta venta? Se devolverá el stock al inventario y no se podrá deshacer.",
    )
  ) {
    return;
  }
  try {
    await post(`/pedidos/${pedidoId}/anular`, { motivo: trim });
    showToast(`Venta #${pedidoId} anulada`, "success");
    recargar();
  } catch (error) {
    showToast(`Error anulando venta: ${error.message}`, "error");
  }
}

function actualizarBotonesRango() {
  document.querySelectorAll(".hist-rango-btn").forEach((btn) => {
    const r = RANGOS[btn.dataset.rango]?.();
    const activo = r && r.desde === state.desde && r.hasta === state.hasta;
    btn.classList.toggle("bg-blue-600", !!activo);
    btn.classList.toggle("text-white", !!activo);
    btn.classList.toggle("border-blue-600", !!activo);
  });
}

// -----------------------------------------------------------------------------
// Carga de datos
// -----------------------------------------------------------------------------
async function recargar() {
  if (!state.desde || !state.hasta) return;
  if (state.cargando) return;
  state.cargando = true;
  const params = new URLSearchParams({
    desde: state.desde,
    hasta: state.hasta,
  });
  const txParams = new URLSearchParams({
    desde: state.desde,
    hasta: state.hasta,
    limite: String(state.limite),
    offset: String(state.offset),
  });
  if (esAdmin()) {
    txParams.set("area", state.area || "todas");
    txParams.set("estado_pedido", state.estadoPedido || "todos");
  }
  setText(
    "hist-rango-label",
    `${state.desde}  →  ${state.hasta}`,
  );
  setText("hist-actualizado", "Cargando…");
  try {
    const [resumen, areas, metodos, tabla] = await Promise.all([
      get(`/reportes/historial/resumen?${params}`),
      get(`/reportes/historial/ventas-por-area?${params}`),
      get(`/reportes/historial/por-metodo-pago?${params}`),
      get(`/reportes/historial/transacciones?${txParams}`),
    ]);
    renderResumen(resumen);
    renderAreas(areas);
    renderMetodos(metodos);
    renderTabla(tabla);
    actualizarBotonesRango();
    setText(
      "hist-actualizado",
      `Actualizado ${formatFechaHoraVe(new Date())}`,
    );
  } catch (error) {
    showToast(`Error cargando historial: ${error.message}`, "error");
    setText("hist-actualizado", `Error: ${error.message}`);
  } finally {
    state.cargando = false;
  }
}

function aplicarRango(clave) {
  const rango = RANGOS[clave]?.();
  if (!rango) return;
  state.desde = rango.desde;
  state.hasta = rango.hasta;
  state.offset = 0;
  if ($("hist-desde")) $("hist-desde").value = rango.desde;
  if ($("hist-hasta")) $("hist-hasta").value = rango.hasta;
  recargar();
}

function aplicarPersonalizado() {
  const desde = $("hist-desde")?.value;
  const hasta = $("hist-hasta")?.value;
  if (!desde || !hasta) {
    showToast("Indique fechas desde y hasta", "error");
    return;
  }
  state.desde = desde;
  state.hasta = hasta;
  state.offset = 0;
  recargar();
}

// -----------------------------------------------------------------------------
// Entrada
// -----------------------------------------------------------------------------
let _inicializado = false;

export async function initHistorial() {
  if (!_inicializado) {
    document.querySelectorAll(".hist-rango-btn").forEach((btn) =>
      btn.addEventListener("click", () => aplicarRango(btn.dataset.rango)),
    );
    $("hist-aplicar")?.addEventListener("click", aplicarPersonalizado);
    $("hist-pag-anterior")?.addEventListener("click", () => {
      if (state.offset <= 0) return;
      state.offset = Math.max(0, state.offset - state.limite);
      recargar();
    });
    $("hist-pag-siguiente")?.addEventListener("click", () => {
      if (state.offset + state.limite >= state.total) return;
      state.offset += state.limite;
      recargar();
    });
    const filtros = document.getElementById("filtros-admin");
    const admin = esAdmin();
    if (filtros) filtros.classList.toggle("hidden", !admin);
    const selectArea = document.getElementById("hist-filtro-area");
    const selectEstado = document.getElementById("hist-filtro-estado");
    if (admin) {
      selectArea?.addEventListener("change", () => {
        state.area = selectArea.value || "todas";
        state.offset = 0;
        recargar();
      });
      selectEstado?.addEventListener("change", () => {
        state.estadoPedido = selectEstado.value || "todos";
        state.offset = 0;
        recargar();
      });
    }
    _inicializado = true;
  }
  // Carga inicial: día actual.
  aplicarRango("dia");
}
