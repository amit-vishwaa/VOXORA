'use strict';
/* Voxora main: boot, login, shell, router, event delegation. */
const NAV_ADMIN = [['dashboard', 'Dashboard', 'dashboard'], ['companies', 'Companies', 'building'], ['users', 'Users', 'users'], ['agents', 'Agents', 'agent'], ['calls', 'Calls', 'phone'], ['live', 'Live monitor', 'live'], ['billing', 'Billing', 'card'], ['providers', 'Providers', 'plug'], ['audit', 'Audit log', 'shield'], ['support', 'Support', 'help'], ['settings', 'Settings', 'cog']];
const NAV_CLIENT = [['dashboard', 'Dashboard', 'dashboard'], ['agents', 'My agents', 'agent'], ['calls', 'Call history', 'phone'], ['live', 'Live calls', 'live'], ['billing', 'Billing & usage', 'card'], ['support', 'Support', 'help'], ['settings', 'Settings', 'cog']];

window.boot = async function () {
  if (!state.token) return renderLogin();
  try { state.user = (await api('/auth/me')).user; state.meta = await api('/meta'); } catch (e) { return renderLogin(); }
  renderShell(); route();
};

function renderLogin(err) {
  $('#app').innerHTML = h`<div class="login"><div class="card fade"><div class="brand"><div class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M3 12h2m3-6v12m4-9v6m4-8v10m4-5h2"/></svg></div><div>Voxora AI<small>Intelligent Conversations. Limitless Possibilities.</small></div></div>
    <h2 class="mb">Sign in</h2>${err ? h`<div class="banner" style="background:var(--bad-soft);color:var(--bad)">${err}</div>` : ''}
    <form data-form="login">${field('email', 'Email', '', 'email', 'autocomplete="username" required')}${field('password', 'Password', '', 'password', 'autocomplete="current-password" required')}<button class="btn primary" style="width:100%;justify-content:center">Sign in</button></form>
    <p class="muted small mt">Development build · all calls, AI and telephony are simulated.</p></div></div>`.s;
}
forms.login = async d => {
  try { const r = await api('/auth/login', { method: 'POST', data: d }); state.token = r.token; sessionStorage.setItem('vx_token', r.token); location.hash = '#/dashboard'; await boot(); }
  catch (e) { renderLogin(e.message); }
};

function renderShell() {
  const nav = isAdmin() ? NAV_ADMIN : NAV_CLIENT;
  const co = state.user.company ? state.user.company.name : 'Voxora Super Admin';
  $('#app').innerHTML = h`<div class="shell"><aside class="side" id="side"><div class="brand"><div class="logo"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M3 12h2m3-6v12m4-9v6m4-8v10m4-5h2"/></svg></div><div>Voxora<small>${co}</small></div></div>
    <nav class="nav">${nav.map(([k, t, i]) => h`<a href="#/${k}" data-k="${k}">${icon(i)}${t}</a>`)}</nav><div class="grow"></div><button class="btn" data-act="logout">Sign out</button></aside>
    <div class="main"><header class="top"><button class="iconbtn menu-btn" data-act="menu" aria-label="Menu">${icon('menu')}</button><div class="grow"></div>
    <button class="iconbtn" data-act="theme" aria-label="Toggle theme">${icon('sun')}</button><a class="iconbtn" href="#/notifications" aria-label="Notifications">${icon('bell')}<span class="dot" id="bell" hidden></span></a>
    <div class="pill-user"><div class="avatar">${state.user.name[0]}</div><div class="nm"><b>${state.user.name}</b><div class="muted small">${label(state.user.role)}</div></div></div></header>
    <main class="content" id="view"></main></div></div>`.s;
  api('/notifications').then(n => { state.unread = n.unread; updateBell(); }).catch(() => { });
}
function updateBell() { const b = $('#bell'); if (!b) return; b.hidden = !state.unread; b.textContent = state.unread; }
actions.logout = () => logout();
actions.menu = () => $('#side').classList.toggle('open');
actions.close = closeModal;

async function route() {
  if (!state.user) return;
  clearInterval(state.timer); state.timer = null;
  const [path, qs] = (location.hash.slice(2) || 'dashboard').split('?');
  const p = new URLSearchParams(qs || ''), seg = path.split('/');
  let key = seg[0], arg = null;
  if (seg[1]) { key = seg[0] + '/detail'; arg = seg[1]; }
  const base = seg[0];
  document.querySelectorAll('.nav a').forEach(a => a.classList.toggle('active', a.dataset.k === base));
  $('#side').classList.remove('open');
  const adminOnly = ['companies', 'users', 'providers', 'audit'];
  const v = views[key];
  const view = $('#view');
  if (!v || (adminOnly.includes(base) && !isAdmin())) { view.innerHTML = h`<div class="card empty">Page not found</div>`.s; return; }
  try { view.innerHTML = (await v(p, arg)).s; view.firstElementChild && view.classList.add('fade'); }
  catch (e) { view.innerHTML = h`<div class="card empty">${e.message}</div>`.s; }
}
window.addEventListener('hashchange', route);

async function guarded(fn) { try { await fn(); } catch (e) { toast(e.message, true); } }
document.addEventListener('click', e => {
  const t = e.target.closest('[data-act]');
  if (t) { e.preventDefault(); const fn = actions[t.dataset.act]; if (fn) guarded(() => fn(t)); return; }
  const row = e.target.closest('[data-href]'); if (row) location.hash = row.dataset.href;
  if (e.target.classList.contains('overlay')) closeModal();
});
document.addEventListener('submit', e => {
  const f = e.target.closest('form[data-form]'); if (!f) return;
  e.preventDefault();
  const fn = forms[f.dataset.form]; if (!fn) return;
  const d = {}; new FormData(f).forEach((v, k) => { d[k] = v; });
  f.querySelectorAll('input[type=checkbox]').forEach(c => { d[c.name] = c.checked; });
  const btn = f.querySelector('button:not([type=button])'); if (btn) btn.disabled = true;
  guarded(() => fn(d, f)).finally(() => { if (btn) btn.disabled = false; });
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.dataset.nav) {   // filter selects/inputs rewrite the query string of the current route
    const [path, qs] = (location.hash.slice(2) || 'dashboard').split('?'); const p = new URLSearchParams(qs || '');
    t.value ? p.set(t.dataset.nav, t.value) : p.delete(t.dataset.nav); location.hash = '#/' + path + (p.toString() ? '?' + p : '');
  }
  if (t.matches('select[data-lang]')) { const v = t.form.querySelector('[name=voice]'); v.innerHTML = options(state.meta.voices[t.value]).s; }
});
boot();
