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
    const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || 'Something went wrong. Please try again.');
    return data;
  }
  function show(data) {
    setSid(data.done ? null : data.session_id);
    data.replies.forEach((t, i) => setTimeout(() => add(t, 'bot'), i * 250));
  }
  async function send(text) {
    btn.disabled = true;
    try { show(await post('/api/chat', { session_id: sid, channel: 'web', text })); }
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
