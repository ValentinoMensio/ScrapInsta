// background.js - ScrapInsta Service Worker
// Coordina el polling de tareas y la comunicación con el content script

// =====================================================
// CONFIGURACIÓN
// =====================================================
const CONFIG = {
  // Rate limiting (seguridad anti-baneo)
  minDelayBetweenDMs: 180000,   // 3 minutos mínimo entre DMs
  maxDelayBetweenDMs: 420000,   // 7 minutos máximo entre DMs
  
  // Polling
  pollIntervalMs: 30000,        // Cada 30 segundos revisar si hay tareas
  
  // Límites
  maxDMsPerSession: 20,         // Máximo DMs por sesión
};

// =====================================================
// ESTADO
// =====================================================
let state = {
  isRunning: false,
  isProcessing: false,
  currentTask: null,
  dmsSentThisSession: 0,
  lastDMTime: 0,
  nextDMTime: 0,
  pollAlarmName: 'scrapinsta-poll',
};

// =====================================================
// UTILIDADES
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
        use_jwt: false,
        jwt_token: "",
        jwt_expires_at: 0,
      },
      (cfg) => resolve(cfg)
    );
  });
}

function saveState(patch) {
  return new Promise((resolve) => {
    chrome.storage.local.set(patch, () => resolve());
  });
}

function loadState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(
      {
        dm_sender_running: false,
        dm_sender_session_count: 0,
        dm_sender_last_time: 0,
        dm_sender_next_time: 0,
        dm_sender_current_job_id: null,
      },
      (data) => {
        state.isRunning = data.dm_sender_running;
        state.dmsSentThisSession = data.dm_sender_session_count;
        state.lastDMTime = data.dm_sender_last_time;
        state.nextDMTime = data.dm_sender_next_time;
        resolve(state);
      }
    );
  });
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

function randomBetween(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

// =====================================================
// API CALLS
// =====================================================

async function pullTask() {
  const cfg = await loadSettings();
  if (!cfg.api_base || !cfg.api_token) {
    console.log('[BG] No hay configuración de API');
    return null;
  }
  
  const headers = await getAuthHeaders(cfg);
  const url = new URL('/api/send/pull', cfg.api_base).toString();
  
  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify({ limit: 1 }),  // Solo 1 tarea a la vez
    });
    
    if (!resp.ok) {
      console.error('[BG] Pull failed:', resp.status);
      return null;
    }
    
    const data = await resp.json();
    if (data.items && data.items.length > 0) {
      return data.items[0];
    }
    return null;
  } catch (e) {
    console.error('[BG] Pull error:', e);
    return null;
  }
}

async function reportResult(jobId, taskId, ok, destUsername, error = null) {
  const cfg = await loadSettings();
  if (!cfg.api_base) return;
  
  const headers = await getAuthHeaders(cfg);
  const url = new URL('/api/send/result', cfg.api_base).toString();
  
  try {
    const body = {
      job_id: jobId,
      task_id: taskId,
      ok: ok,
      dest_username: destUsername,
    };
    if (error) {
      body.error = error;
    }
    
    const resp = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
    });
    
    if (!resp.ok) {
      console.error('[BG] Report result failed:', resp.status);
    }
  } catch (e) {
    console.error('[BG] Report error:', e);
  }
}

// =====================================================
// ENVÍO DE DM VIA CONTENT SCRIPT
// =====================================================

async function findOrCreateInstagramTab() {
  // Buscar tab existente de Instagram
  const tabs = await chrome.tabs.query({ url: '*://www.instagram.com/*' });
  
  if (tabs.length > 0) {
    // Usar la primera tab encontrada
    return tabs[0];
  }
  
  // Crear nueva tab
  const newTab = await chrome.tabs.create({
    url: 'https://www.instagram.com/',
    active: false,  // No traer al frente
  });
  
  // Esperar a que cargue
  await new Promise((resolve) => {
    const listener = (tabId, info) => {
      if (tabId === newTab.id && info.status === 'complete') {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    };
    chrome.tabs.onUpdated.addListener(listener);
    
    // Timeout de 15 segundos
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, 15000);
  });
  
  return newTab;
}

