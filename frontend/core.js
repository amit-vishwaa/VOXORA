'use strict';
/* Voxora core: safe templating, API client, charts, modal, toast. All dynamic text is HTML-escaped by default. */
const $ = (s, r = document) => r.querySelector(s);
class Raw { constructor(s) { this.s = s; } }
const raw = s => new Raw(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const part = v => v instanceof Raw ? v.s : Array.isArray(v) ? v.map(part).join('') : esc(v);
function h(strings, ...vals) { let o = strings[0]; vals.forEach((v, i) => { o += part(v) + strings[i + 1]; }); return new Raw(o); }

const state = { token: sessionStorage.getItem('vx_token'), user: null, meta: null, timer: null, unread: 0 };
const isAdmin = () => state.user && state.user.role === 'super_admin';

async function api(path, { method = 'GET', data, blob } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  if (data) headers['Content-Type'] = 'application/json';
  const res = await fetch('/api' + path, { method, headers, body: data ? JSON.stringify(data) : undefined });
  if (blob && res.ok) return res.blob();
  let j = {}; try { j = await res.json(); } catch (e) { /* non-json */ }
  if (res.status === 401 && state.token) { logout(); throw new Error('Session expired, please sign in again'); }
  if (!res.ok) throw new Error(j.error || 'Request failed (' + res.status + ')');
  return j;
}
function logout() { sessionStorage.removeItem('vx_token'); state.token = null; state.user = null; location.hash = ''; window.boot && window.boot(); }

function toast(msg, err) {
  const el = document.createElement('div'); el.className = 'toast' + (err ? ' err' : ''); el.textContent = msg;
  $('#toasts').appendChild(el); setTimeout(() => el.remove(), 4200);
}
function modal(title, content) {
  closeModal();
  const o = document.createElement('div'); o.className = 'overlay'; o.id = 'modal';
  o.innerHTML = h`<div class="modal fade"><div class="row spread mb"><h2>${title}</h2><button class="btn sm" data-act="close">✕</button></div>${content}</div>`.s;
  document.body.appendChild(o);
}
function closeModal() { const m = $('#modal'); if (m) m.remove(); }

/* ---- formatting */
const dt = s => s ? new Date(s.replace(' ', 'T') + 'Z').toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const dur = s => { s = +s || 0; return s >= 60 ? Math.floor(s / 60) + 'm ' + (s % 60) + 's' : s + 's'; };
const inr = n => '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 });
const label = s => String(s || '').replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
const STATUS_CLS = { completed: 'ok', deployed: 'ok', approved: 'ok', paid: 'ok', active: 'ok', resolved: 'ok', positive: 'ok', in_progress: 'info', issued: 'info', testing: 'info', open: 'info',
  transferred: 'warn', pending_approval: 'warn', draft: 'mute', neutral: 'mute', failed: 'bad', no_answer: 'bad', busy: 'warn', rejected: 'bad', suspended: 'bad', negative: 'bad' };
const badge = s => h`<span class="badge b-${STATUS_CLS[s] || 'mute'}">${label(s)}</span>`;
const options = (items, sel) => items.map(i => { const [v, t] = Array.isArray(i) ? i : [i, label(i)]; return h`<option value="${v}" ${String(v) === String(sel) ? raw('selected') : ''}>${t}</option>`; });
const field = (name, lbl, val = '', type = 'text', extra = '') => h`<div class="field"><label>${lbl}</label><input name="${name}" type="${type}" value="${val}" ${raw(extra)}></div>`;

/* ---- charts (inline SVG, no libraries) */
function barChart(series, key = 'calls') {
  const W = 640, H = 190, pad = 26, max = Math.max(1, ...series.map(s => s[key]));
  const bw = (W - pad * 2) / series.length;
  const bars = series.map((s, i) => {
    const bh = (H - pad * 2) * s[key] / max;
    return `<rect class="bar" rx="3" x="${pad + i * bw + bw * .15}" y="${H - pad - bh}" width="${bw * .7}" height="${bh}"><title>${esc(s.date)}: ${s[key]}</title></rect>`;
  }).join('');
  const step = Math.ceil(series.length / 7);
  const labels = series.map((s, i) => i % step === 0 ? `<text class="axis" x="${pad + i * bw + bw / 2}" y="${H - 8}" text-anchor="middle">${esc(s.date.slice(5))}</text>` : '').join('');
  const grid = [0, .5, 1].map(f => `<line class="gridline" x1="${pad}" x2="${W - pad}" y1="${H - pad - (H - pad * 2) * f}" y2="${H - pad - (H - pad * 2) * f}"/><text class="axis" x="2" y="${H - pad - (H - pad * 2) * f + 3}">${Math.round(max * f)}</text>`).join('');
  return raw(`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart">${grid}${bars}${labels}</svg>`);
}
const COLORS = ['#6d5dfc', '#22d3ee', '#12a37f', '#d98a00', '#e5484d', '#8892b0'];
function donut(data) {
  const entries = Object.entries(data).filter(([, v]) => v > 0), total = entries.reduce((a, [, v]) => a + v, 0);
  if (!total) return h`<div class="empty">No data yet</div>`;
  let off = 0; const R = 46, C = 2 * Math.PI * R;
  const arcs = entries.map(([k, v], i) => { const len = C * v / total; const s = `<circle r="${R}" cx="60" cy="60" fill="none" stroke="${COLORS[i % 6]}" stroke-width="16" stroke-dasharray="${len} ${C - len}" stroke-dashoffset="${-off}" transform="rotate(-90 60 60)"><title>${esc(label(k))}: ${v}</title></circle>`; off += len; return s; }).join('');
  const legend = entries.map(([k, v], i) => `<span><i style="background:${COLORS[i % 6]}"></i>${esc(label(k))} ${v}</span>`).join('');
  return raw(`<div class="row"><svg viewBox="0 0 120 120" width="130" height="130">${arcs}<text x="60" y="66" text-anchor="middle" font-size="20" font-weight="700" fill="currentColor">${total}</text></svg><div class="legend" style="flex-direction:column;gap:6px">${legend}</div></div>`);
}
const ICONS = {
  dashboard: 'M3 13h8V3H3zm0 8h8v-6H3zm10 0h8V11h-8zm0-18v6h8V3z', building: 'M4 21V5l8-3v6l8 3v10zM8 9v2m0 4v2m8-2v2', users: 'M16 11a4 4 0 100-8 4 4 0 000 8zM2 21a6 6 0 0112 0m3-6a5 5 0 015 5',
  agent: 'M12 3a3 3 0 013 3v5a3 3 0 11-6 0V6a3 3 0 013-3zM5 11a7 7 0 0014 0M12 18v3', phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z',
  live: 'M2 12h3l3-8 4 16 3-8h7', chart: 'M4 20V10m6 10V4m6 16v-7m5 7H3', card: 'M3 6h18v12H3zM3 10h18', plug: 'M9 2v6m6-6v6M6 8h12v4a6 6 0 01-12 0zM12 18v4', shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z',
  help: 'M12 22a10 10 0 100-20 10 10 0 000 20zM9.5 9a2.5 2.5 0 015 .5c0 1.7-2.5 2-2.5 4M12 17h.01', bell: 'M6 8a6 6 0 0112 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 004 0', sun: 'M12 4V2m0 20v-2M4 12H2m20 0h-2M5.6 5.6L4.2 4.2m15.6 15.6l-1.4-1.4M18.4 5.6l1.4-1.4M4.2 19.8l1.4-1.4M12 17a5 5 0 100-10 5 5 0 000 10z',
  cog: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19 12l2-1-2-4-2 1a7 7 0 00-2-1l-.5-2h-5L9 7a7 7 0 00-2 1L5 7 3 11l2 1a7 7 0 000 2l-2 1 2 4 2-1a7 7 0 002 1l.5 2h5l.5-2a7 7 0 002-1l2 1 2-4-2-1a7 7 0 000-2z', menu: 'M4 6h16M4 12h16M4 18h16'
};
const icon = n => raw(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="${ICONS[n]}"/></svg>`);
