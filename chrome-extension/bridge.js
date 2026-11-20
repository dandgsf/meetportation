// O canvas só existe enquanto este documento está pareado.
(() => {
  let canvas = null, port = null, busy = false;

  function stop() {
    if (!canvas) return;
    canvas.getContext("2d").clearRect(0, 0, canvas.width, canvas.height);
    canvas.remove();
    canvas = null;
    navigator.mediaDevices.dispatchEvent(new Event("devicechange"));
  }

  function start() {
    stop();
    canvas = document.createElement("canvas");
    canvas.id = "meetportation-canvas";
    canvas.width = 1280; canvas.height = 720;
    canvas.style.cssText = "position:fixed;left:-9999px;top:-9999px;width:1px;height:1px;";
    document.documentElement.appendChild(canvas);
    navigator.mediaDevices.dispatchEvent(new Event("devicechange"));
  }

  async function draw(b64) {
    if (!canvas || busy) return;
    const target = canvas;
    busy = true;
    try {
      const blob = await (await fetch("data:image/jpeg;base64," + b64)).blob();
      const bmp = await createImageBitmap(blob);
      if (canvas === target) {
        if (target.width !== bmp.width || target.height !== bmp.height) {
          target.width = bmp.width; target.height = bmp.height;
        }
        target.getContext("2d").drawImage(bmp, 0, 0);
      }
      bmp.close();
    } finally { busy = false; }
  }

  let visible = true;
  function connect() {
    if (!visible || port) return;
    try { port = chrome.runtime.connect({ name: "meetportation" }); } catch { return; }
    const current = port;
    port.onMessage.addListener((m) => {
      if (port !== current) return;
      if (m.type === "start") start();
      else if (m.type === "frame") draw(m.jpeg);
      else if (m.type === "stop") stop();
    });
    port.onDisconnect.addListener(() => {
      if (port !== current) return;
      port = null;
      stop();
      if (visible) setTimeout(connect, 500);
    });
  }
  addEventListener("pagehide", () => {
    visible = false;
    port?.disconnect();
    port = null;
    stop();
  });
  addEventListener("pageshow", () => { visible = true; connect(); });
  connect();
})();
