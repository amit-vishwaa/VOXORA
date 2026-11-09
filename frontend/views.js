'use strict';
/* Voxora views. Each view: async (params) => Raw html. Interactions use data-act / data-form (CSP forbids inline handlers). */
const views = {}, actions = {}, forms = {};
const pageHead = (title, sub, right = '') => h`<div class="page-head"><div><h1>${title}</h1><div class="muted">${sub}</div></div><div class="row">${right}</div></div>`;
const table = (cols, rows, empty = 'Nothing here yet') => rows.length
  ? h`<div class="table-wrap"><table><thead><tr>${cols.map(c => h`<th>${c}</th>`)}</tr></thead><tbody>${rows}</tbody></table></div>` : h`<div class="card empty">${empty}</div>`;

/* ---------------- dashboard */
views.dashboard = async (p) => {
  const days = +p.get('days') || 30, co = p.get('company_id') || '';
  const q = `?days=${days}` + (co && isAdmin() ? `&company_id=${co}` : '');
  const [a, cos] = await Promise.all([api('/analytics/overview' + q), isAdmin() ? api('/companies') : { items: [] }]);
  const t = a.totals;
  return h`${pageHead(isAdmin() ? 'Platform overview' : 'Your voice agents at a glance', `Last ${days} days · simulated development data`,
    h`${isAdmin() ? h`<select data-nav="company_id">${options([['', 'All companies'], ...cos.items.map(c => [c.id, c.name])], co)}</select>` : ''}
      <select data-nav="days">${options([[7, '7 days'], [30, '30 days'], [90, '90 days']], days)}</select>`)}
  <div class="grid g4 mb">
    <div class="card kpi"><div class="label">Total calls</div><div class="value">${t.calls}</div><div class="sub">${t.answered} answered · ${t.missed} missed</div></div>
    <div class="card kpi"><div class="label">Billable minutes</div><div class="value">${t.minutes}</div><div class="sub">avg call ${dur(t.avg_duration)}</div></div>
    <div class="card kpi"><div class="label">Success rate</div><div class="value">${t.success_rate}%</div><div class="sub">${t.handovers} human handovers</div></div>
    <div class="card kpi"><div class="label">${isAdmin() && !co ? 'Active companies' : 'Deployed agents'}</div><div class="value">${isAdmin() && !co ? a.companies : a.deployed_agents}</div><div class="sub">${a.deployed_agents} agents live${isAdmin() ? ' · ' + t.provider_errors + ' provider errors' : ''}</div></div>
  </div>
  <div class="grid g2 mb"><div class="card"><div class="row spread"><h2>Calls per day</h2><span class="muted small">${a.days} days</span></div><div class="mt">${barChart(a.series, 'calls')}</div></div>
    <div class="card"><h2>Call outcomes</h2><div class="mt">${donut(a.status)}</div><h2 class="mt">Sentiment</h2><div class="mt">${donut(a.sentiment)}</div></div></div>
  <div class="card"><h2>Calls by agent</h2><div class="mt">${a.by_agent.length ? a.by_agent.map(x => h`<div class="mb"><div class="row spread small"><b>${x.name}</b><span class="muted">${x.calls} calls · ${x.minutes} min</span></div><div class="hbar"><i style="width:${Math.round(100 * x.calls / a.by_agent[0].calls)}%"></i></div></div>`) : h`<div class="empty">No calls in this period</div>`}</div></div>`;
};

