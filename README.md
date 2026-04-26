# NFL Contract Intelligence

A full-stack web application that scores NFL skill position players on contract value — identifying who is outperforming their deal and who is being overpaid.

**[View Live App](https://web-production-d7646.up.railway.app)**

---

## What It Does

Search any NFL QB, RB, WR, or TE and receive an AI-generated contract valuation report powered by Claude. Each report includes:

- A **Value Score** (0–100) comparing performance to salary expectations at the same position
- Position-specific 2025 stats (EPA, CPOE, WOPR, YPC, target share)
- A **multi-season trend** showing how the player's value has shifted from 2023–2025
- A full **position ranking** table so you can see where the player stands among peers
- A **side-by-side comparison** tool with a second AI-generated comparative analysis

The home page shows leaderboards for each position — best value players and most overpaid — without requiring a search.

---

## How the Scoring Works

1. **Performance Score** — Each position uses a custom formula weighted toward the most predictive stats (EPA-based). Games played weights penalize injury-shortened seasons.
2. **Normalization** — Raw scores are normalized 0–100 within each position and season.
3. **Linear Regression** — Performance is regressed against APY (annual contract value) to establish what's expected at each salary tier.
4. **Value Score** — The residual (actual − expected) is normalized to 0–100. Above 50 = outperforming contract. Below 50 = underperforming.

Full methodology is available at `/methodology` in the app.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · Flask |
| Database | SQLite |
| Data pipeline | pandas · scipy · nflreadpy · nflverse |
| AI reports | Claude API (Anthropic) |
| Frontend | HTML · CSS · JavaScript (vanilla) |
| Deployment | Railway |

---

## Running Locally

**Requirements:** Python 3.11+, `nfl_project` conda environment (or install dependencies manually)

```bash
# 1. Clone the repo
git clone https://github.com/grantkins77-cmd/nfl-contract-intelligence.git
cd nfl-contract-intelligence

# 2. Install runtime dependencies
pip install -r requirements.txt

# 3. Install data pipeline dependencies (one-time)
pip install -r requirements-data.txt

# 4. Add your Anthropic API key
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# 5. Build the database (downloads 2023–2025 NFL data, takes ~1 min)
python data/load_data.py

# 6. Start the app
python app.py
# → http://localhost:5001
```

> **Note:** The SQLite database is committed to the repo so step 5 is only needed if you want to refresh the data.

---

## Project Structure

```
sports_intelligence/
├── app.py                  # Flask app — all API routes + Claude prompts
├── data/load_data.py       # One-time pipeline: stats + contracts → SQLite
├── database/
│   ├── schema.sql          # players, stats, scores tables
│   └── sports_intelligence.db
├── models/scoring.py       # DB query helpers used by Flask routes
├── templates/
│   ├── index.html          # Main app
│   └── methodology.html    # Scoring explainer page
├── static/
│   ├── style.css
│   ├── main.js
│   └── methodology.css
├── requirements.txt        # Runtime (Flask, Anthropic, gunicorn)
└── requirements-data.txt   # Data pipeline only (nflreadpy, pandas, scipy)
```

---

## Data Sources

- **Player stats:** [nflreadpy](https://github.com/nflverse/nflreadpy) — 2023–2025 NFL regular season
- **Contract data:** [nflverse historical contracts](https://github.com/nflverse/nflverse-data) — APY, guaranteed money, signing year
