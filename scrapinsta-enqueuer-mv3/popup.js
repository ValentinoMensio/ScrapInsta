// popup.js - ScrapInsta Extension
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

// =====================================================
// SETTINGS & AUTH
// =====================================================

function loadSettings() {
  return new Promise((resolve) => {
    chrome.storage.sync.get(
      {
        api_base: "",
        auth_mode: "x-api-key",
        api_token: "",
        x_account: "",
        x_client_id: "",
        client_id: "",
        default_limit: 50,
        use_jwt: false,
        jwt_token: "",
        jwt_expires_at: 0,
      },
      (cfg) => resolve(cfg)
    );
  });
}

function saveSettings(patch) {
  return new Promise((resolve) => {
    chrome.storage.sync.set(patch, () => resolve());
  });
}

async function getJwtToken(apiBase, apiKey) {
  if (!apiBase || !apiKey) return null;
  try {
    const url = new URL("/api/auth/login", apiBase).toString();
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!resp.ok) {
      console.error("[JWT login] HTTP", resp.status);
      return null;
    }
    const data = await resp.json();
    const expiresIn = data.expires_in || 3600;
    const expiresAt = Date.now() + (expiresIn * 1000);
    await saveSettings({
      jwt_token: data.access_token,
      jwt_expires_at: expiresAt,
      client_id: data.client_id,
    });
    return data.access_token;
  } catch (e) {
    console.error("[JWT login] Error:", e);
    return null;
  }
}

async function getAuthHeaders(cfg) {
  const headers = { "Content-Type": "application/json" };
  
  if (cfg.x_account) {
    headers["X-Account"] = cfg.x_account;
  }
  
  if (cfg.use_jwt && cfg.jwt_token && cfg.jwt_expires_at > Date.now()) {
    headers["Authorization"] = `Bearer ${cfg.jwt_token}`;
    return headers;
  }
  
  if (cfg.use_jwt && cfg.api_token) {
    const token = await getJwtToken(cfg.api_base, cfg.api_token);
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
      return headers;
    }
  }
  
  if (cfg.auth_mode === "bearer") {
    if (cfg.api_token) {
      headers["Authorization"] = "Bearer " + cfg.api_token;
    }
  } else {
    if (cfg.api_token) {
      headers["X-Api-Key"] = cfg.api_token;
    }
  }
  
  const clientId = cfg.x_client_id || cfg.client_id || "";
  if (clientId) {
    headers["X-Client-Id"] = clientId;
  }
  
  return headers;
}

// =====================================================
// TAB NAVIGATION
// =====================================================

function initTabs() {
  const tabs = $$('.tab');
  const contents = $$('.tab-content');
  if (!tabs.length) return;
  tabs.forEach(tab => {
    tab.addEventListener('click', async () => {
      const targetId = `tab-${tab.dataset.tab}`;
      tabs.forEach(t => t.classList.remove('active'));
      contents.forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      const targetContent = $(`#${targetId}`);
      if (targetContent) {
        targetContent.classList.add('active');
        targetContent.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      }
      if (tab.dataset.tab === 'send') {
        updateSenderStatus();
        loadFollowingsJobsForSend();
        const stats = await refreshSendJobProgress();
        if (stats && ((stats.queued || 0) + (stats.sent || 0) > 0)) startSendProgressPolling();
      }
      if (tab.dataset.tab === 'fetch') {
        loadLastJobs(5);
      }
    });
  });
}

// =====================================================
// FETCH / ANALYZE (Tab 1)
// =====================================================

