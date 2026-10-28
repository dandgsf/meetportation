// Service worker da extensão: ÚNICO ponto que fala com o Python (ws://127.0.0.1:8765).
// Contexto de extensão não sofre o bloqueio "Local Network Access" nem a CSP do Meet.
const WS_URL = "ws://127.0.0.1:8765";
const ports = new Set();
let ws = null, connected = false, frames = 0;

function b64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function broadcast(msg) {
  for (const p of ports) { try { p.postMessage(msg); } catch (e) { ports.delete(p); } }
}

function connect() {
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
  try { ws = new WebSocket(WS_URL); } catch (e) { setTimeout(connect, 1000); return; }
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { connected = true; broadcast({ type: "status", connected: true }); };
  ws.onmessage = (ev) => {
    frames++;
    if (ports.size) broadcast({ type: "frame", jpeg: b64(ev.data) });
  };
  ws.onclose = () => { connected = false; broadcast({ type: "status", connected: false }); setTimeout(connect, 1000); };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "meetportation") return;
  ports.add(port);
  port.postMessage({ type: "status", connected });
  port.onDisconnect.addListener(() => ports.delete(port));
  connect();
});

// mantém o worker vivo enquanto houver abas interessadas
setInterval(() => { if (ports.size) connect(); }, 5000);
connect();
