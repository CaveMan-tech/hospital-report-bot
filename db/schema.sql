-- Hospital Pattern Bot: Postgres schema.
-- Applied automatically at startup (every statement is idempotent), so there is no
-- manual migration step. On Railway the database is reachable only over the private
-- network from the app service; nothing talks to it from a browser.

create table if not exists reports (
  id                   uuid primary key,
  ref_code_hmac        text not null unique,      -- HMAC-SHA256(server secret, code). The code is never stored.
  created_at           timestamptz not null default now(),
  channel              text not null check (channel in ('web','whatsapp','telegram')),
  pack                 text not null default 'ng-lagos',
  language             text not null default 'en',
  hospital_id          text,                       -- id from the pack's hospital list; null if unmatched
  hospital_name_raw    text,                       -- kept only when no hospital matched, for human review
  department           text not null default 'unknown',
  category             text not null
                       check (category in ('emergency_refused','detention','abuse','neglect','other')),
  secondary_categories text[] not null default '{}',
  severity             text not null check (severity in ('severe','not_severe')),
  incident_timing      text not null default 'unknown',
  is_ongoing           boolean,
  reporter_role        text not null default 'unknown',
  patient_group        text not null default 'unknown',
  subtype              text not null default 'other',
  harm_outcome         text not null default 'unknown',
  time_bucket          text not null default 'unknown',
  money_demanded       boolean,
  amount_bucket        text not null default 'unknown',
  extra                jsonb not null default '{}',  -- future facets without a migration
  extraction_version   text not null,               -- prompt + schema version, enables re-processing
  summary_redacted     text not null default '',
  rights_shown         text[] not null default '{}',
  escalation_shown     boolean not null default false,
  followup_opt_in      boolean not null default false,
  followup_due_at      timestamptz,
  status               text not null default 'new'
                       check (status in ('new','resolved','unchanged','worse','left','no_response')),
  credibility          text not null default 'ok'
                       check (credibility in ('ok','review','excluded')),
  dedupe_key           text,                        -- HMAC(daily rotating salt, ip); unlinkable after 24h
  is_sample            boolean not null default false
);
create index if not exists reports_pattern_idx on reports (hospital_id, category, created_at);
create index if not exists reports_dedupe_idx  on reports (dedupe_key, created_at);

create table if not exists followups (
  id         uuid primary key,
  report_id  uuid not null references reports(id) on delete cascade,
  created_at timestamptz not null default now(),
  status     text not null check (status in ('resolved','unchanged','worse','left'))
);

-- Short-lived conversation state. The raw story lives in `context` only while the
-- chat is active and is removed the moment the report row is written.
create table if not exists sessions (
  id         uuid primary key,
  channel    text not null,
  pack       text not null default 'ng-lagos',
  state      text not null default 'S1',
  context    jsonb not null default '{}',
  report_id  uuid references reports(id) on delete set null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index if not exists sessions_expiry_idx on sessions (expires_at);
