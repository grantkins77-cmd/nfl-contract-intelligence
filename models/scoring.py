"""
Query helpers used by app.py to fetch player data and peer comparisons.
All heavy scoring is done at load time (data/load_data.py).
This module reads pre-computed scores from the DB and assembles report payloads.
"""

import sqlite3


def search_players(conn, query: str) -> list[dict]:
    """Return players whose names contain the query string (case-insensitive)."""
    rows = conn.execute(
        """
        SELECT player_id, display_name, position, team, apy
        FROM players
        WHERE display_name LIKE ?
        ORDER BY display_name
        LIMIT 10
        """,
        (f"%{query}%",),
    ).fetchall()
    return [dict(r) for r in rows]


def get_player_report(conn, player_id: str) -> dict | None:
    """
    Assemble full report payload for one player:
      - player info + contract
      - 2025 stats
      - pre-computed scores
      - peer comparison (same position, same season)
    Returns None if player not found.
    """
    player = conn.execute(
        "SELECT * FROM players WHERE player_id = ?", (player_id,)
    ).fetchone()
    if not player:
        return None
    player = dict(player)

    stats = conn.execute(
        "SELECT * FROM stats  WHERE player_id = ? AND season = 2025", (player_id,)
    ).fetchone()

    score = conn.execute(
        "SELECT * FROM scores WHERE player_id = ? AND season = 2025", (player_id,)
    ).fetchone()

    peers = conn.execute(
        """
        SELECT p.display_name, p.apy, s.value_score_norm, s.contract_tier
        FROM scores s
        JOIN players p ON p.player_id = s.player_id
        WHERE p.position = ? AND s.season = 2025
        ORDER BY s.value_score_norm DESC
        """,
        (player['position'],),
    ).fetchall()

    return {
        "player":  player,
        "stats":   dict(stats)  if stats else {},
        "score":   dict(score)  if score else {},
        "peers":   [dict(r) for r in peers],
    }
