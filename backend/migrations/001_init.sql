CREATE TABLE plans (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, monthly_fee REAL NOT NULL,
  included_minutes INTEGER NOT NULL, per_minute_rate REAL NOT NULL
);
INSERT INTO plans VALUES
 ('starter','Starter',4999,500,6.0),
 ('growth','Growth',14999,2500,4.5),
 ('enterprise','Enterprise',49999,12000,3.0);

CREATE TABLE companies (
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
  industry TEXT NOT NULL DEFAULT 'other', plan TEXT NOT NULL DEFAULT 'starter' REFERENCES plans(code),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended')),
  contact_email TEXT, created_at TEXT NOT NULL
);
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER REFERENCES companies(id),
  name TEXT NOT NULL, email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('super_admin','client')),
  active INTEGER NOT NULL DEFAULT 1, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until TEXT,
  created_at TEXT NOT NULL,
  CHECK ((role='client' AND company_id IS NOT NULL) OR role='super_admin')
);
CREATE TABLE agents (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id),
  name TEXT NOT NULL, industry TEXT NOT NULL DEFAULT 'other', language TEXT NOT NULL DEFAULT 'en',
  voice TEXT NOT NULL DEFAULT 'en-female-1', greeting TEXT NOT NULL DEFAULT '', prompt TEXT NOT NULL DEFAULT '',
  stt_provider TEXT NOT NULL DEFAULT 'mock-stt', llm_provider TEXT NOT NULL DEFAULT 'mock-llm',
  tts_provider TEXT NOT NULL DEFAULT 'mock-tts', telephony_provider TEXT NOT NULL DEFAULT 'mock-telephony',
  phone_number TEXT NOT NULL DEFAULT '', handover_number TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','testing','pending_approval','approved','rejected','deployed')),
  current_version INTEGER NOT NULL DEFAULT 1, deployed_version INTEGER,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE agent_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, snapshot TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(agent_id, version)
);
CREATE TABLE knowledge_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE approvals (
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  version INTEGER NOT NULL, decision TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
  decided_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL
);
CREATE TABLE calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id),
  agent_id INTEGER NOT NULL REFERENCES agents(id), agent_version INTEGER NOT NULL DEFAULT 1,
  direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound')),
  from_number TEXT NOT NULL, to_number TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'en',
  status TEXT NOT NULL CHECK (status IN ('in_progress','completed','transferred','failed','no_answer','busy')),
  scenario TEXT NOT NULL DEFAULT 'normal', is_test INTEGER NOT NULL DEFAULT 0,
  provider_sid TEXT, started_at TEXT NOT NULL, ended_at TEXT, duration_sec INTEGER NOT NULL DEFAULT 0,
  billable_minutes INTEGER NOT NULL DEFAULT 0, summary TEXT NOT NULL DEFAULT '', sentiment TEXT NOT NULL DEFAULT 'neutral',
  handover INTEGER NOT NULL DEFAULT 0, handover_target TEXT, errors INTEGER NOT NULL DEFAULT 0,
  recording_file TEXT
);
CREATE INDEX idx_calls_company_started ON calls(company_id, started_at);
CREATE TABLE call_turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT, call_id INTEGER NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL, speaker TEXT NOT NULL CHECK (speaker IN ('agent','caller','system')),
  text TEXT NOT NULL, intent TEXT, confidence REAL, latency_ms INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0, ts TEXT NOT NULL
);
CREATE TABLE invoices (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id),
  period TEXT NOT NULL, plan TEXT NOT NULL, subscription_fee REAL NOT NULL, included_minutes INTEGER NOT NULL,
  minutes_used INTEGER NOT NULL, overage_minutes INTEGER NOT NULL, per_minute_rate REAL NOT NULL,
  usage_amount REAL NOT NULL, total REAL NOT NULL, status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','issued','paid')),
  created_at TEXT NOT NULL, UNIQUE(company_id, period)
);
CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL, body TEXT NOT NULL DEFAULT '', is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT, company_id INTEGER NOT NULL REFERENCES companies(id),
  user_id INTEGER NOT NULL REFERENCES users(id), subject TEXT NOT NULL, body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','in_progress','resolved')),
  response TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, company_id INTEGER, action TEXT NOT NULL,
  entity TEXT NOT NULL DEFAULT '', entity_id INTEGER, detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