/* ---------------- companies (admin) */
views.companies = async () => {
  const { items } = await api('/companies');
  return h`${pageHead('Companies', 'Client organisations on the platform', h`<button class="btn primary" data-act="new-company">+ New company</button>`)}
  ${table(['Company', 'Industry', 'Plan', 'Status', 'Agents', 'Users', 'Calls', ''], items.map(c => h`<tr><td><b>${c.name}</b><div class="muted small">${c.contact_email}</div></td><td>${label(c.industry)}</td><td>${label(c.plan)}</td><td>${badge(c.status)}</td><td>${c.agents}</td><td>${c.users}</td><td>${c.calls}</td>
    <td class="right nowrap"><button class="btn sm" data-act="edit-company" data-id="${c.id}" data-plan="${c.plan}" data-status="${c.status}">Edit</button></td></tr>`))}`;
};
actions['new-company'] = () => modal('New company', h`<form data-form="company">${field('name', 'Company name')}${field('contact_email', 'Contact email', '', 'email')}
  <div class="fgrid"><div class="field"><label>Industry</label><select name="industry">${options(state.meta.industries)}</select></div><div class="field"><label>Plan</label><select name="plan">${options(state.meta.plans.map(p => [p.code, p.name + ' (' + inr(p.monthly_fee) + '/mo)']))}</select></div></div><button class="btn primary">Create</button></form>`);
forms.company = async d => { await api('/companies', { method: 'POST', data: d }); closeModal(); toast('Company created'); route(); };
actions['edit-company'] = el => modal('Edit company', h`<form data-form="company-edit" data-id="${el.dataset.id}"><div class="fgrid"><div class="field"><label>Plan</label><select name="plan">${options(state.meta.plans.map(p => [p.code, p.name]), el.dataset.plan)}</select></div>
  <div class="field"><label>Status</label><select name="status">${options(['active', 'suspended'], el.dataset.status)}</select></div></div><p class="muted small">Suspending a company blocks all of its users immediately.</p><button class="btn primary">Save</button></form>`);
forms['company-edit'] = async (d, f) => { await api('/companies/' + f.dataset.id, { method: 'PATCH', data: d }); closeModal(); toast('Company updated'); route(); };

/* ---------------- users (admin) */
views.users = async () => {
  const [{ items }, cos] = await Promise.all([api('/users'), api('/companies')]);
  window._companies = cos.items;
  return h`${pageHead('Users', 'Super admins and client accounts', h`<button class="btn primary" data-act="new-user">+ New user</button>`)}
  ${table(['Name', 'Email', 'Role', 'Company', 'Status', ''], items.map(u => h`<tr><td><b>${u.name}</b></td><td>${u.email}</td><td>${label(u.role)}</td><td>${u.company_name || '—'}</td><td>${badge(u.active ? 'active' : 'suspended')}</td>
    <td class="right nowrap"><button class="btn sm" data-act="toggle-user" data-id="${u.id}" data-active="${u.active}">${u.active ? 'Disable' : 'Enable'}</button> <button class="btn sm" data-act="reset-pw" data-id="${u.id}">Reset password</button></td></tr>`))}`;
};
actions['new-user'] = () => modal('New user', h`<form data-form="user">${field('name', 'Full name')}${field('email', 'Email', '', 'email')}${field('password', 'Temporary password (min 8)', '', 'password', 'autocomplete="new-password"')}
  <div class="fgrid"><div class="field"><label>Role</label><select name="role">${options(['client', 'super_admin'])}</select></div><div class="field"><label>Company (clients)</label><select name="company_id">${options(window._companies.map(c => [c.id, c.name]))}</select></div></div><button class="btn primary">Create</button></form>`);
forms.user = async d => { if (d.role !== 'client') delete d.company_id; await api('/users', { method: 'POST', data: d }); closeModal(); toast('User created'); route(); };
actions['toggle-user'] = async el => { await api('/users/' + el.dataset.id, { method: 'PATCH', data: { active: el.dataset.active !== '1' } }); route(); };
actions['reset-pw'] = async el => { const pw = prompt('New password (min 8 characters):'); if (!pw) return; await api('/users/' + el.dataset.id, { method: 'PATCH', data: { password: pw } }); toast('Password updated'); };

