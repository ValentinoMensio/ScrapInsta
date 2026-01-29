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
        'div[aria-label*="Message"]',
      ],
      sendButton: [
        'button[type="submit"]',
        'div[role="button"]:has-text("Send")',
        'div[role="button"]:has-text("Enviar")',
        '[aria-label="Send"]',
        '[aria-label="Enviar"]',
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

  async function waitForElement(selectors, timeout = 10000) {
    const selectorList = Array.isArray(selectors) ? selectors : [selectors];
    const startTime = Date.now();
    
    while (Date.now() - startTime < timeout) {
      for (const selector of selectorList) {
        try {
          // Intentar con querySelector estándar primero
          let element = document.querySelector(selector);
          if (element && element.offsetParent !== null) {
            return element;
          }
          
          // Si tiene :has-text, buscar manualmente
          if (selector.includes(':has-text')) {
            const match = selector.match(/:has-text\("([^"]+)"\)/);
            if (match) {
              const text = match[1];
              const baseSelector = selector.replace(/:has-text\("[^"]+"\)/, '');
              const elements = document.querySelectorAll(baseSelector || '*');
              for (const el of elements) {
                if (el.textContent && el.textContent.trim().includes(text)) {
                  if (el.offsetParent !== null) {
                    return el;
                  }
                }
              }
            }
          }
        } catch (e) {
          // Selector inválido, continuar
        }
      }
      await sleep(200);
    }
    return null;
  }

  // =====================================================
  // SIMULACIÓN DE ESCRITURA HUMANA
  // =====================================================
  
  async function typeHumanLike(element, text) {
    // Enfocar el elemento
    element.focus();
    await humanDelay(300, 600);
    
    // Limpiar contenido previo si existe
    if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
      element.value = '';
    } else {
      element.textContent = '';
    }
    
    // Escribir caracter por caracter
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      
      // Insertar caracter
      if (element.tagName === 'TEXTAREA' || element.tagName === 'INPUT') {
        element.value += char;
      } else {
        element.textContent += char;
      }
      
      // Disparar eventos como si fuera input real
      element.dispatchEvent(new Event('input', { bubbles: true }));
      element.dispatchEvent(new KeyboardEvent('keydown', { key: char, bubbles: true }));
      element.dispatchEvent(new KeyboardEvent('keyup', { key: char, bubbles: true }));
      
      // Delay variable entre caracteres
      const baseDelay = HUMAN_CONFIG.typingBaseMs;
      const jitter = randomBetween(-HUMAN_CONFIG.typingJitterMs, HUMAN_CONFIG.typingJitterMs);
      await sleep(Math.max(20, baseDelay + jitter));
      
      // Pausas ocasionales (como si pensara)
      if (Math.random() < 0.05) { // 5% chance de pausa
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

  async function clickMessageButton() {
    console.log('[ScrapInsta] Buscando botón de mensaje...');
    
    const msgBtn = await waitForElement(HUMAN_CONFIG.selectors.messageButton, 8000);
    if (!msgBtn) {
      console.error('[ScrapInsta] No se encontró botón de mensaje');
      return false;
    }
    
    // Pausa humana antes de click
    await humanDelay(HUMAN_CONFIG.profileViewMin, HUMAN_CONFIG.profileViewMax);
    
    console.log('[ScrapInsta] Click en botón de mensaje');
    msgBtn.click();
    
    // Esperar a que aparezca el textarea
    await sleep(1500);
    return true;
  }

  async function typeAndSendMessage(message) {
    console.log('[ScrapInsta] Buscando textarea de mensaje...');
    
    const textarea = await waitForElement(HUMAN_CONFIG.selectors.messageTextarea, 8000);
    if (!textarea) {
      console.error('[ScrapInsta] No se encontró textarea de mensaje');
      return false;
    }
    
    console.log('[ScrapInsta] Escribiendo mensaje...');
    await typeHumanLike(textarea, message);
    
    // Buscar botón de enviar
    console.log('[ScrapInsta] Buscando botón de enviar...');
    const sendBtn = await waitForElement(HUMAN_CONFIG.selectors.sendButton, 5000);
    if (!sendBtn) {
      console.error('[ScrapInsta] No se encontró botón de enviar');
      return false;
    }
    
    // Pausa antes de enviar
    await humanDelay(800, 1500);
    
    console.log('[ScrapInsta] Click en enviar');
    sendBtn.click();
    
    // Esperar confirmación
    await humanDelay(HUMAN_CONFIG.afterSendMin, HUMAN_CONFIG.afterSendMax);
    
    return true;
  }

  // =====================================================
  // FUNCIÓN PRINCIPAL DE ENVÍO (DRY-RUN HABILITADO)
  // =====================================================
  
  async function sendDM(username, message, dryRun = true) {
    console.log(`[ScrapInsta] sendDM iniciado - username: ${username}, dryRun: ${dryRun}`);
    
    const result = {
      success: false,
      username: username,
      error: null,
      dryRun: dryRun,
      steps: [],
    };
    
    try {
      // Paso 1: Navegar al perfil
      result.steps.push('navigate_start');
      const navigated = await navigateToProfile(username);
      if (!navigated) {
        result.error = 'navigation_failed';
        return result;
      }
      result.steps.push('navigate_done');
      
      // Esperar carga completa
      await humanDelay(2000, 4000);
      
      // Paso 2: Click en mensaje
      result.steps.push('message_button_start');
      const clickedMsg = await clickMessageButton();
      if (!clickedMsg) {
        result.error = 'message_button_not_found';
        return result;
      }
      result.steps.push('message_button_done');
      
      // =====================================================
      // DRY-RUN: NO ENVIAR REALMENTE
      // =====================================================
      if (dryRun) {
        console.log('[ScrapInsta] DRY-RUN: Simulando envío exitoso');
        result.steps.push('dry_run_skip_send');
        result.success = true;
        result.dryRunMessage = `Mensaje simulado para ${username}: "${message.substring(0, 50)}..."`;
        return result;
      }
      
      // Paso 3: Escribir y enviar (solo si NO es dry-run)
      result.steps.push('type_and_send_start');
      const sent = await typeAndSendMessage(message);
      if (!sent) {
        result.error = 'send_failed';
        return result;
      }
      result.steps.push('type_and_send_done');
      
      result.success = true;
      console.log('[ScrapInsta] Mensaje enviado exitosamente');
      
    } catch (err) {
      console.error('[ScrapInsta] Error en sendDM:', err);
      result.error = err.message || 'unknown_error';
    }
    
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

