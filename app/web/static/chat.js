(() => {
  const log = document.getElementById('log'), form = document.getElementById('form');
  const box = document.getElementById('text'), btn = form.querySelector('button');
  let sid = null;
  try { sid = sessionStorage.getItem('sid'); } catch (e) {}

  function add(text, cls) {
    const d = document.createElement('div');
    d.className = 'm ' + cls;
    d.textContent = text;
    // Make the reference code easy to read and copy.
    d.innerHTML = d.innerHTML.replace(/\b([0-9A-Z]{4}-[0-9A-Z]{4}-[0-9A-Z]{4})\b/, '<span class="code">$1</span>');
    log.appendChild(d);
    d.scrollIntoView({ block: 'end' });
  }
  function setSid(v) { sid = v; try { v ? sessionStorage.setItem('sid', v) : sessionStorage.removeItem('sid'); } catch (e) {} }

  async function post(url, body) {
    let r;
    try { r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
    catch (e) { throw new Error(window.OFFLINE); }  // no network: still say what to do in danger
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : window.OFFLINE);
    return data;
  }
  function clearQuick() { const q = document.getElementById('quick'); if (q) q.remove(); }
  function quick(options) {
    if (!options || !options.length) return;
    const row = document.createElement('div');
    row.id = 'quick'; row.className = 'quick';
    options.forEach(o => {
      const b = document.createElement('button');
      b.type = 'button'; b.textContent = o.label;
      b.onclick = () => { add(o.label, 'me'); send(o.value); };
      row.appendChild(b);
    });
    log.appendChild(row);
    row.scrollIntoView({ block: 'end' });
  }
  function show(data) {
    setSid(data.done ? null : data.session_id);
    data.replies.forEach((t, i) => setTimeout(() => add(t, 'bot'), i * 250));
    setTimeout(() => quick(data.quick_replies), data.replies.length * 250);
  }
  async function send(text) {
    clearQuick();
    btn.disabled = true;
    try { show(await post('/api/chat', { session_id: sid, channel: 'web', pack: window.PACK, text })); }
    catch (e) { add(e.message, 'sys err'); }
    finally { btn.disabled = false; box.focus(); }
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    const t = box.value.trim();
    if (!t) return;
    add(t, 'me'); box.value = ''; send(t);
  });
  box.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

  document.getElementById('new').onclick = () => { setSid(null); log.innerHTML = ''; send(''); };
  document.getElementById('check').onclick = async () => {
    const code = prompt('Enter your code'); if (!code) return;
    try { add((await post('/api/report/lookup', { ref_code: code })).message, 'bot'); } catch (e) { add(e.message, 'sys err'); }
  };
  const nd = document.getElementById('nextday');
  if (nd) nd.onclick = async () => {
    const code = prompt('Demo: enter a report code to simulate the next-day check-in'); if (!code) return;
    add('— one day later —', 'sys');
    try { show(await post('/api/demo/next-day', { ref_code: code })); } catch (e) { add(e.message, 'sys err'); }
  };

  setSid(null); send('');
})();
