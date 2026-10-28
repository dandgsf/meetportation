// Mundo isolado: recebe os frames do service worker e desenha num canvas escondido.
(() => {
  const canvas = document.createElement("canvas");
  canvas.id = "meetportation-canvas";
  canvas.width = 1280; canvas.height = 720;
  canvas.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;";
  const ctx = canvas.getContext("2d");
  (document.documentElement || document).appendChild(canvas);

  function placeholder(text) {
    ctx.fillStyle = "#222"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#0f3"; ctx.font = "36px sans-serif";
    ctx.fillText("Meetportation: " + text, 40, 360);
  }
  placeholder("conectando à extensão...");

  let busy = false;
  async function draw(b64) {
    if (busy) return;
    busy = true;
    try {
      const blob = await (await fetch("data:image/jpeg;base64," + b64)).blob();
      const bmp = await createImageBitmap(blob);
      if (canvas.width !== bmp.width || canvas.height !== bmp.height) { canvas.width = bmp.width; canvas.height = bmp.height; }
      ctx.drawImage(bmp, 0, 0); bmp.close();
      canvas.dataset.frames = String((+canvas.dataset.frames || 0) + 1);
    } catch (e) { /* frame inválido */ }
    busy = false;
  }

  function connect() {
    let port;
    try { port = chrome.runtime.connect({ name: "meetportation" }); } catch (e) { setTimeout(connect, 1000); return; }
    port.onMessage.addListener((m) => {
      if (m.type === "frame") draw(m.jpeg);
      else if (m.type === "status") { canvas.dataset.connected = String(m.connected); if (!m.connected) placeholder("aguardando o Python (run-meet.bat)"); }
    });
    port.onDisconnect.addListener(() => setTimeout(connect, 1000));
  }
  connect();
})();