async function sendDMViaContentScript(username, message, dryRun = true) {
  console.log(`[BG] Enviando DM a ${username}, dryRun: ${dryRun}`);
  
  try {
    const tab = await findOrCreateInstagramTab();
    if (!tab || !tab.id) {
      return { success: false, error: 'no_instagram_tab' };
    }

    const directUrl = 'https://www.instagram.com/direct/';
    const alreadyOnDirect = tab.url && tab.url.includes('instagram.com/direct');
    if (!alreadyOnDirect) {
      await chrome.tabs.update(tab.id, { url: directUrl });
      await new Promise((resolve) => {
        const listener = (tabId, info) => {
          if (tabId === tab.id && info.status === 'complete') {
            chrome.tabs.onUpdated.removeListener(listener);
            resolve();
          }
        };
        chrome.tabs.onUpdated.addListener(listener);
        setTimeout(() => {
          chrome.tabs.onUpdated.removeListener(listener);
          resolve();
        }, 10000);
      });
      // Dar tiempo al content script a inyectarse en la nueva página
      await new Promise(r => setTimeout(r, 3500));
    } else {
      await new Promise(r => setTimeout(r, 800));
    }

    // Comprobar que la pestaña sigue en Instagram (p. ej. usuario navegó a otro sitio)
    let currentTab;
    try {
      currentTab = await chrome.tabs.get(tab.id);
    } catch (_) {
      return { success: false, error: 'Pestaña de Instagram cerrada. Abre instagram.com/direct/ y vuelve a Iniciar.' };
    }
    if (!currentTab || !currentTab.url || !currentTab.url.includes('instagram.com')) {
      return { success: false, error: 'Pestaña de Instagram cerrada o cambiada. Abre instagram.com/direct/ y vuelve a Iniciar.' };
    }

    const payload = {
      action: 'send_dm',
      username: username,
      text: message,
      dryRun: dryRun,
    };
    const maxTries = 3;
    let lastErr = null;
    for (let tryNum = 1; tryNum <= maxTries; tryNum++) {
      try {
        console.log('[BG] Enviando mensaje send_dm al content script (tab', tab.id, ', intento', tryNum, ')');
        const result = await chrome.tabs.sendMessage(tab.id, payload);
        console.log('[BG] Resultado del content script:', result);
        if (!result.success && result.error) {
          console.error('[BG] send_dm falló:', result.error, 'steps:', result.steps);
        }
        return result;
      } catch (e) {
        lastErr = e;
        const isReceivingEnd = (e.message || '').includes('Receiving end does not exist');
        if (isReceivingEnd && tryNum < maxTries) {
          console.warn('[BG] Content script no listo, esperando 2s antes de reintentar...');
          await new Promise(r => setTimeout(r, 2000));
        } else {
          throw e;
        }
      }
    }
    throw lastErr;
  } catch (e) {
    console.error('[BG] sendDMViaContentScript error:', e);
    const msg = (e && e.message) || String(e);
    if (msg.includes('Receiving end does not exist')) {
      return {
        success: false,
        error: 'Extensión no conectada a la pestaña. Abre una pestaña en instagram.com/direct/ (o recarga la de Instagram) y vuelve a Iniciar.',
      };
    }
    return { success: false, error: msg };
  }
}

// =====================================================
// LOOP PRINCIPAL DE ENVÍO
// =====================================================

async function processNextTask() {
  await loadState();

  if (state.isProcessing) {
    console.log('[BG] Ya hay un envío en curso, esperando...');
    return;
  }
  state.isProcessing = true;
  
  try {
    if (!state.isRunning) {
      console.log('[BG] Sender no está corriendo');
      return;
    }
    
    // Verificar límite de sesión
    if (state.dmsSentThisSession >= CONFIG.maxDMsPerSession) {
      console.log('[BG] Límite de sesión alcanzado');
      await stopSender('session_limit');
      return;
    }
    
    // Verificar timing
    const now = Date.now();
    if (state.nextDMTime > now) {
      console.log(`[BG] Esperando... próximo DM en ${Math.round((state.nextDMTime - now) / 1000)}s`);
      return;
    }
    
    // Obtener tarea
    console.log('[BG] Pulling task...');
    const task = await pullTask();
    
    if (!task) {
      console.log('[BG] No hay tareas pendientes');
      await stopSender('no_tasks');
      return;
    }
    
    console.log('[BG] Task obtenida:', task);
    state.currentTask = task;
    
    // Extraer datos
    const username = task.dest_username || task.payload?.target_username;
    const message = task.payload?.message_template || task.payload?.message || 'Hola!';
    const dryRun = task.payload?.dry_run !== false;  // Por defecto dry_run = true
    
    if (!username) {
      console.error('[BG] Task sin username');
      await reportResult(task.job_id, task.task_id, false, null, 'missing_username');
      return;
    }
    
    // Ejecutar envío
    console.log(`[BG] Ejecutando DM a ${username} (dryRun: ${dryRun})`);
    const result = await sendDMViaContentScript(username, message, dryRun);
    
    // Reportar resultado
    await reportResult(task.job_id, task.task_id, result.success, username, result.error);
   
    // Actualizar estado
    state.dmsSentThisSession++;
    state.lastDMTime = Date.now();
    if (dryRun) {
      state.nextDMTime = Date.now() + 5000;
    } else {
      state.nextDMTime = Date.now() + randomBetween(CONFIG.minDelayBetweenDMs, CONFIG.maxDelayBetweenDMs);
    }
    state.currentTask = null;
   
    await saveState({
      dm_sender_session_count: state.dmsSentThisSession,
      dm_sender_last_time: state.lastDMTime,
      dm_sender_next_time: state.nextDMTime,
    });
   
    // Notificar al popup
    chrome.runtime.sendMessage({
      type: 'dm_status_update',
      data: {
        lastUsername: username,
        success: result.success,
        sessionCount: state.dmsSentThisSession,
        nextDMTime: state.nextDMTime,
      },
    }).catch(() => {});
   
    if (dryRun) {
      console.log(`[BG] Dry-run OK para ${username}. Siguiente usuario en 5 s.`);
    } else {
      console.log(`[BG] DM ${result.success ? 'exitoso' : 'fallido'} a ${username}. Próximo en ${Math.round((state.nextDMTime - Date.now()) / 60000)} minutos`);
    }
   
    if (dryRun && state.isRunning) {
      setTimeout(() => processNextTask(), 5000);
    }
  } finally {
    state.isProcessing = false;
  }
}