async function enqueue() {
  const cfg = await loadSettings();
  const mode = ("#mode" in window ? $("#mode").value : "followings");
  if (!cfg.api_base) return setStatus("Configura la API en Opciones.", true);
  if (!cfg.api_token && !cfg.use_jwt) return setStatus("Configura tu API token en Opciones.", true);

  const headers = await getAuthHeaders(cfg);
  
  if (!headers["Authorization"] && !headers["X-Api-Key"]) {
    return setStatus("Falta token de autenticación. Configura en Opciones.", true);
  }
  
  if (mode === "followings" && !cfg.x_account) {
    return setStatus("Configura tu X-Account en Opciones.", true);
  }

  if (mode === "followings") {
    const target = $("#target").value.trim();
    let limit = parseInt($("#limit").value, 10);
    if (!target) return setStatus("Ingresá un target.", true);
    if (!Number.isFinite(limit) || limit <= 0) limit = cfg.default_limit || 50;
    const url = new URL("/ext/followings/enqueue", cfg.api_base).toString();
    setStatus("Enviando…");
    try {
      const resp = await fetch(url, {
        method: "POST",
        headers,
        body: JSON.stringify({ target_username: target, limit }),
      });
      const text = await resp.text();
      let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
      if (!resp.ok) {
        console.error("[enqueue followings] HTTP", resp.status, data);
        return setStatus(`Error ${resp.status}: ${data?.detail || text}`, true);
      }
      const jobId = data?.job_id || "(sin id)";
      setStatus(`Encolado ✅ Job: ${jobId}`);
      await saveSettings({ default_limit: limit });
      
      if (jobId && jobId !== "(sin id)") {
        showJobStatusSection(jobId);
        setTimeout(async () => {
          await refreshJobStatus();
          startAutoRefresh(5000);
        }, 1000);
      }
    } catch (e) {
      console.error(e);
      setStatus("Fallo de red/permiso. Revisá permisos de host y URL de API.", true);
    }
    return;
  }

  // analyze
  const raw = $("#usernames").value || "";
  const usernames = raw
    .split(/[\n,]/)
    .map((s) => s.trim().toLowerCase())
    .filter((s) => s.length > 0);
  if (usernames.length === 0) return setStatus("Ingresá al menos un username.", true);
  let batchSize = parseInt($("#batch_size").value, 10);
  if (!Number.isFinite(batchSize) || batchSize <= 0) batchSize = 25;
  const url = new URL("/ext/analyze/enqueue", cfg.api_base).toString();
  setStatus("Enviando…");
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ usernames, batch_size: batchSize }),
    });
    const text = await resp.text();
    let data; try { data = JSON.parse(text); } catch { data = { raw: text }; }
    if (!resp.ok) {
      console.error("[enqueue analyze] HTTP", resp.status, data);
      return setStatus(`Error ${resp.status}: ${data?.detail || text}`, true);
    }
    const jobId = data?.job_id || "(sin id)";
    const totalItems = data?.total_items || usernames.length;
    setStatus(`Encolado analyze ✅ Job: ${jobId} (${totalItems} perfiles)`);
    
    if (jobId && jobId !== "(sin id)") {
      showJobStatusSection(jobId);
      setTimeout(async () => {
        await refreshJobStatus();
        startAutoRefresh(5000);
      }, 1000);
    }
  } catch (e) {
    console.error(e);
    setStatus("Fallo de red/permiso. Revisá permisos de host y URL de API.", true);
  }
}

function setStatus(msg, isErr = false) {
  const el = $("#status");
  el.textContent = msg;
  el.className = isErr ? "err" : "ok";
}

let currentJobId = null;
let statusCheckInterval = null;

function showJobStatusSection(jobId) {
  currentJobId = jobId;
  const sel = $("#last_jobs_select");
  if (sel && jobId) {
    if (Array.from(sel.options).every(o => o.value !== jobId)) {
      const opt = document.createElement("option");
      opt.value = jobId;
      opt.textContent = jobId;
      sel.appendChild(opt);
    }
    sel.value = jobId;
  }
  $("#job_progress").style.display = "none";
  chrome.storage.local.set({ last_job_id: jobId });
}

