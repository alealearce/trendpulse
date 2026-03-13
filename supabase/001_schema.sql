-- ─────────────────────────────────────────────────────────────────────────────
-- TrendPulse — Supabase Schema
-- Run this in your Supabase project: SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────


-- ── 1. Daily trend snapshots ──────────────────────────────────────────────────
create table if not exists tiktok_trends (
  id                      uuid primary key default gen_random_uuid(),
  date                    date not null,
  rank                    int  not null,

  -- Trend identity
  trend_name              text not null,
  trend_type              text not null default 'hashtag'
                            check (trend_type in
                              ('hashtag','sound','dance','challenge','food','product')),
  category                text not null default 'general',
  category_display        text,

  -- Scoring
  early_score             numeric(5,1) not null default 0,
  score_label             text,
  type_emoji              text,

  -- Signal metadata
  source                  text not null,         -- primary source
  cross_platform          boolean default false,
  cross_platform_sources  text[],
  velocity_24h            numeric,               -- % growth (when available)
  total_uses              bigint default 0,       -- TikTok use count

  -- Display
  example_url             text,
  why_its_early           text,                  -- AI-generated blurb (Day 3)

  created_at              timestamptz default now()
);

-- Fast lookups for the daily email builder
create index if not exists tiktok_trends_date_score_idx
  on tiktok_trends (date, early_score desc);

create index if not exists tiktok_trends_date_type_idx
  on tiktok_trends (date, trend_type);


-- ── 2. Subscribers ────────────────────────────────────────────────────────────
create table if not exists trend_subscribers (
  id                      uuid primary key default gen_random_uuid(),
  email                   text not null unique,

  -- Subscription
  tier                    text not null default 'free'
                            check (tier in ('free', 'pro')),
  niche_filter            text,   -- null = all | 'food' | 'beauty' | 'fashion'
                                  --         | 'fitness' | 'home' | 'product'

  -- Stripe (populated when Pro)
  stripe_customer_id      text,
  stripe_subscription_id  text,

  -- Timestamps
  subscribed_at           timestamptz default now(),
  unsubscribed_at         timestamptz,             -- null = still active
  last_email_sent_at      timestamptz
);

create index if not exists trend_subscribers_email_idx
  on trend_subscribers (email);

create index if not exists trend_subscribers_active_idx
  on trend_subscribers (tier)
  where unsubscribed_at is null;


-- ── 3. Trend send log (deduplication) ────────────────────────────────────────
-- Every trend sent to every subscriber is recorded here.
-- Before building a digest, we exclude any trend_name sent in the last 14 days.
create table if not exists trend_sends (
  id              uuid primary key default gen_random_uuid(),
  subscriber_id   uuid references trend_subscribers(id) on delete cascade,
  trend_id        uuid references tiktok_trends(id) on delete cascade,
  trend_name      text not null,     -- denormalized for fast set lookups
  digest_date     date not null,
  sent_at         timestamptz default now()
);

-- Used by get_trends_sent_last_n_days()
create index if not exists trend_sends_name_sent_idx
  on trend_sends (trend_name, sent_at);

create index if not exists trend_sends_subscriber_sent_idx
  on trend_sends (subscriber_id, sent_at);


-- ── 4. Daily digest log (monitoring) ─────────────────────────────────────────
create table if not exists daily_digests (
  id              uuid primary key default gen_random_uuid(),
  digest_date     date not null unique,
  total_trends    int default 0,
  free_sends      int default 0,
  pro_sends       int default 0,
  completed_at    timestamptz default now()
);


-- ── Row Level Security ────────────────────────────────────────────────────────
-- Trends are public (read-only) — powers the landing page preview
alter table tiktok_trends       enable row level security;
alter table trend_subscribers   enable row level security;
alter table trend_sends         enable row level security;
alter table daily_digests       enable row level security;

-- Public can read today's top trends (landing page teaser)
create policy "trends_public_read"
  on tiktok_trends for select using (true);

-- All other tables: server-side (service role) only
create policy "subscribers_service_only"
  on trend_subscribers using (false);

create policy "sends_service_only"
  on trend_sends using (false);

create policy "digests_service_only"
  on daily_digests using (false);
