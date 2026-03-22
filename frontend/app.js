// app.js — PharmWatch dashboard
const API_BASE = "http://localhost:8000";

// ── Clock ─────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  document.getElementById("clock").textContent =
    `${String(now.getUTCHours()).padStart(2,"0")}:${String(now.getUTCMinutes()).padStart(2,"0")}:${String(now.getUTCSeconds()).padStart(2,"0")} UTC`;
}
setInterval(updateClock, 1000); updateClock();

// ── Health check ──────────────────────────────────────────────────────────────
async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    const dot   = document.getElementById("status-dot");
    const label = document.getElementById("status-label");
    if (res.ok) {
      dot.className   = "status-dot online";
      label.textContent = "Online";
    } else { throw new Error(); }
  } catch {
    document.getElementById("status-dot").className    = "status-dot offline";
    document.getElementById("status-label").textContent = "Offline";
  }
}
setInterval(checkHealth, 10000); checkHealth();

// ── Upload inventory ──────────────────────────────────────────────────────────
document.getElementById("inv-upload").addEventListener("change", async function() {
  const msg = document.getElementById("pipeline-msg");
  msg.className = "pipeline-msg";
  msg.textContent = `Uploading ${this.files[0].name}...`;

  const fd = new FormData();
  fd.append("file", this.files[0]);

  try {
    const res  = await fetch(`${API_BASE}/ingest/inventory`, { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      msg.className   = "pipeline-msg ok";
      msg.textContent = `✓ Inventory accepted: ${data.drugs} drugs, ${data.rows} batches, total value Ksh ${data.total_value_ksh.toLocaleString()}`;
      loadSummary();
    } else {
      msg.className = "pipeline-msg error";
      msg.textContent = `✗ ${data.detail}`;
    }
  } catch { msg.className = "pipeline-msg error"; msg.textContent = "✗ Upload failed"; }
  this.value = "";
});

// ── Upload dispensing ─────────────────────────────────────────────────────────
document.getElementById("disp-upload").addEventListener("change", async function() {
  const msg = document.getElementById("pipeline-msg");
  msg.className = "pipeline-msg";
  msg.textContent = `Uploading ${this.files[0].name}...`;

  const fd = new FormData();
  fd.append("file", this.files[0]);

  try {
    const res  = await fetch(`${API_BASE}/ingest/dispensing`, { method: "POST", body: fd });
    const data = await res.json();
    if (res.ok) {
      msg.className   = "pipeline-msg ok";
      msg.textContent = `✓ Dispensing records accepted: ${data.drugs} drugs, ${data.rows} rows (${data.date_range.from} → ${data.date_range.to})`;
    } else {
      msg.className = "pipeline-msg error";
      msg.textContent = `✗ ${data.detail}`;
    }
  } catch { msg.className = "pipeline-msg error"; msg.textContent = "✗ Upload failed"; }
  this.value = "";
});

// ── Run checks ────────────────────────────────────────────────────────────────
async function runChecks() {
  const btn = document.querySelector(".btn-run");
  const msg = document.getElementById("pipeline-msg");
  btn.disabled  = true;
  msg.className = "pipeline-msg";
  msg.textContent = "Running checks...";

  try {
    const res  = await fetch(`${API_BASE}/run-checks?send_email=false`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      msg.className   = "pipeline-msg ok";
      msg.textContent = `✓ Done — ${data.expiry_flags} expiry flags, ${data.reorder_flags} reorder flags`;
      loadFlags();
      loadForecast();
      loadSummary();
    } else {
      msg.className = "pipeline-msg error";
      msg.textContent = `✗ ${data.detail}`;
    }
  } catch { msg.className = "pipeline-msg error"; msg.textContent = "✗ Failed. Is the backend running?"; }
  btn.disabled = false;
}

// ── Load inventory summary ────────────────────────────────────────────────────
async function loadSummary() {
  try {
    const res  = await fetch(`${API_BASE}/inventory/summary`);
    if (!res.ok) return;
    const d    = await res.json();
    const grid = document.getElementById("summary-grid");

    grid.innerHTML = `
      <div class="summary-card">
        <div class="s-label">Total drugs</div>
        <div class="s-value">${d.total_drugs}</div>
        <div class="s-sub">${d.total_batches} batches</div>
      </div>
      <div class="summary-card">
        <div class="s-label">Stock value</div>
        <div class="s-value">Ksh ${(d.total_stock_value/1000).toFixed(1)}k</div>
        <div class="s-sub">Total inventory</div>
      </div>
      <div class="summary-card ${d.expired_count > 0 ? 'danger' : 'ok'}">
        <div class="s-label">Expired</div>
        <div class="s-value">${d.expired_count}</div>
        <div class="s-sub">Remove immediately</div>
      </div>
      <div class="summary-card ${d.critical_count > 0 ? 'danger' : 'ok'}">
        <div class="s-label">Critical (&lt;30d)</div>
        <div class="s-value">${d.critical_count}</div>
        <div class="s-sub">Batches expiring soon</div>
      </div>
      <div class="summary-card ${d.warn_count > 0 ? 'warn' : 'ok'}">
        <div class="s-label">Warning (&lt;90d)</div>
        <div class="s-value">${d.warn_count}</div>
        <div class="s-sub">Plan ahead</div>
      </div>
      <div class="summary-card ${d.at_risk_value_ksh > 0 ? 'warn' : 'ok'}">
        <div class="s-label">At-risk value</div>
        <div class="s-value">Ksh ${(d.at_risk_value_ksh/1000).toFixed(1)}k</div>
        <div class="s-sub">Expiring within 90d</div>
      </div>
    `;
  } catch {}
}

// ── Load flags ────────────────────────────────────────────────────────────────
async function loadFlags() {
  try {
    const res   = await fetch(`${API_BASE}/flags`);
    const flags = await res.json();
    const tbody = document.getElementById("flags-body");
    const badge = document.getElementById("flag-count");

    badge.textContent = flags.length;
    badge.className   = `count-badge ${flags.length > 0 ? "has-flags" : ""}`;

    if (!flags.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="empty-row">No active flags — all clear</td></tr>`;
      return;
    }

    tbody.innerHTML = flags.map(f => `
      <tr>
        <td><strong>${f.drug_name}</strong></td>
        <td style="font-family:var(--mono);font-size:11px">${f.batch_number || "—"}</td>
        <td><span class="badge badge-${f.flag_type.toLowerCase()}">${f.flag_type.replace("_"," ")}</span></td>
        <td style="font-family:var(--mono)">${f.days_to_expiry !== null ? f.days_to_expiry + "d" : "—"}</td>
        <td style="font-family:var(--mono)">${f.quantity ?? "—"}</td>
        <td style="font-family:var(--mono)">${f.value_ksh ? "Ksh " + f.value_ksh.toLocaleString() : "—"}</td>
        <td class="msg-cell">${f.message}</td>
        <td><button class="btn-resolve" onclick="resolveFlag(${f.id}, this)">Resolve</button></td>
      </tr>
    `).join("");
  } catch {}
}

// ── Resolve a flag ────────────────────────────────────────────────────────────
async function resolveFlag(flagId, btn) {
  try {
    const res = await fetch(`${API_BASE}/flags/resolve`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ flag_id: flagId })
    });
    if (res.ok) {
      btn.closest("tr").style.opacity = "0.3";
      setTimeout(() => { loadFlags(); }, 600);
    }
  } catch {}
}

// ── Load forecast ─────────────────────────────────────────────────────────────
async function loadForecast() {
  try {
    const res      = await fetch(`${API_BASE}/forecast`);
    if (!res.ok) return;
    const forecast = await res.json();
    const tbody    = document.getElementById("forecast-body");

    if (!forecast.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-row">No forecast data</td></tr>`;
      return;
    }

    // Sort by forecast_units descending — highest demand first
    forecast.sort((a, b) => b.forecast_units - a.forecast_units);

    tbody.innerHTML = forecast.map(f => `
      <tr>
        <td><strong>${f.drug_name}</strong></td>
        <td style="font-family:var(--mono)">${f.forecast_units.toLocaleString()}</td>
        <td style="font-family:var(--mono)">${f.avg_daily}/day</td>
        <td style="font-family:var(--mono);font-size:11px">${f.peak_day || "—"}</td>
        <td style="font-family:var(--mono)">${f.history_days}d</td>
        <td><span class="badge ${f.reliable ? 'badge-reliable' : 'badge-estimate'}">${f.reliable ? "Prophet" : "Estimate"}</span></td>
      </tr>
    `).join("");
  } catch {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadFlags();
loadSummary();
setInterval(loadFlags, 60000);