async function loadLastJobs(limit = 5) {
  const cfg = await loadSettings();
  if (!cfg.api_base) return;
  const headers = await getAuthHeaders(cfg);
  const url = new URL("/ext/jobs", cfg.api_base);
  url.searchParams.set("limit", String(limit));
  try {
    const resp = await fetch(url.toString(), { headers });
    if (!resp.ok) return;
    const data = await resp.json();
    const jobs = data.jobs || [];
    const sel = $("#last_jobs_select");
    if (!sel) return;
    sel.innerHTML = '<option value="">— Selecciona un job —</option>';
    jobs.forEach((j) => {
      const opt = document.createElement("option");
      opt.value = j.id;
      const kind = j.kind || "";
      const status = j.status || "";
      opt.textContent = `${j.id} (${kind} ${status})`;
      sel.appendChild(opt);
    });
    const saved = await new Promise((r) => chrome.storage.local.get({ last_job_id: null }, (d) => r(d.last_job_id)));
    if (saved && jobs.some((j) => j.id === saved)) sel.value = saved;
    if (sel.value) {
      currentJobId = sel.value;
      const stats = await checkJobStatus(sel.value);
      if (stats) updateJobProgress(stats);
    }
  } catch (e) {
    console.error("[loadLastJobs]", e);
  }
}

async function fetchJobSummary(cfg, headers, jid) {
  const url = new URL(`/jobs/${encodeURIComponent(jid)}/summary`, cfg.api_base).toString();
  try {
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      if (resp.status === 401) {
        return { _error: "auth", status: 401 };
      }
      if (resp.status === 404) {
        return { _error: "not_found", status: 404 };
      }
      return null;
    }
    const text = await resp.text();
    try { return JSON.parse(text); } catch { return null; }
  } catch {
    return null;
  }
}

async function checkJobStatus(jobId = null) {
  const cfg = await loadSettings();
  const jid = jobId || currentJobId;
  
  if (!jid) {
    setStatus("No hay job para verificar", true);
    return null;
  }
  
  if (!cfg.api_base) {
    setStatus("Configura la API primero", true);
    return null;
  }
  
  const headers = await getAuthHeaders(cfg);
  
  const mainStats = await fetchJobSummary(cfg, headers, jid);
  
  if (mainStats?._error === "auth") {
    setStatus("⚠️ Token expirado. Re-autentica en Opciones.", true);
    if (cfg.use_jwt) {
      await saveSettings({ jwt_token: "", jwt_expires_at: 0 });
    }
    return null;
  }
  
  if (!mainStats || mainStats._error) {
    setStatus(`Job no encontrado: ${jid}`, true);
    return null;
  }
  
  const analyzeJobId = `analyze:${jid}`;
  const analyzeStats = await fetchJobSummary(cfg, headers, analyzeJobId);
  
  const hasAnalyze = analyzeStats && !analyzeStats._error;
  
  const combined = {
    queued: (mainStats.queued || 0) + (hasAnalyze ? (analyzeStats.queued || 0) : 0),
    sent: (mainStats.sent || 0) + (hasAnalyze ? (analyzeStats.sent || 0) : 0),
    ok: (mainStats.ok || 0) + (hasAnalyze ? (analyzeStats.ok || 0) : 0),
    error: (mainStats.error || 0) + (hasAnalyze ? (analyzeStats.error || 0) : 0),
    hasAnalyzeJob: hasAnalyze,
    analyzeJobId: hasAnalyze ? analyzeJobId : null,
  };
  
  return combined;
}

function updateJobProgress(stats) {
  if (!stats) return;
  
  const queued = stats.queued || 0;
  const sent = stats.sent || 0;
  const ok = stats.ok || 0;
  const error = stats.error || 0;
  const total = queued + sent + ok + error;
  const completed = ok + error;
  const hasAnalyze = stats.hasAnalyzeJob;
  const isFinished = queued === 0 && sent === 0 && total > 0 && hasAnalyze;
  
  $("#stat_queued").textContent = queued;
  $("#stat_sent").textContent = sent;
  $("#stat_ok").textContent = ok;
  $("#stat_error").textContent = error;
  
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
  $("#progress_fill").style.width = `${percent}%`;
  
  let statusText = "";
  if (isFinished) {
    statusText = `✅ Completado: ${ok} OK, ${error} errores`;
    stopAutoRefresh();
  } else if (!hasAnalyze && queued === 0 && sent === 0 && (ok > 0 || error > 0)) {
    // Job de análisis visto directamente o fetch ya terminado
    statusText = `✅ Completado: ${ok} OK, ${error} errores`;
  } else if (!hasAnalyze && queued === 0 && sent === 0) {
    statusText = `⏳ Esperando análisis...`;
  } else if (sent > 0) {
    statusText = `🚀 Procesando: ${completed}/${total} (${percent}%)`;
  } else if (queued > 0) {
    statusText = `⏳ En cola: ${queued} pendientes`;
  } else {
    statusText = `Esperando...`;
  }
  
  $("#progress_text").textContent = statusText;
  $("#job_progress").style.display = "block";
}

