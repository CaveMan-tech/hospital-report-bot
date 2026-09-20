(() => {
  const log = document.getElementById('log'), form = document.getElementById('form');
  const box = document.getElementById('text'), btn = form.querySelector('button');
  // sessionStorage only: it never leaves this device and is wiped when the tab closes.
  const S = {
    get(k) { try { return JSON.parse(sessionStorage.getItem(k)); } catch (e) { return null; } },
    set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  };
  let sid = S.get('sid'), hist = S.get('hist') || [];

  function draw(text, cls) {
    const d = document.createElement('div');
    d.className = 'm ' + cls;
    d.textContent = text;
    // Make the reference code easy to read and copy.
    d.innerHTML = d.innerHTML.replace(/\b([0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4})\b/, '<span class="code">$1</span>');
    // Links in the bot's own words only (never in what the reporter typed). No referrer, new tab.
    if (cls === 'bot') d.innerHTML = d.innerHTML.replace(/https:\/\/[^\s<"'`]+/g, u => `<a href="${u}" target="_blank" rel="noopener noreferrer">${u}</a>`);
    log.appendChild(d);
    d.scrollIntoView({ block: 'end' });
  }
  function add(text, cls) { draw(text, cls); hist.push([text, cls]); S.set('hist', hist); }
  function setSid(v) { sid = v; S.set('sid', v); }
  function drop(id) { const e = document.getElementById(id); if (e) e.remove(); }

  function buttons(id, options, onPick) {
    drop(id);
    if (!options || !options.length) return;
    const row = document.createElement('div');
    row.id = id; row.className = 'quick';
    options.forEach(o => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = o.label;
      b.onclick = () => onPick(o);
      row.appendChild(b);
    });
    log.appendChild(row);
    row.scrollIntoView({ block: 'end' });
  }
  function quick(options) {
    S.set('quick', options && options.length ? options : null);
    buttons('quick', options, o => { add(o.label, 'me'); send(o.value); });
  }

  async function post(url, body) {
    let r;
    try { r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
    catch (e) { throw new Error(window.OFFLINE); }  // no network: still say what to do in danger
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : window.OFFLINE);
    return data;
  }
  function show(data) {
    setSid(data.done ? null : data.session_id);
    data.replies.forEach((t, i) => setTimeout(() => add(t, 'bot'), i * 250));
    setTimeout(() => quick(data.quick_replies), data.replies.length * 250);
  }
  async function send(text) {
    quick(null); drop('retry'); drop('err');
    btn.disabled = true;
    try { show(await post('/api/chat', { session_id: sid, channel: 'web', pack: window.PACK, text })); }
    catch (e) {
      // The message is not lost: one tap sends it again when the network is back.
      const d = document.createElement('div'); d.id = 'err'; d.className = 'm sys err'; d.textContent = e.message;
      log.appendChild(d);
      buttons('retry', [{ label: 'Try again' }], () => send(text));
    }
    finally { btn.disabled = false; box.focus(); }
  }
  function forget() {
    if (sid && navigator.sendBeacon) navigator.sendBeacon('/api/chat/forget',
      new Blob([JSON.stringify({ session_id: sid })], { type: 'application/json' }));
    hist = []; setSid(null); S.set('hist', null); S.set('quick', null);
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    const t = box.value.trim();
    if (!t) return;
    add(t, 'me'); box.value = ''; send(t);
  });
  box.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

  document.getElementById('new').onclick = () => { forget(); log.innerHTML = ''; send(''); };
  // Quick exit: wipe this device, delete the unfinished story on the server, and leave without
  // a trace in the back button. For when someone walks up behind you.
  document.getElementById('exit').onclick = () => { forget(); log.innerHTML = ''; location.replace('https://www.google.com'); };
  document.getElementById('check').onclick = async () => {
    const code = prompt('Enter your code'); if (!code) return;
    try { draw((await post('/api/report/lookup', { ref_code: code })).message, 'bot'); } catch (e) { draw(e.message, 'sys err'); }
  };
  const nd = document.getElementById('nextday');
  if (nd) nd.onclick = async () => {
    const code = prompt('Demo: enter a report code to simulate the next-day check-in'); if (!code) return;
    draw('— one day later —', 'sys');
    try { show(await post('/api/demo/next-day', { ref_code: code })); } catch (e) { draw(e.message, 'sys err'); }
  };

  if (sid && hist.length) {   // the page was reloaded mid-report: carry on where they were
    hist.forEach(([t, c]) => draw(t, c));
    draw('— continuing your report —', 'sys');
    quick(S.get('quick'));
  } else { forget(); send(''); }
})();
