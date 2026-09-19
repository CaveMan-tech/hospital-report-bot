// Voice notes. Loaded only when the deployment has them switched on.
(() => {
  const mic = document.getElementById('mic'), box = document.getElementById('text'), log = document.getElementById('log');
  if (!mic || !navigator.mediaDevices || !window.MediaRecorder) { if (mic) mic.remove(); return; }
  let rec = null, chunks = [], timer = null, told = false;

  function note(text, err) {
    const d = document.createElement('div');
    d.className = 'm sys' + (err ? ' err' : ''); d.textContent = text;
    log.appendChild(d); d.scrollIntoView({ block: 'end' });
  }
  function stop() { if (rec && rec.state !== 'inactive') rec.stop(); }

  async function start() {
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { note('I could not use the microphone. You can type instead.', true); return; }
    if (!told) { note(window.VOICE_NOTE); told = true; }
    chunks = [];
    rec = new MediaRecorder(stream);
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      clearTimeout(timer);
      stream.getTracks().forEach(t => t.stop());           // release the microphone straight away
      mic.setAttribute('aria-pressed', 'false'); mic.disabled = true;
      const blob = new Blob(chunks, { type: rec.mimeType || 'audio/webm' });
      chunks = [];
      try {
        const r = await fetch('/api/transcribe?pack=' + encodeURIComponent(window.PACK),
          { method: 'POST', headers: { 'Content-Type': blob.type }, body: blob });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : window.OFFLINE);
        box.value = (box.value ? box.value + ' ' : '') + data.text;   // into the box to check, never auto-sent
        box.focus();
      } catch (e) { note(e.message, true); }
      finally { mic.disabled = false; }
    };
    rec.start();
    mic.setAttribute('aria-pressed', 'true');
    timer = setTimeout(stop, 60000);                         // one minute is plenty, and keeps uploads small
  }
  mic.onclick = () => (rec && rec.state === 'recording') ? stop() : start();
})();