/* ---------------- agents */
views.agents = async () => {
  const { items } = await api('/agents');
  if (isAdmin()) window._companies = (await api('/companies')).items;
  return h`${pageHead('Agents', isAdmin() ? 'Configure, test and deploy voice agents' : 'Your assigned voice agents', isAdmin() ? h`<button class="btn primary" data-act="new-agent">+ New agent</button>` : '')}
  ${table(['Agent', ...(isAdmin() ? ['Company'] : []), 'Language', 'Status', 'Version', 'Calls', 'Minutes'], items.map(a => h`<tr class="click" data-href="#/agents/${a.id}"><td><b>${a.name}</b><div class="muted small">${label(a.industry)}</div></td>${isAdmin() ? h`<td>${a.company_name}</td>` : ''}
    <td>${state.meta.languages[a.language]}</td><td>${badge(a.status)}</td><td>v${a.current_version}${a.deployed_version ? h` <span class="muted small">(live v${a.deployed_version})</span>` : ''}</td><td>${a.total_calls}</td><td>${a.total_minutes}</td></tr>`))}`;
};
actions['new-agent'] = () => modal('New agent', h`<form data-form="agent">${field('name', 'Agent name')}<div class="fgrid"><div class="field"><label>Company</label><select name="company_id">${options(window._companies.map(c => [c.id, c.name]))}</select></div>
  <div class="field"><label>Industry</label><select name="industry">${options(state.meta.industries)}</select></div><div class="field"><label>Language</label><select name="language" data-lang>${options(Object.entries(state.meta.languages))}</select></div>
  <div class="field"><label>Voice</label><select name="voice">${options(state.meta.voices.en)}</select></div></div><button class="btn primary">Create agent</button></form>`);
forms.agent = async d => { const a = await api('/agents', { method: 'POST', data: d }); closeModal(); toast('Agent created'); location.hash = '#/agents/' + a.id; };