async function refreshJobStatus() {
  const stats = await checkJobStatus();
  if (stats) {
    updateJobProgress(stats);
    setStatus(`Actualizado: ${new Date().toLocaleTimeString()}`);
  }
}

function startAutoRefresh(intervalMs = 5000) {
  stopAutoRefresh();
  statusCheckInterval = setInterval(refreshJobStatus, intervalMs);
}

function stopAutoRefresh() {
  if (statusCheckInterval) {
    clearInterval(statusCheckInterval);
    statusCheckInterval = null;
  }
}

// =====================================================
// SEND DMs (Tab 2) — Job de followings + pendientes
// =====================================================

let selectedSendJobId = null;
let selectedSendUsernames = [];

function setSendStatus(msg, isErr = false) {
  const el = $("#send_status");
  if (el) {
    el.textContent = msg;
    el.className = isErr ? "err" : "ok";
  }
}

function updateSendJobProgress(stats) {
  if (!stats) return;
  const queued = stats.queued || 0;
  const sent = stats.sent || 0;
  const ok = stats.ok || 0;
  const error = stats.error || 0;
  const total = queued + sent + ok + error;
  const completed = ok + error;
  const isFinished = queued === 0 && sent === 0 && total > 0;
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0;

  const qEl = $("#send_stat_queued");
  const sEl = $("#send_stat_sent");
  const oEl = $("#send_stat_ok");
  const eEl = $("#send_stat_error");
  const textEl = $("#send_progress_text");
  const section = $("#send_job_progress_section");
  const fillEl = $("#send_progress_fill");
  if (qEl) qEl.textContent = queued;
  if (sEl) sEl.textContent = sent;
  if (oEl) oEl.textContent = ok;
  if (eEl) eEl.textContent = error;
  if (section) section.style.display = "block";
  if (fillEl) fillEl.style.width = percent + "%";

  let statusText = "";
  if (isFinished) {
    statusText = `✅ Completado: ${ok} OK, ${error} errores`;
    stopSendProgressPolling();
  } else if (sent > 0) {
    statusText = `🚀 Procesando: ${completed}/${total} (${percent}%)`;
  } else if (queued > 0) {
    statusText = `⏳ En cola: ${queued} pendientes`;
  } else {
    statusText = total > 0 ? "Esperando..." : "—";
  }
  if (textEl) textEl.textContent = statusText;
}

async function refreshSendJobProgress() {
  const data = await new Promise((r) => chrome.storage.local.get({ last_send_job_id: null }, (d) => r(d)));
  const jobId = data.last_send_job_id;
  if (!jobId) return null;
  const cfg = await loadSettings();
  if (!cfg.api_base) return null;
  const headers = await getAuthHeaders(cfg);
  const stats = await fetchJobSummary(cfg, headers, jobId);
  if (stats && !stats._error) {
    updateSendJobProgress(stats);
    return stats;
  }
  return null;
}

let sendProgressInterval = null;
const SEND_PROGRESS_POLL_MS = 4000;

function startSendProgressPolling() {
  stopSendProgressPolling();
  sendProgressInterval = setInterval(async () => {
    const stats = await refreshSendJobProgress();
    if (stats) {
      const queued = stats.queued || 0;
      const sent = stats.sent || 0;
      if (queued === 0 && sent === 0) stopSendProgressPolling();
    }
  }, SEND_PROGRESS_POLL_MS);
}

