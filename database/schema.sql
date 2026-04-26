CREATE TABLE IF NOT EXISTS players (
    player_id       TEXT PRIMARY KEY,
    display_name    TEXT NOT NULL,
    position        TEXT NOT NULL,  -- QB, RB, WR, TE
    team            TEXT,
    apy             REAL,           -- avg per year salary (millions)
    apy_cap_pct     REAL,
    guaranteed      REAL,
    year_signed     INTEGER,
    draft_year      INTEGER
);

CREATE TABLE IF NOT EXISTS stats (
    player_id               TEXT NOT NULL,
    season                  INTEGER NOT NULL,
    games_played            INTEGER,
    -- Passing
    completions             REAL, attempts REAL,
    passing_yards           REAL, passing_tds REAL, passing_interceptions REAL,
    passing_epa             REAL, passing_cpoe REAL,
    -- Rushing
    carries                 REAL, rushing_yards REAL, rushing_tds REAL,
    rushing_epa             REAL, yards_per_carry REAL,
    -- Receiving
    receptions              REAL, targets REAL, receiving_yards REAL,
    receiving_tds           REAL, receiving_epa REAL,
    target_share            REAL, wopr REAL,
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE IF NOT EXISTS scores (
    player_id           TEXT NOT NULL,
    season              INTEGER NOT NULL,
    performance_score   REAL,
    perf_norm           REAL,       -- 0-100 within position+season
    expected_perf       REAL,       -- regression predicted perf for their salary
    value_per_million   REAL,       -- residual: actual - expected
    value_score_norm    REAL,       -- 0-100 final value score
    contract_tier       TEXT,       -- 'Elite Value', 'Fair Value', 'Overpaid'
    contract_type       TEXT,       -- 'Rookie Contract', 'Non-Rookie Contract'
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE INDEX IF NOT EXISTS idx_players_name     ON players(display_name);
CREATE INDEX IF NOT EXISTS idx_players_position ON players(position);