const provSel = (kind, val) => options(state.meta.providers.filter(p => p.kind === kind).map(p => [p.name, p.name + (p.implemented ? ' (simulated)' : ' (stub – not implemented)')]), val);
views['agents/detail'] = async (p, id) => {
  const a = await api('/agents/' + id), tab = p.get('tab') || 'overview';
  const tabs = isAdmin() ? ['overview', 'config', 'knowledge', 'versions', 'test'] : ['overview'];
  const adminBtns = {
    testing: h`<button class="btn primary" data-act="wf" data-do="request-approval" data-id="${a.id}">Request client approval</button>`,
    rejected: h`<button class="btn primary" data-act="wf" data-do="request-approval" data-id="${a.id}">Re-request approval</button>`,
    approved: h`<button class="btn primary" data-act="wf" data-do="deploy" data-id="${a.id}">Deploy agent</button>`,
  };
  const approveBtns = a.status === 'pending_approval' ? h`<button class="btn primary" data-act="wf" data-do="approve" data-id="${a.id}">Approve</button><button class="btn danger" data-act="wf" data-do="reject" data-id="${a.id}">Request changes</button>` : '';
  let bodyHtml = '';
  if (tab === 'overview') {
    const calls = await api(`/calls?agent_id=${id}&limit=8`);
    bodyHtml = h`<div class="grid g22"><div class="card"><h2>Details</h2><div class="mt">${[['Company', a.company_name], ['Industry', label(a.industry)], ['Language', state.meta.languages[a.language]], ['Phone number', a.phone_number || '—'], ['Version', 'v' + a.current_version], ['Live version', a.deployed_version ? 'v' + a.deployed_version : 'not deployed']].map(([k, v]) => h`<div class="row spread mb"><span class="muted">${k}</span><b>${v}</b></div>`)}</div></div>
      <div class="card"><h2>Approval history</h2><div class="mt">${a.approvals.length ? a.approvals.map(x => h`<div class="mb">${badge(x.decision)} <b>v${x.version}</b> by ${x.by_name || '—'} <span class="muted small">${dt(x.created_at)}</span>${x.comment ? h`<div class="muted small">“${x.comment}”</div>` : ''}</div>`) : h`<div class="muted">No decisions yet</div>`}</div></div></div>
      <h2 class="mt mb">Recent calls</h2>${callsTable(calls.items)}`;
  } else if (tab === 'config') {
    bodyHtml = h`<div class="card"><form data-form="agent-config" data-id="${a.id}"><div class="fgrid">${field('name', 'Name', a.name)}<div class="field"><label>Industry</label><select name="industry">${options(state.meta.industries, a.industry)}</select></div>
      <div class="field"><label>Language</label><select name="language" data-lang>${options(Object.entries(state.meta.languages), a.language)}</select></div><div class="field"><label>Voice</label><select name="voice">${options(state.meta.voices[a.language], a.voice)}</select></div>
      ${field('phone_number', 'Agent phone number (DID)', a.phone_number)}${field('handover_number', 'Human handover number / SIP target', a.handover_number)}</div>
      <div class="field"><label>Greeting (blank = language default)</label><input name="greeting" value="${a.greeting}"></div><div class="field"><label>System prompt</label><textarea name="prompt" rows="5">${a.prompt}</textarea></div>
      <div class="fgrid"><div class="field"><label>STT provider</label><select name="stt_provider">${provSel('stt', a.stt_provider)}</select></div><div class="field"><label>LLM provider</label><select name="llm_provider">${provSel('llm', a.llm_provider)}</select></div>
      <div class="field"><label>TTS provider</label><select name="tts_provider">${provSel('tts', a.tts_provider)}</select></div><div class="field"><label>Telephony provider</label><select name="telephony_provider">${provSel('telephony', a.telephony_provider)}</select></div></div>
      <p class="muted small">Saving creates a new version. Editing a deployed agent takes it out of “deployed” until it is tested, approved and redeployed (or rolled back).</p><button class="btn primary">Save as new version</button></form></div>`;
  } else if (tab === 'knowledge') {
    const kb = await api(`/agents/${id}/knowledge`);
    bodyHtml = h`<div class="grid g22"><div class="card"><h2>Add knowledge</h2><form class="mt" data-form="kb" data-id="${a.id}">${field('title', 'Title')}<div class="field"><label>Content</label><textarea name="content"></textarea></div><button class="btn primary">Add</button></form>
      <p class="muted small mt">Mock retrieval uses keyword overlap, not embeddings.</p></div><div class="card"><h2>Documents (${kb.items.length})</h2><div class="mt">${kb.items.map(k => h`<div class="mb"><div class="row spread"><b>${k.title}</b><button class="btn sm danger" data-act="kb-del" data-id="${k.id}">Delete</button></div><div class="muted small">${k.content.slice(0, 200)}</div></div>`)}</div></div></div>`;
  } else if (tab === 'versions') {
    const v = await api(`/agents/${id}/versions`);
    bodyHtml = table(['Version', 'Change', 'By', 'When', ''], v.items.map(x => h`<tr><td><b>v${x.version}</b></td><td>${x.note}</td><td>${x.by_name || '—'}</td><td>${dt(x.created_at)}</td><td class="right">${x.version !== a.current_version ? h`<button class="btn sm" data-act="rollback" data-id="${a.id}" data-version="${x.version}">Roll back to this</button>` : h`<span class="badge b-info">Current</span>`}</td></tr>`));
  } else if (tab === 'test') {
    bodyHtml = h`<div class="card"><h2>Run a simulated test call</h2><p class="muted small">Uses mock STT/LLM/TTS/telephony. Pick a failure scenario to test fallbacks.</p>
      <form class="mt" data-form="test-call" data-id="${a.id}"><div class="fgrid"><div class="field"><label>Scenario</label><select name="scenario">${options(state.meta.scenarios)}</select></div><div class="field"><label>Direction</label><select name="direction">${options(['inbound', 'outbound'])}</select></div></div>
      <div class="field"><label>Caller lines (one per line; blank = default script in the agent's language)</label><textarea name="lines" placeholder="Hello&#10;What is the price?&#10;Thank you"></textarea></div><button class="btn primary">Run test call</button></form></div>`;
  }
  return h`${pageHead(a.name, h`${a.company_name} · ${badge(a.status)} · v${a.current_version}`, h`${isAdmin() ? (adminBtns[a.status] || '') : ''}${approveBtns}`)}
  ${a.status === 'pending_approval' && !isAdmin() ? h`<div class="banner">This agent is waiting for your approval. Review the recent calls, then approve or request changes.</div>` : ''}
  <div class="tabs">${tabs.map(t => h`<a href="#/agents/${a.id}?tab=${t}" class="${t === tab ? 'active' : ''}">${label(t)}</a>`)}</div>${bodyHtml}`;
};
actions.wf = async el => {
  const what = el.dataset.do; let data = {};
  if (what === 'reject') { const c = prompt('What should change? (visible to the Voxora team)'); if (c === null) return; data = { comment: c }; }
  if (what === 'approve') { const c = prompt('Optional comment:'); if (c === null) return; data = { comment: c }; }
  await api(`/agents/${el.dataset.id}/${what}`, { method: 'POST', data }); toast('Done'); route();
};
actions.rollback = async el => { if (confirm('Roll back to version ' + el.dataset.version + '? This redeploys that configuration immediately.')) { await api(`/agents/${el.dataset.id}/rollback`, { method: 'POST', data: { version: +el.dataset.version } }); toast('Rolled back'); location.hash = '#/agents/' + el.dataset.id; } };
actions['kb-del'] = async el => { await api('/knowledge/' + el.dataset.id, { method: 'DELETE' }); route(); };
forms['agent-config'] = async (d, f) => { await api('/agents/' + f.dataset.id, { method: 'PATCH', data: d }); toast('Saved as new version'); location.hash = '#/agents/' + f.dataset.id; };
forms.kb = async (d, f) => { await api(`/agents/${f.dataset.id}/knowledge`, { method: 'POST', data: d }); toast('Added'); route(); };
forms['test-call'] = async (d, f) => {
  const lines = (d.lines || '').split('\n').map(s => s.trim()).filter(Boolean);
  const call = await api(`/agents/${f.dataset.id}/test-call`, { method: 'POST', data: { scenario: d.scenario, direction: d.direction, utterances: lines.length ? lines : undefined } });
  toast('Test call ' + label(call.status)); location.hash = '#/calls/' + call.id;
};