function stopSendProgressPolling() {
  if (sendProgressInterval) {
    clearInterval(sendProgressInterval);
    sendProgressInterval = null;
  }
}

async function loadFollowingsJobsForSend() {
  const cfg = await loadSettings();
  if (!cfg.api_base) {
    setSendStatus("Configura la API en Opciones.", true);
    return;
  }
  const base = (cfg.api_base || "").trim().replace(/\/$/, "");
  if (!base) {
    setSendStatus("URL de API vacía. Configura en Opciones.", true);
    return;
  }
  const headers = await getAuthHeaders(cfg);
  const url = new URL("/ext/jobs", base);
  url.searchParams.set("limit", "20");
  const sel = $("#send_followings_job_select");
  if (!sel) return;
  sel.innerHTML = '<option value="">— Cargando... —</option>';
  setSendStatus("Cargando jobs de followings...");
  try {
    const resp = await fetch(url.toString(), { headers });
    const text = await resp.text();
    let data = {};
    try {
      data = text ? JSON.parse(text) : {};
    } catch (_) {
      data = { detail: text || "Sin respuesta" };
    }
    if (!resp.ok) {
      const msg = data.detail || (typeof data.detail === "string" ? data.detail : resp.statusText) || `HTTP ${resp.status}`;
      sel.innerHTML = '<option value="">— Error —</option>';
      setSendStatus(`Error ${resp.status}: ${msg}. Revisa token y URL (${base}) en Opciones.`, true);
      return;
    }
    const allJobs = data.jobs || [];
    const jobs = allJobs.filter((j) => (j.kind || "") === "fetch_followings");
    sel.innerHTML = '<option value="">— Selecciona un job de followings —</option>';
    jobs.forEach((j) => {
      const opt = document.createElement("option");
      opt.value = j.id;
      opt.textContent = `${j.id} (${j.status || ""})`;
      sel.appendChild(opt);
    });
    selectedSendJobId = null;
    selectedSendUsernames = [];
    $("#send_followings_info").style.display = "none";
    if (jobs.length === 0) {
      setSendStatus("No hay jobs de followings. Extrae followings en la pestaña Extraer.", true);
    } else {
      setSendStatus(`${jobs.length} job(s) de followings. Elige uno.`);
    }
  } catch (e) {
    console.error("[loadFollowingsJobsForSend]", e);
    sel.innerHTML = '<option value="">— Error al cargar —</option>';
    setSendStatus("Error de red o CORS. ¿API en " + base + "? Revisa Opciones.", true);
  }
}

async function onSendFollowingsJobChange(jobId) {
  if (!jobId) {
    selectedSendJobId = null;
    selectedSendUsernames = [];
    $("#send_followings_info").style.display = "none";
    return;
  }
  const cfg = await loadSettings();
  if (!cfg.api_base) return;
  const headers = await getAuthHeaders(cfg);
  const url = new URL(`/ext/jobs/${encodeURIComponent(jobId)}/followings-recipients`, cfg.api_base).toString();
  setSendStatus("Cargando destinatarios...");
  try {
    const resp = await fetch(url, { headers });
    if (!resp.ok) {
      const text = await resp.text();
      let d; try { d = JSON.parse(text); } catch { d = {}; }
      setSendStatus(`Error: ${d.detail || text}`, true);
      return;
    }
    const data = await resp.json();
    selectedSendJobId = jobId;
    selectedSendUsernames = data.usernames || [];
    const total = data.total || 0;
    const already = data.already_sent_count || 0;
    const pending = data.pending_count ?? (total - already);
    $("#send_followings_summary").textContent =
      `${total} followings · ${already} ya enviados · ${pending} pendientes`;
    $("#send_followings_info").style.display = "block";
    setSendStatus(pending > 0 ? `Listo: ${pending} pendientes de recibir mensaje` : "Todos ya recibieron mensaje.");
  } catch (e) {
    console.error("[onSendFollowingsJobChange]", e);
    setSendStatus("Error al cargar destinatarios", true);
  }
}

