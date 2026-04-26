import os
import sqlite3
from flask import Flask, request, jsonify, render_template, g
from anthropic import Anthropic
from dotenv import load_dotenv
from models.scoring import search_players, get_player_report

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'sports_intelligence.db')


# ── DB connection (per-request) ───────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/methodology')
def methodology():
    return render_template('methodology.html')


@app.route('/api/search')
def search():
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])
    return jsonify(search_players(get_db(), query))


@app.route('/api/report/<player_id>')
def report(player_id):
    db   = get_db()
    data = get_player_report(db, player_id)
    if not data:
        return jsonify({'error': 'Player not found'}), 404

    trend = db.execute(
        "SELECT season, value_score_norm, contract_tier FROM scores WHERE player_id = ? ORDER BY season",
        (player_id,)
    ).fetchall()
    data['trend'] = [dict(r) for r in trend]

    data['narrative'] = generate_narrative(data)
    return jsonify(data)


@app.route('/api/leaderboards')
def leaderboards():
    db     = get_db()
    result = {}
    for pos in ['QB', 'RB', 'WR', 'TE']:
        rows = db.execute(
            """
            SELECT p.player_id, p.display_name, p.team, p.apy,
                   s.value_score_norm, s.contract_tier, s.contract_type
            FROM scores s
            JOIN players p ON p.player_id = s.player_id
            WHERE p.position = ? AND s.season = 2025
            ORDER BY s.value_score_norm DESC
            """,
            (pos,),
        ).fetchall()
        players = [dict(r) for r in rows]
        result[pos] = {
            'top':    players[:5],
            'bottom': list(reversed(players[-5:])) if len(players) >= 5 else list(reversed(players)),
        }
    return jsonify(result)


@app.route('/api/position/<pos>')
def position_rankings(pos):
    if pos not in ('QB', 'RB', 'WR', 'TE'):
        return jsonify({'error': 'Invalid position'}), 400
    rows = get_db().execute(
        """
        SELECT p.player_id, p.display_name, p.team, p.apy,
               s.value_score_norm, s.perf_norm, s.value_per_million,
               s.contract_tier, s.contract_type,
               st.games_played
        FROM scores s
        JOIN players p  ON p.player_id  = s.player_id
        JOIN stats  st  ON st.player_id = s.player_id AND st.season = 2025
        WHERE p.position = ? AND s.season = 2025
        ORDER BY s.value_score_norm DESC
        """,
        (pos,),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/compare/<id1>/<id2>')
def compare(id1, id2):
    db = get_db()
    d1 = get_player_report(db, id1)
    d2 = get_player_report(db, id2)
    if not d1 or not d2:
        return jsonify({'error': 'One or both players not found'}), 404
    narrative = generate_comparison_narrative(d1, d2)
    return jsonify({'player1': d1, 'player2': d2, 'narrative': narrative})


# ── Claude narratives ─────────────────────────────────────────────────────────

def generate_narrative(data: dict) -> str:
    client = Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
    player = data['player']
    stats  = data['stats']
    score  = data['score']
    peers  = data['peers']

    prompt = f"""You are an NFL contract analyst writing a concise valuation report for a front office audience.

Player: {player['display_name']} | Position: {player['position']} | Team: {player['team']}
Contract: ${player['apy']}M/yr APY | Type: {score.get('contract_type', 'N/A')}

2025 Performance:
- Performance score (0–100, position-normalized): {score.get('perf_norm', 0):.1f}
- Expected score for their salary tier: {score.get('expected_perf', 0):.1f}
- Value over/under expectation: {score.get('value_per_million', 0):.1f} pts
- Final value score (0–100): {score.get('value_score_norm', 0):.1f}
- Contract tier: {score.get('contract_tier', 'N/A')}

Key 2025 stats: {_format_stats(player['position'], stats)}

Top value players at {player['position']}: {_format_peers(peers[:5])}
Lowest value players at {player['position']}: {_format_peers(peers[-3:])}

Write a 3-paragraph valuation report:
1. Overall verdict on the contract value
2. What the stats say about on-field performance relative to salary
3. Contract outlook — strength or liability going forward?

200 words max. No markdown headers. Plain prose only."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def generate_comparison_narrative(d1: dict, d2: dict) -> str:
    client  = Anthropic()
    p1, s1, sc1 = d1['player'], d1['stats'], d1['score']
    p2, s2, sc2 = d2['player'], d2['stats'], d2['score']

    prompt = f"""You are an NFL contract analyst. Compare these two players head-to-head.

{p1['display_name']} ({p1['position']}, {p1['team']}) — ${p1['apy']:.1f}M/yr
  Value score: {sc1.get('value_score_norm', 0):.1f} | Tier: {sc1.get('contract_tier', 'N/A')}
  Stats: {_format_stats(p1['position'], s1)}

{p2['display_name']} ({p2['position']}, {p2['team']}) — ${p2['apy']:.1f}M/yr
  Value score: {sc2.get('value_score_norm', 0):.1f} | Tier: {sc2.get('contract_tier', 'N/A')}
  Stats: {_format_stats(p2['position'], s2)}

Write 2 paragraphs:
1. Who provides better contract value and the key reason why
2. What each contract signals about their team's cap management

150 words max. No headers. Plain prose only."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ── Formatting helpers ────────────────────────────────────────────────────────

def _format_stats(position: str, stats: dict) -> str:
    if position == 'QB':
        return (f"{stats.get('passing_yards', 0):.0f} pass yds, "
                f"{stats.get('passing_tds', 0):.0f} TDs, "
                f"{stats.get('passing_interceptions', 0):.0f} INTs, "
                f"EPA {stats.get('passing_epa', 0):.1f}, "
                f"CPOE {stats.get('passing_cpoe', 0):.1f}%")
    elif position == 'WR':
        return (f"{stats.get('receptions', 0):.0f} rec / {stats.get('targets', 0):.0f} tgt, "
                f"{stats.get('receiving_yards', 0):.0f} yds, "
                f"{stats.get('receiving_tds', 0):.0f} TDs, "
                f"EPA {stats.get('receiving_epa', 0):.1f}, "
                f"WOPR {stats.get('wopr', 0):.2f}")
    elif position == 'RB':
        return (f"{stats.get('carries', 0):.0f} car, "
                f"{stats.get('rushing_yards', 0):.0f} yds, "
                f"{stats.get('yards_per_carry', 0):.1f} YPC, "
                f"rushing EPA {stats.get('rushing_epa', 0):.1f}")
    elif position == 'TE':
        return (f"{stats.get('receptions', 0):.0f} rec / {stats.get('targets', 0):.0f} tgt, "
                f"{stats.get('receiving_yards', 0):.0f} yds, "
                f"{stats.get('receiving_tds', 0):.0f} TDs, "
                f"EPA {stats.get('receiving_epa', 0):.1f}, "
                f"target share {stats.get('target_share', 0):.1%}")
    return str(stats)


def _format_peers(peers: list[dict]) -> str:
    lines = [
        f"  {p['display_name']} — ${p['apy']:.1f}M, score {p['value_score_norm']:.1f} ({p['contract_tier']})"
        for p in peers
    ]
    return "\n".join(lines) if lines else "  N/A"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_ENV') != 'production')
