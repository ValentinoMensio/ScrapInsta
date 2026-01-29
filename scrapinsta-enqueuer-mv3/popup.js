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
  
  if (cfg.x_client_id) {
    headers["X-Client-Id"] = cfg.x_client_id;
  }
  
  return headers;
}

// =====================================================
// TAB NAVIGATION
// =====================================================

function initTabs() {
  const tabs = $$('.tab');
  const contents = $$('.tab-content');
  
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const targetId = `tab-${tab.dataset.tab}`;
      
      tabs.forEach(t => t.classList.remove('active'));
      contents.forEach(c => c.classList.remove('active'));
      
      tab.classList.add('active');
      const targetContent = $(`#${targetId}`);
      if (targetContent) targetContent.classList.add('active');
      
      // Si es tab de envío, actualizar estado
      if (tab.dataset.tab === 'send') {
        updateSenderStatus();
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
  $("#last_job_id").value = jobId;
  $("#job_status_section").style.display = "block";
  $("#job_progress").style.display = "none";
  chrome.storage.local.set({ last_job_id: jobId });
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
  const jid = jobId || currentJobId || $("#last_job_id").value;
  
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
    
    // Mostrar botón para enviar mensajes
    const sendBtn = $("#start_send_flow");
    if (sendBtn && ok > 0) {
      sendBtn.style.display = "block";
      sendBtn.dataset.analyzeJobId = stats.analyzeJobId || currentJobId;
    }
  } else if (!hasAnalyze && queued === 0 && sent === 0 && ok > 0) {
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
// SEND DMs (Tab 2)
// =====================================================

let selectedProfiles = new Set();

function setSendStatus(msg, isErr = false) {
  const el = $("#send_status");
  if (el) {
    el.textContent = msg;
    el.className = isErr ? "err" : "ok";
  }
}

async function loadAnalyzedProfiles(analyzeJobId) {
  const cfg = await loadSettings();
  if (!cfg.api_base) return [];
  
  const headers = await getAuthHeaders(cfg);
  const url = new URL(`/ext/analyze/${encodeURIComponent(analyzeJobId)}/profiles`, cfg.api_base).toString();
  
  try {
    const resp = await fetch(url, { headers });
    if (!resp.ok) return [];
    const data = await resp.json();
    return data.profiles || [];
  } catch (e) {
    console.error("[loadAnalyzedProfiles] Error:", e);
    return [];
  }
}

function renderProfilesList(profiles) {
  const container = $("#profiles_list");
  if (!container) return;
  
  if (!profiles || profiles.length === 0) {
    container.innerHTML = '<div class="muted" style="text-align: center; padding: 20px;">No hay perfiles disponibles</div>';
    return;
  }
  
  selectedProfiles = new Set(profiles.map(p => p.username));
  
  container.innerHTML = profiles.map(p => `
    <div class="profile-item">
      <label style="display: flex; align-items: center; margin: 0; cursor: pointer;">
        <input type="checkbox" class="profile-checkbox" data-username="${p.username}" checked>
        <span style="margin-left: 4px;">@${p.username}</span>
      </label>
      <span style="color: #666;">
        ${p.followers ? `${formatNumber(p.followers)} seg` : ''}
        ${p.verified ? '✓' : ''}
      </span>
    </div>
  `).join('');
  
  // Event listeners para checkboxes
  container.querySelectorAll('.profile-checkbox').forEach(cb => {
    cb.addEventListener('change', (e) => {
      if (e.target.checked) {
        selectedProfiles.add(e.target.dataset.username);
      } else {
        selectedProfiles.delete(e.target.dataset.username);
      }
    });
  });
}

function formatNumber(num) {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

async function enqueueSendMessages() {
  const cfg = await loadSettings();
  if (!cfg.api_base) return setSendStatus("Configura la API en Opciones.", true);
  if (!cfg.x_account) return setSendStatus("Configura tu X-Account en Opciones.", true);
  
  const usernames = Array.from(selectedProfiles);
  if (usernames.length === 0) return setSendStatus("Selecciona al menos un perfil.", true);
  
  const message = $("#send_message").value.trim();
  if (!message) return setSendStatus("Escribe un mensaje.", true);
  if (message.length < 10) return setSendStatus("El mensaje es muy corto (mínimo 10 caracteres).", true);
  if (message.length > 1000) return setSendStatus("El mensaje es muy largo (máximo 1000 caracteres).", true);
  
  const headers = await getAuthHeaders(cfg);
  const url = new URL("/ext/send/enqueue", cfg.api_base).toString();
  
  setSendStatus("Encolando mensajes...");
  
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({
        usernames: usernames,
        message_template: message,
        source_job_id: currentJobId,
        dry_run: true,  // SIEMPRE dry_run por ahora
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
    const total = data?.total_items || usernames.length;
    const dailyRemaining = data?.daily_remaining || '-';
    const hourlyRemaining = data?.hourly_remaining || '-';
    
    // Actualizar límites
    $("#limit_daily").textContent = dailyRemaining;
    $("#limit_hourly").textContent = hourlyRemaining;
    
    // Guardar job_id de envío
    chrome.storage.local.set({ last_send_job_id: jobId });
    
    setSendStatus(`✅ Encolados ${total} mensajes (Job: ${jobId})`);
    
  } catch (e) {
    console.error("[enqueue send] Error:", e);
    setSendStatus("Error de red. Verifica la conexión.", true);
  }
}

async function updateSenderStatus() {
  try {
    const status = await chrome.runtime.sendMessage({ action: 'get_sender_status' });
    
    if (!status) return;
    
    const badge = $("#sender_status_badge");
    const timer = $("#sender_timer");
    const stats = $("#sender_stats");
    const startBtn = $("#start_sender");
    const stopBtn = $("#stop_sender");
    
    if (status.isRunning) {
      badge.className = "badge running";
      badge.textContent = "🔄 Ejecutando";
      timer.style.display = "block";
      timer.textContent = status.timeUntilNextFormatted || "00:00";
      stats.style.display = "block";
      startBtn.disabled = true;
      stopBtn.disabled = false;
    } else {
      badge.className = "badge stopped";
      badge.textContent = "⏹️ Detenido";
      timer.style.display = "none";
      stats.style.display = "none";
      startBtn.disabled = false;
      stopBtn.disabled = true;
    }
    
    $("#sender_session_count").textContent = status.sessionCount || 0;
    
  } catch (e) {
    console.error("[updateSenderStatus] Error:", e);
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
      setSendStatus("⏹️ Sender detenido");
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
  
  const checkStatusBtn = $("#check_status");
  if (checkStatusBtn) {
    checkStatusBtn.addEventListener("click", async () => {
      setStatus("Verificando estado...");
      const stats = await checkJobStatus();
      if (stats) {
        updateJobProgress(stats);
        setStatus(`Actualizado: ${new Date().toLocaleTimeString()}`);
      }
    });
  }
  
  // Botón para iniciar flujo de envío
  const startSendFlowBtn = $("#start_send_flow");
  if (startSendFlowBtn) {
    startSendFlowBtn.addEventListener("click", async () => {
      const analyzeJobId = startSendFlowBtn.dataset.analyzeJobId;
      if (analyzeJobId) {
        // Cambiar a tab de envío
        $$('.tab').forEach(t => t.classList.remove('active'));
        $$('.tab-content').forEach(c => c.classList.remove('active'));
        $('[data-tab="send"]').classList.add('active');
        $('#tab-send').classList.add('active');
        
        // Cargar perfiles
        setSendStatus("Cargando perfiles analizados...");
        const profiles = await loadAnalyzedProfiles(analyzeJobId);
        renderProfilesList(profiles);
        $("#send_profiles_section").style.display = "block";
        setSendStatus(`${profiles.length} perfiles cargados`);
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
  
  const selectAllBtn = $("#select_all_profiles");
  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", () => {
      $$('.profile-checkbox').forEach(cb => {
        cb.checked = true;
        selectedProfiles.add(cb.dataset.username);
      });
    });
  }
  
  const deselectAllBtn = $("#deselect_all_profiles");
  if (deselectAllBtn) {
    deselectAllBtn.addEventListener("click", () => {
      $$('.profile-checkbox').forEach(cb => {
        cb.checked = false;
        selectedProfiles.delete(cb.dataset.username);
      });
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
  
  // Cargar último job
  chrome.storage.local.get({ last_job_id: null }, (data) => {
    if (data.last_job_id) {
      showJobStatusSection(data.last_job_id);
    }
  });
  
  // Mostrar info de config
  const env = $("#env");
  const authInfo = cfg.use_jwt ? " (JWT)" : cfg.auth_mode === "bearer" ? " (Bearer)" : " (X-Api-Key)";
  const clientInfo = cfg.x_client_id ? ` — ClientId: ${cfg.x_client_id}` : "";
  const accountInfo = cfg.x_account ? ` — Cuenta: ${cfg.x_account}` : "";
  env.textContent = cfg.api_base 
    ? `API: ${cfg.api_base}${authInfo}${accountInfo}${clientInfo}` 
    : "API sin configurar";
  
  // Escuchar actualizaciones del background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === 'dm_status_update') {
      const data = message.data;
      if (data.lastUsername) {
        $("#sender_last_username").textContent = `@${data.lastUsername}`;
      }
      $("#sender_session_count").textContent = data.sessionCount || 0;
      updateSenderStatus();
    }
  });
  
  // Actualizar estado del sender al abrir
  updateSenderStatus();
}

document.addEventListener("DOMContentLoaded", main);
