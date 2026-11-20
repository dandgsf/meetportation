// Um Port identifica o documento do Meet. Uma navegação exige nova autorização.
const WS_URL = "ws://127.0.0.1:8765";
const documents = new Map();
let active = null;

function b64(buf) {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function stop() {
  if (!active) return;
  const { port, ws, reply } = active;
  active = null;
  ws.close();
  try { port.postMessage({ type: "stop" }); } catch {}
  if (reply) reply({ ok: false, message: "Pareamento encerrado." });
}

chrome.runtime.onConnect.addListener((port) => {
  const sender = port.sender;
  if (port.name !== "meetportation" || sender.frameId !== 0 || sender.tab?.id == null ||
      sender.origin !== "https://meet.google.com" || new URL(sender.url).origin !== sender.origin) {
    port.disconnect();
    return;
  }
  const id = sender.tab.id;
  if (active && active.port === documents.get(id)) stop();
  documents.set(id, port);
  port.onDisconnect.addListener(() => {
    if (documents.get(id) === port) documents.delete(id);
    if (active?.port === port) stop();
  });
});

chrome.runtime.onMessage.addListener((request, sender, reply) => {
  if (sender.url !== chrome.runtime.getURL("popup.html")) return;
  const port = documents.get(request.tabId);
  if (!port) {
    reply({ ok: false, message: "Abra ou recarregue a aba do Google Meet." });
    return;
  }
  if (request.type === "target") {
    reply({ documentId: port.sender.documentId });
    return;
  }
  if (!request.documentId || request.documentId !== port.sender.documentId) {
    reply({ ok: false, message: "A aba mudou. Reabra a extensão na reunião." });
    return;
  }
  if (request.type === "stop") {
    if (active?.port === port) stop();
    reply({ ok: true, message: "Vídeo desligado nesta aba." });
    return;
  }
  if (request.type !== "pair" || !/^[A-Za-z0-9_-]{32}$/.test(request.code)) {
    reply({ ok: false, message: "Confira o código de pareamento." });
    return;
  }
  stop();
  const ws = new WebSocket(WS_URL);
  const session = active = { port, ws, reply };
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { if (active === session) ws.send(request.code); };
  ws.onmessage = ({ data }) => {
    if (active !== session) return;
    if (session.reply) {
      if (data !== "ok") { stop(); return; }
      session.reply = null;
      port.postMessage({ type: "start" });
      reply({ ok: true, message: "Câmera ligada nesta aba." });
    } else if (data instanceof ArrayBuffer) {
      port.postMessage({ type: "frame", jpeg: b64(data) });
    }
  };
  ws.onclose = () => {
    if (active !== session) return;
    if (session.reply) {
      session.reply = null;
      reply({ ok: false, message: "Confira o código e se o programa está aberto." });
    }
    stop();
  };
  return true;
});