/* ---------------- calls */
const callsTable = items => table(['When', 'Agent', 'Direction', 'Number', 'Status', 'Duration', 'Sentiment'], items.map(c => h`<tr class="click" data-href="#/calls/${c.id}"><td class="nowrap">${dt(c.started_at)}${c.is_test ? h` <span class="badge b-info">test</span>` : ''}</td><td>${c.agent_name || '#' + c.agent_id}</td><td>${label(c.direction)}</td>
  <td class="nowrap">${c.direction === 'inbound' ? c.from_number : c.to_number}</td><td>${badge(c.status)}</td><td>${dur(c.duration_sec)}</td><td>${badge(c.sentiment)}</td></tr>`), 'No calls found');
views.calls = async p => {
  const qs = new URLSearchParams(); ['status', 'direction', 'q', 'agent_id'].forEach(k => p.get(k) && qs.set(k, p.get(k))); qs.set('limit', 100);
  const [{ items, total }, ag] = await Promise.all([api('/calls?' + qs), api('/agents')]);
  return h`${pageHead('Calls', `${total} calls · transcripts, summaries and recordings`, isAdmin() ? h`<button class="btn" data-act="sim-call" data-mode="start">Start live call</button><button class="btn primary" data-act="sim-call" data-mode="simulate">Simulate call</button>` : '')}
  <div class="filters"><input data-nav="q" placeholder="Search number or summary" value="${p.get('q') || ''}"><select data-nav="status">${options([['', 'Any status'], 'completed', 'transferred', 'failed', 'no_answer', 'busy', 'in_progress'], p.get('status'))}</select>
  <select data-nav="direction">${options([['', 'Any direction'], 'inbound', 'outbound'], p.get('direction'))}</select><select data-nav="agent_id">${options([['', 'All agents'], ...ag.items.map(a => [a.id, a.name])], p.get('agent_id'))}</select></div>${callsTable(items)}`;
};
actions['sim-call'] = async el => {
  const ag = (await api('/agents')).items; window._simAgents = ag;
  modal(el.dataset.mode === 'start' ? 'Start live call (step by step)' : 'Simulate a full call', h`<form data-form="sim-call" data-mode="${el.dataset.mode}"><div class="field"><label>Agent</label><select name="agent_id">${options(ag.map(a => [a.id, `${a.name} — ${label(a.status)}`]))}</select></div>
    <div class="fgrid"><div class="field"><label>Scenario</label><select name="scenario">${options(state.meta.scenarios)}</select></div><div class="field"><label>Direction</label><select name="direction">${options(['inbound', 'outbound'])}</select></div></div>
    <div class="field check"><input type="checkbox" name="is_test" id="ist"><label for="ist" style="margin:0">Mark as test call (required if the agent is not deployed; test calls are not billed)</label></div><button class="btn primary">Go</button></form>`);
};
forms['sim-call'] = async (d, f) => {
  const call = await api(f.dataset.mode === 'start' ? '/calls/start' : '/calls/simulate', { method: 'POST', data: { agent_id: +d.agent_id, scenario: d.scenario, direction: d.direction, is_test: !!d.is_test } });
  closeModal(); location.hash = '#/calls/' + call.id;
};
views['calls/detail'] = async (p, id) => {
  const c = await api('/calls/' + id);
  const live = c.status === 'in_progress';
  return h`${pageHead('Call #' + c.id, h`${c.agent_name} · ${label(c.direction)} · ${dt(c.started_at)} ${live ? h`<span class="pulse"></span>LIVE` : ''}`, h`${badge(c.status)}${c.is_test ? h`<span class="badge b-info">test</span>` : ''}`)}
  <div class="grid g2"><div class="card"><h2>Transcript</h2><div class="chat mt">${c.turns.map(t => h`<div class="bubble ${t.speaker}"><div>${t.text}</div><div class="meta">${t.speaker === 'agent' ? 'Agent' : 'Caller'}${t.intent ? ' · ' + t.intent : ''}${t.latency_ms ? ' · ' + t.latency_ms + ' ms' : ''}</div></div>`)}</div>
    ${live && isAdmin() ? h`<form class="row mt" data-form="step" data-id="${c.id}"><input name="text" class="grow" placeholder="Type what the caller says…" autocomplete="off"><button class="btn primary">Send</button><button type="button" class="btn danger" data-act="end-call" data-id="${c.id}">End call</button></form>` : ''}</div>
  <div><div class="card mb"><h2>Summary</h2><p>${c.summary || (live ? 'In progress…' : '—')}</p><div class="row">${badge(c.sentiment)}${c.handover ? h`<span class="badge b-warn">Handover → ${c.handover_target}</span>` : ''}</div></div>
    <div class="card mb"><h2>Details</h2><div class="mt">${[['Duration', dur(c.duration_sec)], ['Billable minutes', c.billable_minutes], ['From', c.from_number], ['To', c.to_number], ['Language', state.meta.languages[c.language]], ['Agent version', 'v' + c.agent_version], ...(isAdmin() ? [['Scenario', c.scenario], ['Provider errors', c.errors], ['Provider SID', c.provider_sid]] : [])].map(([k, v]) => h`<div class="row spread mb"><span class="muted">${k}</span><b>${v}</b></div>`)}</div></div>
    ${c.recording_file ? h`<div class="card"><h2>Recording</h2><p class="muted small">Simulated recording (placeholder tones, not speech).</p><button class="btn" data-act="load-rec" data-id="${c.id}">▶ Load recording</button><div id="rec" class="mt"></div></div>` : ''}</div></div>`;
};
actions['load-rec'] = async el => { const b = await api(`/calls/${el.dataset.id}/recording`, { blob: true }); const a = document.createElement('audio'); a.controls = true; a.src = URL.createObjectURL(b); a.style.width = '100%'; $('#rec').replaceChildren(a); a.play().catch(() => { }); };
forms.step = async (d, f) => { await api(`/calls/${f.dataset.id}/step`, { method: 'POST', data: { text: d.text } }); route(); };
actions['end-call'] = async el => { await api(`/calls/${el.dataset.id}/end`, { method: 'POST' }); route(); };

