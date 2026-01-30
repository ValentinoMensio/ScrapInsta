// content_script.js - ScrapInsta DM Sender (Humanizado)
// Se ejecuta en instagram.com/* y maneja el envío de DMs con comportamiento humanizado

(function() {
  'use strict';

  // =====================================================
  // CONFIGURACIÓN DE HUMANIZACIÓN
  // =====================================================
  const HUMAN_CONFIG = {
    // Delays entre acciones (ms)
    typingBaseMs: 50,           // Base por caracter
    typingJitterMs: 30,         // ±30ms variación
    thinkingPauseMin: 800,      // Pausa mínima "pensando"
    thinkingPauseMax: 2500,     // Pausa máxima "pensando"
    
    // Tiempos de espera
    profileViewMin: 2000,       // Tiempo viendo perfil
    profileViewMax: 5000,
    afterSendMin: 1500,
    afterSendMax: 3000,
    
    // Selectores de Instagram (pueden cambiar, actualizables)
    selectors: {
      messageButton: [
        'div[role="button"]:has-text("Message")',
        'div[role="button"]:has-text("Mensaje")',
        'button:has-text("Message")',
        '[aria-label="Message"]',
        '[aria-label="Mensaje"]',
      ],
      messageTextarea: [
        'textarea[placeholder*="Message"]',
        'textarea[placeholder*="Mensaje"]',
        'div[role="textbox"][contenteditable="true"]',
        'div[contenteditable="true"]',
        'div[aria-label*="Message"]',
      ],
      sendButton: [
        'button[type="submit"]',
        'div[role="button"]:has-text("Send")',
        'div[role="button"]:has-text("Enviar")',
        '[aria-label="Send"]',
        '[aria-label="Enviar"]',
      ],
      // Flujo desde /direct (instagram.com/direct)
      directSearchInput: [
        'input[placeholder="Search"]',
        'input[name="searchInput"]',
        'input[aria-label*="Search"]',
      ],
      directMessageInput: [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        '[aria-label="Message"][contenteditable="true"]',
        '[aria-label="Mensaje"][contenteditable="true"]',
        'div[role="textbox"]',
        'p[dir="auto"]',
      ],
    },
  };

  // =====================================================
  // UTILIDADES
  // =====================================================
  
  function randomBetween(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function humanDelay(minMs, maxMs) {
    const delay = randomBetween(minMs, maxMs);
    await sleep(delay);
    return delay;
  }

  async function waitForElement(selectors, timeout = 10000, logLabel = 'element') {
    const selectorList = Array.isArray(selectors) ? selectors : [selectors];
    const startTime = Date.now();
    let lastLog = 0;
    
    while (Date.now() - startTime < timeout) {
      for (let i = 0; i < selectorList.length; i++) {
        const selector = selectorList[i];
        try {
          // Intentar con querySelector estándar primero (solo si no tiene :has-text)
          if (!selector.includes(':has-text')) {
            const element = document.querySelector(selector);
            if (element && element.offsetParent !== null) {
              console.log(`[ScrapInsta] ${logLabel} encontrado con selector [${i}]:`, selector.substring(0, 60));
              return element;
            }
          } else {
            // Si tiene :has-text, buscar manualmente
            const match = selector.match(/:has-text\("([^"]+)"\)/);
            if (match) {
              const text = match[1];
              const baseSelector = selector.replace(/:has-text\("[^"]+"\)/, '').trim();
              const root = baseSelector ? document.querySelectorAll(baseSelector) : document.querySelectorAll('*');
              const elements = Array.from(root);
              for (const el of elements) {
                if (el.textContent && el.textContent.trim().includes(text)) {
                  if (el.offsetParent !== null) {
                    console.log(`[ScrapInsta] ${logLabel} encontrado con :has-text("${text}") [${i}]`);
                    return el;
                  }
                }
              }
            }
          }
        } catch (e) {
            console.debug(`[ScrapInsta] selector [${i}] error:`, e.message);
        }
      }
      const elapsed = Date.now() - startTime;
      if (elapsed - lastLog > 3000) {
        console.log(`[ScrapInsta] Esperando ${logLabel}... ${Math.round(elapsed / 1000)}s (selectores: ${selectorList.length})`);
        lastLog = elapsed;
      }
      await sleep(200);
    }
    console.error(`[ScrapInsta] TIMEOUT: no se encontró ${logLabel} después de ${timeout}ms. Selectores probados:`, selectorList);
    return null;
  }

  // =====================================================
  // SIMULACIÓN DE ESCRITURA HUMANA
  // =====================================================
  
  function placeCaretInContentEditable(editable) {
    try {
      editable.focus();
      const sel = window.getSelection();
      const range = document.createRange();
      range.selectNodeContents(editable);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    } catch (e) {
      editable.focus();
    }
  }

  async function typeHumanLike(element, text) {
    const isInputOrTextarea = element.tagName === 'TEXTAREA' || element.tagName === 'INPUT';
    if (isInputOrTextarea) {
      element.focus();
      await humanDelay(300, 600);
      element.value = '';
      element.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
      const editable = element.getAttribute('contenteditable') === 'true' ? element : (element.closest('[contenteditable="true"]') || element);
      editable.focus();
      placeCaretInContentEditable(editable);
      await humanDelay(300, 600);
      // No vaciar el DOM en editores tipo Lexical: solo colocar cursor y escribir
    }

    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (isInputOrTextarea) {
        element.value += char;
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        element.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
      } else {
        const editable = element.getAttribute('contenteditable') === 'true' ? element : (element.closest('[contenteditable="true"]') || element);
        editable.focus();
        const inserted = document.execCommand('insertText', false, char);
        if (!inserted) {
          editable.textContent = (editable.textContent || '') + char;
          editable.dispatchEvent(new InputEvent('input', { bubbles: true, data: char, inputType: 'insertText' }));
        }
        editable.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
        editable.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
      }
      const baseDelay = HUMAN_CONFIG.typingBaseMs;
      const jitter = randomBetween(-HUMAN_CONFIG.typingJitterMs, HUMAN_CONFIG.typingJitterMs);
      await sleep(Math.max(20, baseDelay + jitter));
      if (Math.random() < 0.05) {
        await humanDelay(HUMAN_CONFIG.thinkingPauseMin, HUMAN_CONFIG.thinkingPauseMax);
      }
    }
    
    // Pausa final antes de enviar
    await humanDelay(500, 1200);
  }

  // =====================================================
  // FUNCIONES DE ENVÍO DE DM
  // =====================================================
  
  async function navigateToProfile(username) {
    const profileUrl = `https://www.instagram.com/${username}/`;
    
    // Si ya estamos en el perfil, no navegar
    if (window.location.href.includes(`/${username}/`) || 
        window.location.href.includes(`/${username}`)) {
      console.log('[ScrapInsta] Ya estamos en el perfil:', username);
      return true;
    }
    
    console.log('[ScrapInsta] Navegando a perfil:', profileUrl);
    window.location.href = profileUrl;
    
    // Esperar a que cargue la página
    return new Promise((resolve) => {
      const checkLoaded = setInterval(() => {
        if (document.readyState === 'complete') {
          clearInterval(checkLoaded);
          resolve(true);
        }
      }, 100);
      
      // Timeout de 15 segundos
      setTimeout(() => {
        clearInterval(checkLoaded);
        resolve(false);
      }, 15000);
    });
  }

  // =====================================================
  // FLUJO DESDE /direct (más estable que perfil → Message)
  // =====================================================

  async function navigateToDirect() {
    const directUrl = 'https://www.instagram.com/direct/';
    if (window.location.href.startsWith(directUrl) || (window.location.pathname && window.location.pathname.startsWith('/direct'))) {
      console.log('[ScrapInsta] Ya estamos en /direct (inbox o conversación)');
      return true;
    }
    console.log('[ScrapInsta] Navegando a /direct');
    window.location.href = directUrl;
    return new Promise((resolve) => {
      const t = setTimeout(() => resolve(true), 12000);
      const check = setInterval(() => {
        if (document.readyState === 'complete' && window.location.pathname === '/direct/') {
          clearInterval(check);
          clearTimeout(t);
          resolve(true);
        }
      }, 200);
    });
  }

  async function directSearchAndOpenThread(username) {
    console.log('[ScrapInsta] Paso: buscar input de búsqueda en /direct');
    const searchInput = await waitForElement(HUMAN_CONFIG.selectors.directSearchInput, 10000, 'search input');
    if (!searchInput) {
      console.error('[ScrapInsta] No se encontró el input de búsqueda en /direct');
      return false;
    }
    searchInput.focus();
    await humanDelay(300, 600);
    searchInput.value = '';
    searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(300);
    // Escribir username
    for (const c of username) {
      searchInput.value += c;
      searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: c, bubbles: true }));
      searchInput.dispatchEvent(new KeyboardEvent('keyup', { key: c, bubbles: true }));
      await sleep(80 + randomBetween(-20, 40));
    }
    searchInput.dispatchEvent(new Event('input', { bubbles: true }));
    const uname = username.toLowerCase();

    function rowMatchesUsername(row, u) {
      if ((row.textContent || '').toLowerCase().includes(u)) return true;
      const link = row.querySelector('a[href*="' + u + '"]') || row.querySelector('a[href*="/' + u + '/"]');
      return !!link;
    }

    function findResultRows() {
      let scope = document.body;
      const headings = document.querySelectorAll('h2');
      for (const h of headings) {
        const t = (h.textContent || '').trim().toLowerCase();
        if (t.includes('more accounts') || t.includes('más cuentas') || t.includes('accounts')) {
          scope = h.closest('div') || h.parentElement;
          break;
        }
      }
      const candidateButtons = scope.querySelectorAll('div[role="button"]');
      const rows = [];
      for (const btn of candidateButtons) {
        if (btn.offsetParent === null) continue;
        if (!btn.querySelector('img[alt="User avatar"]')) continue;
        rows.push(btn);
      }
      return rows;
    }

    for (let attempt = 0; attempt < 4; attempt++) {
      const waitMs = attempt === 0 ? 3000 : attempt === 1 ? 2500 : 2000;
      await sleep(waitMs);
      const resultRows = findResultRows();
      if (resultRows.length > 0) {
        const match = resultRows.find(r => rowMatchesUsername(r, uname)) || resultRows[0];
        console.log('[ScrapInsta] Paso: clic en resultado del dropdown (', resultRows.length, 'filas, intento', attempt + 1, ', match username:', rowMatchesUsername(match, uname), ')');
        match.click();
        await sleep(2000);
        return true;
      }
      if (attempt < 3) {
        console.log('[ScrapInsta] Dropdown aún no visible, esperando', waitMs / 1000, 's más...');
      }
    }

    // Fallback: cualquier div[role="button"] con avatar que contenga el username (texto o enlace)
    const allAvatarButtons = document.querySelectorAll('div[role="button"]');
    for (const btn of allAvatarButtons) {
      if (btn.offsetParent === null) continue;
      if (!btn.querySelector('img[alt="User avatar"]')) continue;
      if (rowMatchesUsername(btn, uname)) {
        console.log('[ScrapInsta] Paso: clic en resultado por username (fallback)');
        btn.click();
        await sleep(2000);
        return true;
      }
    }

    // Fallback: enlace a perfil que contenga el username (resultados de búsqueda)
    const profileLinks = document.querySelectorAll('a[href*="' + uname + '"]');
    for (const a of profileLinks) {
      if (a.offsetParent === null) continue;
      const href = (a.getAttribute('href') || '').toLowerCase();
      if (href.includes('instagram.com') && (href.includes('/' + uname + '/') || href.endsWith('/' + uname))) {
        const row = a.closest('div[role="button"]');
        if (row && row.querySelector('img[alt="User avatar"]')) {
          console.log('[ScrapInsta] Paso: clic en resultado por enlace de perfil');
          row.click();
          await sleep(2000);
          return true;
        }
      }
    }

    const links = document.querySelectorAll('a[href*="/direct/"]');
    for (const a of links) {
      if (a.offsetParent === null) continue;
      const href = (a.getAttribute('href') || '').toLowerCase();
      const text = (a.textContent || '').toLowerCase();
      if (href.includes('/direct/t/') && (text.includes(uname) || href.includes(uname))) {
        console.log('[ScrapInsta] Paso: abrir conversación por enlace');
        a.click();
        await sleep(2000);
        return true;
      }
    }
    for (const a of links) {
      if (a.offsetParent !== null && (a.getAttribute('href') || '').includes('/direct/t/')) {
        a.click();
        await sleep(2000);
        return true;
      }
    }
    console.error('[ScrapInsta] No se encontró resultado de búsqueda para', username);
    return false;
  }

  async function sendDMViaDirect(username, message, dryRun) {
    console.log('[ScrapInsta] ========== sendDMViaDirect INICIO ==========');
    const result = { success: false, username, error: null, dryRun, steps: [] };
    try {
      result.steps.push('navigate_direct');
      const okNav = await navigateToDirect();
      if (!okNav) {
        result.error = 'navigation_direct_failed';
        return result;
      }
      await humanDelay(2000, 3500);
      result.steps.push('search_user');
      const okSearch = await directSearchAndOpenThread(username);
      if (!okSearch) {
        result.error = 'search_or_open_thread_failed';
        return result;
      }
      await humanDelay(1500, 2500);
      result.steps.push('type_message');
      const messageInput = await waitForElement(HUMAN_CONFIG.selectors.directMessageInput, 8000, 'message input /direct');
      if (!messageInput) {
        result.error = 'message_input_not_found';
        return result;
      }
      messageInput.focus();
      await humanDelay(400, 700);
      if (messageInput.tagName === 'P' || messageInput.getAttribute('contenteditable') !== 'true') {
        const editable = messageInput.closest('[contenteditable="true"]') || document.querySelector('div[contenteditable="true"]');
        if (editable) {
          editable.focus();
          await typeHumanLike(editable, message);
        } else {
          await typeHumanLike(messageInput, message);
        }
      } else {
        await typeHumanLike(messageInput, message);
      }
      if (dryRun) {
        result.steps.push('dry_run_skip_send');
        result.success = true;
        result.dryRunMessage = `Dry-run: texto escrito en la caja para ${username}, sin enviar. Pasando al siguiente.`;
        return result;
      }
      result.steps.push('send');
      const sendBtn = await waitForSendButton(5000);
      if (!sendBtn) {
        result.error = 'send_button_not_found';
        return result;
      }
      await humanDelay(600, 1200);
      sendBtn.click();
      await humanDelay(HUMAN_CONFIG.afterSendMin, HUMAN_CONFIG.afterSendMax);
      result.success = true;
      result.steps.push('sent');
    } catch (err) {
      console.error('[ScrapInsta] sendDMViaDirect error:', err);
      result.error = err.message || 'unknown_error';
    }
    console.log('[ScrapInsta] ========== sendDMViaDirect FIN ========== success:', result.success, 'error:', result.error);
    return result;
  }

  async function clickMessageButton() {
    console.log('[ScrapInsta] Paso: buscar botón "Message"...');
    
    const msgBtn = await waitForElement(HUMAN_CONFIG.selectors.messageButton, 8000, 'botón Message');
    if (!msgBtn) {
      console.error('[ScrapInsta] ERROR: No se encontró el botón de mensaje. Instagram puede haber cambiado el DOM.');
      return false;
    }
    
    // Pausa humana antes de click
    await humanDelay(HUMAN_CONFIG.profileViewMin, HUMAN_CONFIG.profileViewMax);
    
    console.log('[ScrapInsta] Paso: click en botón Message');
    msgBtn.click();
    
    // Esperar a que aparezca el textarea
    await sleep(1500);
    return true;
  }

  // Buscar botón Send: Instagram suele usar svg[aria-label="Send"] dentro de div[role="button"]
  function findSendButton() {
    const labels = ['Send', 'Enviar'];
    for (const label of labels) {
      const svg = document.querySelector(`svg[aria-label="${label}"]`);
      if (svg) {
        const btn = svg.closest('[role="button"]') || svg.closest('button') || svg.parentElement;
        if (btn) {
          console.log('[ScrapInsta] Botón Send encontrado por svg[aria-label="' + label + '"]');
          return btn;
        }
      }
    }
    const byAria = document.querySelector('[aria-label="Send"], [aria-label="Enviar"]');
    if (byAria) return byAria;
    return null;
  }

  async function waitForSendButton(timeout = 8000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const btn = findSendButton();
      if (btn && btn.offsetParent !== null) return btn;
      await sleep(300);
    }
    // Fallback: selectores clásicos
    return waitForElement(HUMAN_CONFIG.selectors.sendButton, 3000, 'botón Send');
  }

  async function typeAndSendMessage(message) {
    console.log('[ScrapInsta] Paso: buscar caja de texto del mensaje...');
    
    const textarea = await waitForElement(HUMAN_CONFIG.selectors.messageTextarea, 8000, 'textarea mensaje');
    if (!textarea) {
      console.error('[ScrapInsta] ERROR: No se encontró el textarea del mensaje.');
      return false;
    }
    
    console.log('[ScrapInsta] Paso: escribir mensaje (' + message.length + ' caracteres)');
    await typeHumanLike(textarea, message);
    
    console.log('[ScrapInsta] Paso: buscar botón Enviar...');
    const sendBtn = await waitForSendButton(5000);
    if (!sendBtn) {
      console.error('[ScrapInsta] ERROR: No se encontró el botón de enviar (probado svg[aria-label=Send] y selectores clásicos).');
      return false;
    }
    
    await humanDelay(800, 1500);
    
    console.log('[ScrapInsta] Paso: click en Enviar');
    sendBtn.click();
    
    await humanDelay(HUMAN_CONFIG.afterSendMin, HUMAN_CONFIG.afterSendMax);
    
    return true;
  }

  // =====================================================
  // FUNCIÓN PRINCIPAL DE ENVÍO
  // Por defecto usa /direct (más estable); fallback a perfil → Message
  // =====================================================
  
  async function sendDM(username, message, dryRun = true) {
    console.log(`[ScrapInsta] ========== sendDM INICIO ==========`);
    console.log(`[ScrapInsta] username: ${username}, dryRun: ${dryRun}, URL actual: ${window.location.href}`);
    
    // Preferir flujo desde /direct (instagram.com/direct): buscar usuario, abrir chat, escribir, Send
    if (window.location.hostname === 'www.instagram.com') {
      const directResult = await sendDMViaDirect(username, message, dryRun);
      console.log('[ScrapInsta] ========== sendDM FIN ========== success:', directResult.success, 'error:', directResult.error, 'steps:', directResult.steps);
      return directResult;
    }
    
    const result = { success: false, username, error: null, dryRun, steps: [] };
    try {
      result.steps.push('navigate_start');
      const navigated = await navigateToProfile(username);
      if (!navigated) {
        result.error = 'navigation_failed';
        return result;
      }
      result.steps.push('navigate_done');
      await humanDelay(2000, 4000);
      result.steps.push('message_button_start');
      const clickedMsg = await clickMessageButton();
      if (!clickedMsg) {
        result.error = 'message_button_not_found';
        return result;
      }
      result.steps.push('message_button_done');
      if (dryRun) {
        result.steps.push('dry_run_skip_send');
        result.success = true;
        result.dryRunMessage = `Mensaje simulado para ${username}: "${message.substring(0, 50)}..."`;
        return result;
      }
      result.steps.push('type_and_send_start');
      const sent = await typeAndSendMessage(message);
      if (!sent) {
        result.error = 'send_failed';
        return result;
      }
      result.steps.push('type_and_send_done');
      result.success = true;
    } catch (err) {
      console.error('[ScrapInsta] Error en sendDM:', err);
      result.error = err.message || 'unknown_error';
      result.steps.push('error: ' + result.error);
    }
    console.log('[ScrapInsta] ========== sendDM FIN ========== success:', result.success, 'error:', result.error, 'steps:', result.steps);
    return result;
  }

  // =====================================================
  // COMUNICACIÓN CON BACKGROUND SCRIPT
  // =====================================================
  
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log('[ScrapInsta CS] Mensaje recibido:', message);
    
    if (message.action === 'send_dm') {
      const { username, text, dryRun } = message;
      
      // Ejecutar async y responder
      sendDM(username, text, dryRun !== false)
        .then(result => {
          console.log('[ScrapInsta CS] Resultado:', result);
          sendResponse(result);
        })
        .catch(err => {
          console.error('[ScrapInsta CS] Error:', err);
          sendResponse({ success: false, error: err.message });
        });
      
      // Retornar true para indicar que la respuesta será asíncrona
      return true;
    }
    
    if (message.action === 'ping') {
      sendResponse({ status: 'ok', url: window.location.href });
      return false;
    }
  });

  // Indicar que el content script está cargado
  console.log('[ScrapInsta] Content script cargado en:', window.location.href);

})();

