"""
Run once to populate the SQLite database.
Usage: python data/load_data.py
"""

import sqlite3
import os
import ssl
import pandas as pd
import nflreadpy as nfl
from scipy import stats as scipy_stats

ssl._create_default_https_context = ssl._create_unverified_context

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'sports_intelligence.db')
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), '..', 'database', 'schema.sql')

SKILL_POSITIONS = ['QB', 'RB', 'WR', 'TE']
SEASONS = [2023, 2024, 2025]

MIN_THRESHOLDS = {
    'QB': {'attempts': 100, 'apy': 5},
    'WR': {'targets': 20,   'apy': 1},
    'RB': {'carries': 20,   'apy': 1},
    'TE': {'targets': 15,   'apy': 1},
}

ROOKIE_APY_THRESHOLD = {'QB': 15, 'WR': 15, 'TE': 12, 'RB': 10}


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    print("Schema applied.")


# ── Load & Clean Stats ────────────────────────────────────────────────────────

def load_stats():
    print(f"Loading player stats from nflreadpy for seasons {SEASONS}...")
    raw = nfl.load_player_stats(seasons=SEASONS).to_pandas()
    raw = raw[
        (raw['position'].isin(SKILL_POSITIONS)) &
        (raw['season_type'] == 'REG')
    ]

    sum_cols = [
        'completions', 'attempts', 'passing_yards', 'passing_tds',
        'passing_interceptions', 'carries', 'rushing_yards', 'rushing_tds',
        'rushing_epa', 'receptions', 'targets', 'receiving_yards',
        'receiving_tds', 'receiving_epa', 'passing_epa',
    ]
    avg_cols = ['passing_cpoe', 'target_share', 'wopr']
    agg = {c: 'sum' for c in sum_cols}
    agg.update({c: 'mean' for c in avg_cols})
    agg['team'] = 'last'

    seasonal = raw.groupby(
        ['player_id', 'player_display_name', 'position', 'season']
    ).agg(agg).reset_index()

    games = raw.groupby(['player_id', 'season'])['game_id'].nunique().reset_index()
    games.columns = ['player_id', 'season', 'games_played']
    seasonal = seasonal.merge(games, on=['player_id', 'season'], how='left')

    seasonal['yards_per_carry'] = (
        seasonal['rushing_yards'] / seasonal['carries']
    ).replace([float('inf'), -float('inf')], 0).fillna(0)

    print(f"Stats loaded: {len(seasonal)} player-seasons")
    return seasonal


# ── Load & Clean Contracts ────────────────────────────────────────────────────

def load_contracts():
    print("Loading contracts from nflverse...")
    url = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.parquet"
    contracts = pd.read_parquet(url)
    contracts = contracts[contracts['position'].isin(SKILL_POSITIONS)]
    contracts = contracts.rename(columns={'gsis_id': 'player_id'})
    contracts = contracts[
        ['player_id', 'apy', 'apy_cap_pct', 'guaranteed',
         'year_signed', 'draft_year', 'is_active']
    ].copy()
    # Keep most recent contract per player
    contracts = contracts.sort_values('year_signed', ascending=False)
    contracts = contracts.drop_duplicates(subset='player_id', keep='first')
    print(f"Contracts loaded: {len(contracts)} players")
    return contracts


# ── Merge & Filter ────────────────────────────────────────────────────────────

def merge_and_filter(stats, contracts):
    df = stats.merge(contracts, on='player_id', how='inner')
    df = df[df['season'] >= df['year_signed']]

    filtered = []
    for pos, thresholds in MIN_THRESHOLDS.items():
        pos_df = df[df['position'] == pos].copy()
        for col, val in thresholds.items():
            pos_df = pos_df[pos_df[col] >= val]
        filtered.append(pos_df)

    df_filtered = pd.concat(filtered).reset_index(drop=True)
    print(f"After filtering: {len(df_filtered)} players")
    return df_filtered


# ── Scoring (mirrors models/scoring.py logic) ─────────────────────────────────

def calc_position_score(row):
    games = row['games_played'] if pd.notna(row['games_played']) else 1
    weight = min(games / 17, 1.0)
    pos = row['position']
    if pos == 'QB':
        score = row['passing_epa'] + (row['passing_cpoe'] * 10 if pd.notna(row['passing_cpoe']) else 0)
    elif pos == 'WR':
        score = row['receiving_epa'] + (row['wopr'] * 50)
    elif pos == 'RB':
        epa = row['rushing_epa'] + row['receiving_epa']
        ypc = (row['yards_per_carry'] - 4.0) * 10
        yards = row['rushing_yards'] / 10
        score = (epa * 0.3) + (ypc * 0.4) + (yards * 0.3)
    elif pos == 'TE':
        score = row['receiving_epa'] + (row['target_share'] * 100)
    else:
        score = 0
    return score * weight


