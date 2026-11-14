-- The research lab's tables (spec Part 4.1), minimal and SQLite.
--
-- WHY SQLITE AND NOT POSTGRESQL (2026-10-17): every database on this site is
-- SQLite, the engine is standard library only, and the droplet has one core.
-- Postgres would add a server process and a dependency for a few thousand
-- registry rows. These tables use only types and constraints that move to
-- Postgres unchanged, so the switch stays a mechanical one if the lab outgrows
-- this. Ethan's call (docs/RESEARCH_LAB.md, "Decisions for Ethan").
--
-- The spec's other tables already exist under other names; see
-- docs/RESEARCH_LAB.md "Where each spec table lives":
--   odds_snapshots    -> history.db odds_history + cache/line_history.jsonl
--   outcomes          -> history.db player_game_logs, games
--   model predictions -> ledger.db forecast_log (hash-chained, sealed pre-game)
--   bet evaluations   -> ledger.db bets (+ bets_audit for every correction)
--
-- The source of truth for the rows below is research/registry.json and
-- research/sources.json (reviewed in git); research/registry.py loads them.

CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    dataset_name TEXT NOT NULL,
    source_url TEXT,
    access TEXT,
    sports TEXT,
    coverage TEXT,
    update_frequency TEXT,
    identifiers TEXT,
    known_missing TEXT,
    quality TEXT,
    license_reference TEXT,
    audited_at TEXT NOT NULL,
    audit_status TEXT NOT NULL CHECK (audit_status IN ('VERIFIED', 'PARTIALLY VERIFIED', 'UNVERIFIED', 'UNAVAILABLE'))
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sport TEXT NOT NULL,
    market TEXT NOT NULL,
    hypothesis TEXT NOT NULL,
    equation TEXT,
    variables TEXT,
    mechanism TEXT,
    prior_art TEXT,
    novelty_class TEXT NOT NULL CHECK (novelty_class IN ('1', '2', '3', '4', '5', '6')),
    data_sources TEXT,
    data_version TEXT,
    code_version TEXT,
    baseline TEXT,
    validation_protocol TEXT,
    primary_metric TEXT,
    sample_size TEXT,
    multiple_testing TEXT,
    failure_modes TEXT,
    next_experiment TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_results (
    result_id INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL REFERENCES experiments (experiment_id),
    evaluation_period TEXT NOT NULL,
    subject TEXT,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    uncertainty_lower REAL,
    uncertainty_upper REAL,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS experiment_results_exp ON experiment_results (experiment_id);

CREATE TABLE IF NOT EXISTS experiment_decisions (
    experiment_id TEXT NOT NULL REFERENCES experiments (experiment_id),
    subject TEXT NOT NULL,
    decision TEXT NOT NULL,
    PRIMARY KEY (experiment_id, subject)
);