views.live = async () => {
  const { items } = await api('/calls/live');
  state.timer = setInterval(route, 5000);
  return h`${pageHead('Live monitor', h`<span class="pulse"></span>${items.length} active call(s) · refreshes every 5 s`, isAdmin() ? h`<button class="btn primary" data-act="sim-call" data-mode="start">Start live call</button>` : '')}
  ${table(['Started', 'Agent', ...(isAdmin() ? ['Company'] : []), 'Direction', 'Number', 'Turns'], items.map(c => h`<tr class="click" data-href="#/calls/${c.id}"><td>${dt(c.started_at)}</td><td>${c.agent_name}</td>${isAdmin() ? h`<td>${c.company_name}</td>` : ''}<td>${label(c.direction)}</td><td>${c.from_number}</td><td>${c.turns}</td></tr>`), 'No calls in progress right now')}`;
};

/* ---------------- billing */
views.billing = async p => {
  const co = isAdmin() ? p.get('company_id') || '' : '';
  const cos = isAdmin() ? (await api('/companies')).items : [];
  const inv = await api('/billing/invoices' + (co ? '?company_id=' + co : ''));
  const target = isAdmin() ? co : state.user.company_id;
  const u = target ? await api('/billing/usage?company_id=' + target) : null;
  const pct = u ? Math.min(100, Math.round(100 * u.minutes_used / u.plan.included_minutes)) : 0;
  return h`${pageHead('Billing & usage', 'Monthly subscription + per-minute overage (INR). Test calls are never billed.', isAdmin() ? h`<select data-nav="company_id">${options([['', 'All companies'], ...cos.map(c => [c.id, c.name])], co)}</select><button class="btn primary" data-act="gen-invoices">Generate this month</button>` : '')}
  ${u ? h`<div class="card mb"><div class="row spread"><h2>${u.period} usage · ${u.plan.name} plan</h2><b>${inr(u.estimated_total)} <span class="muted small">estimated</span></b></div><div class="hbar mt"><i style="width:${pct}%"></i></div>
    <div class="row spread small muted mt"><span>${u.minutes_used} of ${u.plan.included_minutes} included minutes (${u.calls} calls)</span><span>Overage ${u.overage_minutes} min × ${inr(u.plan.per_minute_rate)}</span></div></div>` : ''}
  ${table(['Period', ...(isAdmin() ? ['Company'] : []), 'Plan', 'Minutes', 'Overage', 'Total', 'Status', ''], inv.items.map(i => h`<tr><td><b>${i.period}</b></td>${isAdmin() ? h`<td>${i.company_name}</td>` : ''}<td>${label(i.plan)}</td><td>${i.minutes_used}/${i.included_minutes}</td><td>${inr(i.usage_amount)}</td><td><b>${inr(i.total)}</b></td><td>${badge(i.status)}</td>
    <td class="right nowrap">${isAdmin() && i.status === 'draft' ? h`<button class="btn sm" data-act="inv" data-id="${i.id}" data-st="issued">Issue</button>` : ''}${isAdmin() && i.status === 'issued' ? h`<button class="btn sm" data-act="inv" data-id="${i.id}" data-st="paid">Mark paid</button>` : ''}</td></tr>`), 'No invoices yet')}`;
};
actions['gen-invoices'] = async () => { const r = await api('/billing/generate', { method: 'POST', data: {} }); toast(`Generated ${r.generated} invoice(s) for ${r.period}`); route(); };
actions.inv = async el => { await api(`/billing/invoices/${el.dataset.id}/status`, { method: 'POST', data: { status: el.dataset.st } }); route(); };