async function enqueueSendMessages() {
  const cfg = await loadSettings();
  if (!cfg.api_base) return setSendStatus("Configura la API en Opciones.", true);
  if (!cfg.x_account) return setSendStatus("Configura tu X-Account en Opciones.", true);
  if (!selectedSendJobId || !selectedSendUsernames.length) {
    return setSendStatus("Elige un job de followings primero.", true);
  }

  const message = $("#send_message").value.trim();
  if (!message) return setSendStatus("Escribe un mensaje.", true);
  if (message.length < 10) return setSendStatus("El mensaje es muy corto (mínimo 10 caracteres).", true);
  if (message.length > 1000) return setSendStatus("El mensaje es muy largo (máximo 1000 caracteres).", true);

  const dryRun = $("#dry_run") ? $("#dry_run").checked : true;
  if (!dryRun) {
    if (!confirm("Vas a enviar mensajes realmente. ¿Continuar?")) return;
  }

  const headers = await getAuthHeaders(cfg);
  const url = new URL("/ext/send/enqueue", cfg.api_base).toString();
  setSendStatus("Encolando mensajes (solo pendientes)...");

  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        usernames: selectedSendUsernames,
        message_template: message,
        source_job_id: selectedSendJobId,
        dry_run: dryRun,
      }),
    });

    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch { data = { raw: text }; }

    if (!resp.ok) {
      console.error("[enqueue send] HTTP", resp.status, data);
      return setSendStatus(`Error ${resp.status}: ${data?.detail || text}`, true);
    }

    const jobId = data?.job_id || "(sin id)";
    const total = data?.total_items || 0;
    const dailyRemaining = data?.daily_remaining || "-";
    const hourlyRemaining = data?.hourly_remaining || "-";

    $("#limit_daily").textContent = dailyRemaining;
    $("#limit_hourly").textContent = hourlyRemaining;
    chrome.storage.local.set({ last_send_job_id: jobId });

    setSendStatus(`✅ Encolados ${total} mensajes (solo pendientes). Job: ${jobId}`);
    onSendFollowingsJobChange(selectedSendJobId);
    const stats = await refreshSendJobProgress();
    if (stats && ((stats.queued || 0) + (stats.sent || 0) > 0)) startSendProgressPolling();
  } catch (e) {
    console.error("[enqueue send] Error:", e);
    setSendStatus("Error de red. Verifica la conexión.", true);
  }
}

let senderStatusInterval = null;

function stopSenderStatusPolling() {
  if (senderStatusInterval) {
    clearInterval(senderStatusInterval);
    senderStatusInterval = null;
  }
}

async function updateSenderStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ action: 'get_sender_status' });
    if (!status) return;
    const startBtn = $("#start_sender");
    const stopBtn = $("#stop_sender");
    if (status.isRunning) {
      if (startBtn) startBtn.disabled = true;
      if (stopBtn) stopBtn.disabled = false;
    } else {
      stopSenderStatusPolling();
      if (startBtn) startBtn.disabled = false;
      if (stopBtn) stopBtn.disabled = true;
    }
  } catch (e) {
    console.error("[updateSenderStatus] Error:", e);
    stopSenderStatusPolling();
  }
}

async function startSender() {
  try {
    setSendStatus("Iniciando sender...");
    const result = await chrome.runtime.sendMessage({ action: 'start_sender' });
    if (result?.status === 'started') {
      setSendStatus("✅ Sender iniciado");
      updateSenderStatus();
    }
  } catch (e) {
    console.error("[startSender] Error:", e);
    setSendStatus("Error al iniciar sender", true);
  }
}

async function stopSender() {
  try {
    setSendStatus("Deteniendo sender...");
    const result = await chrome.runtime.sendMessage({ action: 'stop_sender' });
    if (result?.status === 'stopped') {
      setSendStatus("Listo");
      updateSenderStatus();
    }
  } catch (e) {
    console.error("[stopSender] Error:", e);
    setSendStatus("Error al detener sender", true);
  }
}

