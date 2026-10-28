// Mundo da página: faz o Meet "enxergar" o canvas como webcam.
(() => {
  const md = navigator.mediaDevices;
  if (!md || md.__meetportation) return;
  md.__meetportation = true;
  const origGUM = md.getUserMedia.bind(md);
  const origEnum = md.enumerateDevices.bind(md);
  const FAKE_ID = "meetportation-cam";
  const LABEL = "Meetportation (teletransporte)";
  let stream = null;

  function canvasStream() {
    const c = document.getElementById("meetportation-canvas");
    if (!c) return null;
    if (!stream || !stream.active) stream = c.captureStream(30);
    return stream;
  }

  function wantsFake(constraints) {
    const v = constraints && constraints.video;
    if (!v) return false;
    if (v === true) return true;
    const id = v.deviceId && (v.deviceId.exact || v.deviceId.ideal || v.deviceId);
    if (!id) return true;                          // sem deviceId: usa a nossa
    const ids = Array.isArray(id) ? id : [id];
    return ids.includes(FAKE_ID);
  }

  md.enumerateDevices = async () => {
    const devs = await origEnum();
    const fake = { deviceId: FAKE_ID, groupId: "meetportation", kind: "videoinput", label: LABEL,
                   toJSON() { return this; } };
    return [fake, ...devs];
  };

  md.getUserMedia = async (constraints) => {
    if (!wantsFake(constraints)) return origGUM(constraints);
    const cs = canvasStream();
    if (!cs) return origGUM(constraints);
    const out = new MediaStream();
    const vt = cs.getVideoTracks()[0].clone();
    try { Object.defineProperty(vt, "label", { value: LABEL }); } catch (e) {}
    const origSettings = vt.getSettings.bind(vt);
    vt.getSettings = () => ({ ...origSettings(), deviceId: FAKE_ID, groupId: "meetportation" });
    out.addTrack(vt);
    if (constraints.audio) {
      const a = await origGUM({ audio: constraints.audio });
      a.getAudioTracks().forEach((t) => out.addTrack(t));
    }
    return out;
  };
  console.log("[Meetportation] câmera virtual ativa nesta aba");
})();