def build_scores(df):
    df = df.copy()
    df['performance_score'] = df.apply(calc_position_score, axis=1)

    def normalize_perf(group):
        mn, mx = group['performance_score'].min(), group['performance_score'].max()
        group['perf_norm'] = 50.0 if mx == mn else (
            (group['performance_score'] - mn) / (mx - mn) * 100
        ).round(2)
        return group

    def calc_residuals(group):
        if len(group) < 3:
            group['expected_perf'] = group['perf_norm']
            group['value_per_million'] = 0.0
            return group
        slope, intercept, *_ = scipy_stats.linregress(group['apy'], group['perf_norm'])
        group['expected_perf'] = (intercept + slope * group['apy']).round(2)
        group['value_per_million'] = (group['perf_norm'] - group['expected_perf']).round(2)
        return group

    def normalize_value(group):
        mn, mx = group['value_per_million'].min(), group['value_per_million'].max()
        group['value_score_norm'] = 50.0 if mx == mn else (
            (group['value_per_million'] - mn) / (mx - mn) * 100
        ).round(1)
        return group

    def add_tiers(group):
        q75 = group['value_score_norm'].quantile(0.75)
        q25 = group['value_score_norm'].quantile(0.25)
        group['contract_tier'] = group['value_score_norm'].apply(
            lambda x: 'Elite Value' if x >= q75 else ('Fair Value' if x >= q25 else 'Overpaid')
        )
        return group

    def assign_contract_type(row):
        threshold = ROOKIE_APY_THRESHOLD.get(row['position'], 10)
        is_rookie = (
            pd.notna(row.get('draft_year')) and
            row['draft_year'] >= 2022 and
            row['apy'] < threshold
        )
        return 'Rookie Contract' if is_rookie else 'Non-Rookie Contract'

    df = df.groupby(['position', 'season'], group_keys=False).apply(normalize_perf).reset_index(drop=True)
    df = df.groupby(['position', 'season'], group_keys=False).apply(calc_residuals).reset_index(drop=True)
    df = df.groupby(['position', 'season'], group_keys=False).apply(normalize_value).reset_index(drop=True)
    df = df.groupby(['position', 'season'], group_keys=False).apply(add_tiers).reset_index(drop=True)
    df['contract_type'] = df.apply(assign_contract_type, axis=1)
    return df


# ── Write to DB ───────────────────────────────────────────────────────────────

def write_to_db(df, conn):
    player_rows = df[[
        'player_id', 'player_display_name', 'position', 'team',
        'apy', 'apy_cap_pct', 'guaranteed', 'year_signed', 'draft_year'
    ]].drop_duplicates('player_id').rename(columns={'player_display_name': 'display_name'})

    stat_cols = [
        'player_id', 'season', 'games_played',
        'completions', 'attempts', 'passing_yards', 'passing_tds',
        'passing_interceptions', 'passing_epa', 'passing_cpoe',
        'carries', 'rushing_yards', 'rushing_tds', 'rushing_epa', 'yards_per_carry',
        'receptions', 'targets', 'receiving_yards', 'receiving_tds',
        'receiving_epa', 'target_share', 'wopr',
    ]

    score_cols = [
        'player_id', 'season', 'performance_score', 'perf_norm',
        'expected_perf', 'value_per_million', 'value_score_norm',
        'contract_tier', 'contract_type',
    ]

    conn.execute("DELETE FROM scores")
    conn.execute("DELETE FROM stats")
    conn.execute("DELETE FROM players")

    player_rows.to_sql('players', conn, if_exists='append', index=False)
    df[stat_cols].to_sql('stats', conn, if_exists='append', index=False)
    df[score_cols].to_sql('scores', conn, if_exists='append', index=False)
    conn.commit()
    print(f"Wrote {len(player_rows)} players to DB.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    conn = get_db()
    init_db(conn)
    stats = load_stats()
    contracts = load_contracts()
    df = merge_and_filter(stats, contracts)
    df = build_scores(df)
    write_to_db(df, conn)
    conn.close()
    print("Done. Database ready at:", DB_PATH)