// =====================================================
// INICIALIZACIÓN
// =====================================================

async function main() {
  // Cargar settings
  const cfg = await loadSettings();
  
  // Init tabs
  initTabs();
  
  // Tab 1: Fetch/Analyze
  $("#limit").value = cfg.default_limit || 50;
  $("#target").focus();
  $("#enqueue").addEventListener("click", enqueue);
  
  const enqueueAnalyzeBtn = $("#enqueue_analyze");
  if (enqueueAnalyzeBtn) enqueueAnalyzeBtn.addEventListener("click", enqueue);
  
  const modeSel = $("#mode");
  if (modeSel) {
    modeSel.addEventListener("change", () => {
      const m = modeSel.value;
      $("#followings_fields").style.display = m === "followings" ? "block" : "none";
      $("#analyze_fields").style.display = m === "analyze" ? "block" : "none";
    });
  }
  
  // Selector últimos 5 jobs (Extraer): al cambiar, ver estado del job seleccionado
  const lastJobsSelect = $("#last_jobs_select");
  if (lastJobsSelect) {
    lastJobsSelect.addEventListener("change", async () => {
      const jid = lastJobsSelect.value;
      if (!jid) {
        $("#job_progress").style.display = "none";
        return;
      }
      currentJobId = jid;
      setStatus("Cargando estado...");
      const stats = await checkJobStatus(jid);
      if (stats) {
        updateJobProgress(stats);
        setStatus(`Actualizado: ${new Date().toLocaleTimeString()}`);
      } else {
        $("#job_progress").style.display = "none";
      }
    });
  }
  
  
  // Tab 2: Send DMs
  const sendMessageInput = $("#send_message");
  if (sendMessageInput) {
    sendMessageInput.addEventListener("input", () => {
      const count = sendMessageInput.value.length;
      $("#message_char_count").textContent = count;
    });
  }
  
  const sendFollowingsSelect = $("#send_followings_job_select");
  if (sendFollowingsSelect) {
    sendFollowingsSelect.addEventListener("change", () => {
      onSendFollowingsJobChange(sendFollowingsSelect.value);
    });
  }

  const enqueueSendBtn = $("#enqueue_send");
  if (enqueueSendBtn) {
    enqueueSendBtn.addEventListener("click", enqueueSendMessages);
  }

  const startSenderBtn = $("#start_sender");
  if (startSenderBtn) {
    startSenderBtn.addEventListener("click", startSender);
  }

  const stopSenderBtn = $("#stop_sender");
  if (stopSenderBtn) {
    stopSenderBtn.addEventListener("click", stopSender);
  }
  
  // Cargar datos de la pestaña activa al abrir (Extraer por defecto)
  loadLastJobs(5);
  updateSenderStatus();
  
  // Mostrar info de config
  const env = $("#env");
  const authInfo = cfg.use_jwt ? " (JWT)" : cfg.auth_mode === "bearer" ? " (Bearer)" : " (X-Api-Key)";
  const clientId = cfg.x_client_id || cfg.client_id;
  const clientInfo = clientId ? ` — ClientId: ${clientId}` : "";
  const accountInfo = cfg.x_account ? ` — Cuenta: ${cfg.x_account}` : "";
  env.textContent = cfg.api_base 
    ? `API: ${cfg.api_base}${authInfo}${accountInfo}${clientInfo}` 
    : "API sin configurar";
  
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'dm_status_update') {
      updateSenderStatus();
      refreshSendJobProgress();
    }
  });

  window.addEventListener("pagehide", () => {
    stopSenderStatusPolling();
    stopSendProgressPolling();
  });
  window.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      stopSenderStatusPolling();
      stopSendProgressPolling();
    } else {
      updateSenderStatus();
      refreshSendJobProgress();
    }
  });
  
  updateSenderStatus();
}

document.addEventListener("DOMContentLoaded", main);