// =====================================================
// CONTROL DEL SENDER
// =====================================================

async function startSender() {
  console.log('[BG] Iniciando sender...');
  
  state.isRunning = true;
  state.dmsSentThisSession = 0;
  state.nextDMTime = Date.now();  // Puede empezar inmediatamente
  
  await saveState({
    dm_sender_running: true,
    dm_sender_session_count: 0,
    dm_sender_next_time: state.nextDMTime,
  });
  
  // Crear alarm para polling periódico
  chrome.alarms.create(state.pollAlarmName, {
    periodInMinutes: CONFIG.pollIntervalMs / 60000,
  });
  
  // Ejecutar inmediatamente
  await processNextTask();
  
  return { status: 'started' };
}

async function stopSender(reason = 'manual') {
  console.log('[BG] Deteniendo sender, razón:', reason);
  
  state.isRunning = false;
  state.isProcessing = false;
  state.currentTask = null;
  
  await saveState({
    dm_sender_running: false,
  });
  
  chrome.alarms.clear(state.pollAlarmName);
  
  chrome.runtime.sendMessage({
    type: 'dm_status_update',
    data: {
      lastUsername: null,
      success: null,
      sessionCount: state.dmsSentThisSession,
      nextDMTime: state.nextDMTime,
      isRunning: false,
    },
  }).catch(() => {});
  
  return { status: 'stopped', reason };
}

async function getSenderStatus() {
  await loadState();
  
  const now = Date.now();
  const timeUntilNext = Math.max(0, state.nextDMTime - now);
  
  return {
    isRunning: state.isRunning,
    sessionCount: state.dmsSentThisSession,
    lastDMTime: state.lastDMTime,
    nextDMTime: state.nextDMTime,
    timeUntilNextMs: timeUntilNext,
    timeUntilNextFormatted: formatTime(timeUntilNext),
    currentTask: state.currentTask,
  };
}

function formatTime(ms) {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

// =====================================================
// EVENT LISTENERS
// =====================================================

// Alarm para polling periódico
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === state.pollAlarmName) {
    console.log('[BG] Alarm triggered, procesando...');
    await processNextTask();
  }
});

// Mensajes desde popup u otros contextos
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('[BG] Mensaje recibido:', message);
  
  if (message.action === 'start_sender') {
    startSender().then(sendResponse);
    return true;
  }
  
  if (message.action === 'stop_sender') {
    stopSender('manual').then(sendResponse);
    return true;
  }
  
  if (message.action === 'get_sender_status') {
    getSenderStatus().then(sendResponse);
    return true;
  }
  
  if (message.action === 'process_now') {
    // Forzar procesamiento inmediato (para testing)
    processNextTask().then(() => sendResponse({ status: 'processed' }));
    return true;
  }
});

// Instalación
chrome.runtime.onInstalled.addListener(async () => {
  console.log('[BG] ScrapInsta instalado');
  await loadState();
  
  // Si estaba corriendo antes, reiniciar el alarm
  if (state.isRunning) {
    chrome.alarms.create(state.pollAlarmName, {
      periodInMinutes: CONFIG.pollIntervalMs / 60000,
    });
  }
});

// Startup
chrome.runtime.onStartup.addListener(async () => {
  console.log('[BG] ScrapInsta startup');
  await loadState();
  
  if (state.isRunning) {
    chrome.alarms.create(state.pollAlarmName, {
      periodInMinutes: CONFIG.pollIntervalMs / 60000,
    });
  }
});

console.log('[BG] Background script cargado');