/* ---------------- providers / audit / support / notifications / settings */
views.providers = async () => h`${pageHead('Providers', 'Replaceable adapters. Everything marked “simulated” is a mock; “stub” means a real adapter that is NOT implemented yet.')}
  <div class="banner">No real AI, speech or telephone service is connected. See MANUAL_SETUP_AND_NEXT_STEPS.md to add real providers.</div>
  ${table(['Type', 'Name', 'Mode', 'Notes'], state.meta.providers.map(p => h`<tr><td>${p.kind.toUpperCase()}</td><td><b>${p.name}</b></td><td>${p.simulated ? h`<span class="badge b-info">Simulated</span>` : h`<span class="badge b-warn">Stub – not implemented</span>`}</td><td class="muted">${p.note}</td></tr>`))}`;
views.audit = async () => { const { items } = await api('/audit?limit=200'); return h`${pageHead('Audit log', 'Security-relevant actions across the platform')}${table(['When', 'User', 'Company', 'Action', 'Detail'], items.map(a => h`<tr><td class="nowrap">${dt(a.created_at)}</td><td>${a.user_email || '—'}</td><td>${a.company_name || '—'}</td><td><span class="badge b-mute">${a.action}</span></td><td class="muted">${a.detail}</td></tr>`))}`; };
views.support = async () => {
  const { items } = await api('/tickets');
  return h`${pageHead('Support', isAdmin() ? 'Tickets from clients' : 'Contact the Voxora team', isAdmin() ? '' : h`<button class="btn primary" data-act="new-ticket">+ New ticket</button>`)}
  ${items.length ? items.map(t => h`<div class="card mb"><div class="row spread"><h3>${t.subject}</h3>${badge(t.status)}</div><div class="muted small">${t.company_name} · ${t.user_name} · ${dt(t.created_at)}</div><p>${t.body}</p>${t.response ? h`<div class="banner" style="background:var(--ok-soft);color:var(--ok)">Reply: ${t.response}</div>` : ''}
    ${isAdmin() ? h`<form class="row" data-form="ticket-reply" data-id="${t.id}"><input name="response" class="grow" placeholder="Reply…" value="${t.response}"><select name="status" style="width:auto">${options(['open', 'in_progress', 'resolved'], t.status)}</select><button class="btn">Save</button></form>` : ''}</div>`) : h`<div class="card empty">No tickets</div>`}`;
};
actions['new-ticket'] = () => modal('New support ticket', h`<form data-form="ticket">${field('subject', 'Subject')}<div class="field"><label>Message</label><textarea name="body"></textarea></div><button class="btn primary">Send</button></form>`);
forms.ticket = async d => { await api('/tickets', { method: 'POST', data: d }); closeModal(); toast('Ticket sent'); route(); };
forms['ticket-reply'] = async (d, f) => { await api('/tickets/' + f.dataset.id, { method: 'PATCH', data: d }); toast('Ticket updated'); route(); };
views.notifications = async () => {
  const { items } = await api('/notifications'); await api('/notifications/read', { method: 'POST' }); state.unread = 0; updateBell();
  return h`${pageHead('Notifications', 'Approvals, deployments, invoices and tickets')}${items.length ? items.map(n => h`<div class="card mb ${n.is_read ? '' : 'fade'}"><div class="row spread"><b>${n.title}</b><span class="muted small">${dt(n.created_at)}</span></div><div class="muted">${n.body}</div></div>`) : h`<div class="card empty">You're all caught up</div>`}`;
};
views.settings = async () => h`${pageHead('Settings', state.user.email)}<div class="grid g22"><div class="card"><h2>Change password</h2><form class="mt" data-form="password">${field('current', 'Current password', '', 'password', 'autocomplete="current-password"')}${field('new', 'New password (min 8)', '', 'password', 'autocomplete="new-password"')}<button class="btn primary">Update password</button></form></div>
  <div class="card"><h2>Appearance</h2><p class="muted">Light or dark theme.</p><button class="btn" data-act="theme">Toggle theme</button></div></div>`;
forms.password = async (d, f) => { await api('/auth/change-password', { method: 'POST', data: d }); f.reset(); toast('Password updated'); };
actions.theme = () => { const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = t; localStorage.setItem('vx_theme', t); };
