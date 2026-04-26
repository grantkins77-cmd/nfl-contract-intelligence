// ── State ─────────────────────────────────────────────────────────────────────
let currentPlayerId   = null;
let currentPlayerName = null;
let leaderboardCache  = null;  // { QB: {top,bottom}, WR: ..., ... }
let activeLbPos       = 'QB';
let lbExpanded        = false;
let cmpDebounce       = null;

// ── Element refs ──────────────────────────────────────────────────────────────
const searchInput  = document.getElementById('search-input');
const autocomplete = document.getElementById('autocomplete-list');
const skeleton     = document.getElementById('skeleton');
const report       = document.getElementById('report');
const lbLoading    = document.getElementById('lb-loading');
const lbBody       = document.getElementById('lb-body');

// ── Init ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initLeaderboards();
  initLbTabs();
  initExpandBtn();
  initCompareSearch();
  document.getElementById('cmp-close').addEventListener('click', () => {
    document.getElementById('compare-section').classList.add('hidden');
  });
});

// ── Leaderboards ──────────────────────────────────────────────────────────────

async function initLeaderboards() {
  const res  = await fetch('/api/leaderboards');
  leaderboardCache = await res.json();
  renderLeaderboard(activeLbPos);
}

function renderLeaderboard(pos) {
  const data = leaderboardCache?.[pos];
  if (!data) return;

  const topEl    = document.getElementById('lb-top');
  const bottomEl = document.getElementById('lb-bottom');

  topEl.innerHTML    = data.top.map(p => lbCardHTML(p)).join('');
  bottomEl.innerHTML = data.bottom.map(p => lbCardHTML(p)).join('');

  // Click → load report
  document.querySelectorAll('.lb-card').forEach(card => {
    card.addEventListener('click', () => loadReport(card.dataset.id));
  });

  lbLoading.classList.add('hidden');
  lbBody.classList.remove('hidden');

  // Re-render full table if expanded
  if (lbExpanded) renderFullTable(pos);
}

function lbCardHTML(p) {
  const tc = tierClass(p.contract_tier ?? '');
  return `
    <div class="lb-card" data-id="${p.player_id}">
      <div class="lb-card-left">
        <div class="lb-card-name">${p.display_name}</div>
        <div class="lb-card-meta">${p.team ?? '—'} · $${p.apy?.toFixed(1) ?? '—'}M/yr</div>
      </div>
      <div class="lb-card-right">
        <div class="lb-card-score" style="color:${tierColor(p.contract_tier ?? '')}">${fmt(p.value_score_norm)}</div>
        <span class="tier-badge ${tc}" style="font-size:.7rem;padding:.15rem .5rem">${p.contract_tier ?? ''}</span>
      </div>
    </div>`;
}

function initLbTabs() {
  document.getElementById('lb-tabs').addEventListener('click', e => {
    const btn = e.target.closest('.pos-tab');
    if (!btn) return;
    document.querySelectorAll('.pos-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeLbPos = btn.dataset.pos;
    if (leaderboardCache) renderLeaderboard(activeLbPos);
    else initLeaderboards();
  });
}

function initExpandBtn() {
  const btn     = document.getElementById('lb-expand-btn');
  const fullDiv = document.getElementById('lb-full');
  btn.addEventListener('click', async () => {
    lbExpanded = !lbExpanded;
    if (lbExpanded) {
      btn.textContent = 'Hide full rankings ↑';
      fullDiv.classList.remove('hidden');
      renderFullTable(activeLbPos);
    } else {
      btn.textContent = 'View full rankings ↓';
      fullDiv.classList.add('hidden');
    }
  });
}

async function renderFullTable(pos) {
  const res  = await fetch(`/api/position/${pos}`);
  const rows = await res.json();
  const tbody = document.getElementById('lb-full-body');
  tbody.innerHTML = rows.map((p, i) => {
    const tc = tierClass(p.contract_tier ?? '');
    return `
      <tr>
        <td>${i + 1}</td>
        <td style="cursor:pointer;color:var(--blue)" class="lb-full-name" data-id="${p.player_id}">${p.display_name}</td>
        <td>${p.team ?? '—'}</td>
        <td>$${p.apy?.toFixed(1) ?? '—'}M</td>
        <td>${p.games_played ?? '—'}</td>
        <td>
          <div class="mini-bar-wrap">
            <div class="mini-bar-track"><div class="mini-bar-fill ${tc}" style="width:${p.value_score_norm ?? 0}%"></div></div>
            <span>${fmt(p.value_score_norm)}</span>
          </div>
        </td>
        <td><span class="tier-badge ${tc}">${p.contract_tier ?? '—'}</span></td>
      </tr>`;
  }).join('');

  tbody.querySelectorAll('.lb-full-name').forEach(cell => {
    cell.addEventListener('click', () => loadReport(cell.dataset.id));
  });
}

// ── Main search autocomplete ──────────────────────────────────────────────────

let searchDebounce = null;

searchInput.addEventListener('input', () => {
  clearTimeout(searchDebounce);
  const q = searchInput.value.trim();
  if (q.length < 2) { hideAuto(autocomplete); return; }
  searchDebounce = setTimeout(() => fetchSuggestions(q, autocomplete, loadReport), 220);
});

searchInput.addEventListener('keydown', e => { if (e.key === 'Escape') hideAuto(autocomplete); });
document.addEventListener('click', e => {
  if (!e.target.closest('.search-wrapper')) {
    hideAuto(autocomplete);
    hideAuto(document.getElementById('cmp-autocomplete'));
  }
});

async function fetchSuggestions(q, listEl, onSelect) {
  const res  = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
  const data = await res.json();
  renderAutocomplete(data, listEl, onSelect);
}

function renderAutocomplete(players, listEl, onSelect) {
  if (!players.length) { hideAuto(listEl); return; }
  listEl.innerHTML = players.map(p => `
    <li data-id="${p.player_id}" data-name="${p.display_name}">
      <span class="pos-tag">${p.position}</span>
      ${p.display_name}
      <span style="margin-left:auto;color:var(--muted);font-size:.8rem">$${p.apy?.toFixed(1) ?? '—'}M</span>
    </li>
  `).join('');
  listEl.classList.remove('hidden');

  listEl.querySelectorAll('li').forEach(li => {
    li.addEventListener('click', () => {
      hideAuto(listEl);
      onSelect(li.dataset.id, li.dataset.name);
    });
  });
}

function hideAuto(listEl) {
  listEl.classList.add('hidden');
  listEl.innerHTML = '';
}

// ── Load report ───────────────────────────────────────────────────────────────

async function loadReport(playerId) {
  report.classList.add('hidden');
  skeleton.classList.remove('hidden');
  document.getElementById('compare-section').classList.add('hidden');
  skeleton.scrollIntoView({ behavior: 'smooth' });

  try {
    const res  = await fetch(`/api/report/${encodeURIComponent(playerId)}`);
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    currentPlayerId   = playerId;
    currentPlayerName = data.player.display_name;
    renderReport(data);
    showCompareSection(data.player);
  } catch (err) {
    alert('Failed to load report. Check that the server is running.');
    console.error(err);
  } finally {
    skeleton.classList.add('hidden');
  }
}

// ── Render report ─────────────────────────────────────────────────────────────

function renderReport(data) {
  const { player, stats, score, peers, narrative, trend } = data;
  const tier = score.contract_tier ?? '';
  const tc   = tierClass(tier);

  // Header
  document.getElementById('r-name').textContent          = player.display_name;
  document.getElementById('r-position').textContent      = player.position;
  document.getElementById('r-team').textContent          = player.team ?? '—';
  document.getElementById('r-contract-type').textContent = score.contract_type ?? '';
  document.getElementById('r-apy').textContent           = `$${player.apy?.toFixed(1) ?? '—'}M / yr`;

  const tierEl = document.getElementById('r-tier');
  tierEl.textContent = tier;
  tierEl.className   = `tier-badge ${tc}`;

  const rankIdx = peers.findIndex(p => p.display_name === player.display_name);
  const rankEl  = document.getElementById('r-rank');
  rankEl.innerHTML  = rankIdx >= 0
    ? `<strong>#${rankIdx + 1}</strong> of ${peers.length} ${player.position}s`
    : '';

  // Score cards
  document.getElementById('value-card').className = `score-card featured ${tc}`;
  document.getElementById('r-value-score').textContent = fmt(score.value_score_norm);
  document.getElementById('r-value-score').style.color = tierColor(tier);
  setBar('r-value-bar', score.value_score_norm, tc);

  document.getElementById('r-perf-norm').textContent = fmt(score.perf_norm);
  setBar('r-perf-bar', score.perf_norm, 'neutral');

  document.getElementById('r-expected').textContent = fmt(score.expected_perf);
  setBar('r-expected-bar', score.expected_perf, 'neutral');

  const delta   = score.value_per_million;
  const deltaEl = document.getElementById('r-delta');
  deltaEl.textContent = delta != null ? (delta >= 0 ? `+${delta.toFixed(1)}` : delta.toFixed(1)) : '—';
  deltaEl.style.color = delta == null ? '' : delta >= 0 ? 'var(--elite)' : 'var(--over)';

  // Trend
  renderTrend(trend ?? []);

  // Stats
  renderStats(player.position, stats);

  // Narrative
  const narrativeEl = document.getElementById('r-narrative');
  narrativeEl.innerHTML = (narrative ?? '').split(/\n\n+/)
    .filter(p => p.trim())
    .map(p => `<p>${p.trim()}</p>`)
    .join('');

  // Peers
  document.getElementById('r-peers-title').textContent = `${player.position} Rankings · 2025`;
  const tbody = document.getElementById('r-peers-body');
  tbody.innerHTML = peers.map((p, i) => {
    const ptc = tierClass(p.contract_tier ?? '');
    return `
      <tr class="${p.display_name === player.display_name ? 'highlight' : ''}">
        <td>${i + 1}</td>
        <td>${p.display_name}</td>
        <td>$${p.apy?.toFixed(1) ?? '—'}M</td>
        <td>
          <div class="mini-bar-wrap">
            <div class="mini-bar-track"><div class="mini-bar-fill ${ptc}" style="width:${p.value_score_norm ?? 0}%"></div></div>
            <span>${fmt(p.value_score_norm)}</span>
          </div>
        </td>
        <td><span class="tier-badge ${ptc}">${p.contract_tier ?? '—'}</span></td>
      </tr>`;
  }).join('');

  report.classList.remove('hidden');
  report.scrollIntoView({ behavior: 'smooth' });
}

// ── Trend ─────────────────────────────────────────────────────────────────────

function renderTrend(trend) {
  const wrap = document.getElementById('r-trend-wrap');
  const el   = document.getElementById('r-trend');

  if (!trend || trend.length <= 1) {
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');

  el.innerHTML = trend.map((t, i) => {
    const tc    = tierClass(t.contract_tier ?? '');
    const color = tierColor(t.contract_tier ?? '');
    let arrow = '';
    if (i > 0) {
      const prev = trend[i - 1];
      const diff = (t.value_score_norm ?? 0) - (prev.value_score_norm ?? 0);
      const cls  = diff >= 0 ? 'up' : 'down';
      const sym  = diff >= 0 ? '↑' : '↓';
      arrow = `<div class="trend-arrow ${cls}">${sym} ${Math.abs(diff).toFixed(1)}</div>`;
    }
    return `
      ${arrow}
      <div class="trend-node">
        <div class="trend-season">${t.season}</div>
        <div class="trend-score" style="color:${color}">${fmt(t.value_score_norm)}</div>
        <div class="trend-tier"><span class="tier-badge ${tc}" style="font-size:.65rem;padding:.1rem .4rem">${t.contract_tier ?? ''}</span></div>
      </div>`;
  }).join('');
}

// ── Stats ─────────────────────────────────────────────────────────────────────

const STAT_DEFS = {
  QB: [
    { label: 'Pass Yards', key: 'passing_yards',        dec: 0 },
    { label: 'TDs',        key: 'passing_tds',           dec: 0 },
    { label: 'INTs',       key: 'passing_interceptions', dec: 0 },
    { label: 'Pass EPA',   key: 'passing_epa',           dec: 1 },
    { label: 'CPOE',       key: 'passing_cpoe',          dec: 1, unit: '%' },
    { label: 'Games',      key: 'games_played',          dec: 0 },
  ],
  WR: [
    { label: 'Receptions', key: 'receptions',      dec: 0 },
    { label: 'Targets',    key: 'targets',         dec: 0 },
    { label: 'Rec Yards',  key: 'receiving_yards', dec: 0 },
    { label: 'TDs',        key: 'receiving_tds',   dec: 0 },
    { label: 'Rec EPA',    key: 'receiving_epa',   dec: 1 },
    { label: 'WOPR',       key: 'wopr',            dec: 2 },
  ],
  RB: [
    { label: 'Carries',    key: 'carries',        dec: 0 },
    { label: 'Rush Yards', key: 'rushing_yards',  dec: 0 },
    { label: 'YPC',        key: 'yards_per_carry', dec: 1 },
    { label: 'Rush TDs',   key: 'rushing_tds',    dec: 0 },
    { label: 'Rush EPA',   key: 'rushing_epa',    dec: 1 },
    { label: 'Games',      key: 'games_played',   dec: 0 },
  ],
  TE: [
    { label: 'Receptions', key: 'receptions',      dec: 0 },
    { label: 'Targets',    key: 'targets',         dec: 0 },
    { label: 'Rec Yards',  key: 'receiving_yards', dec: 0 },
    { label: 'TDs',        key: 'receiving_tds',   dec: 0 },
    { label: 'Rec EPA',    key: 'receiving_epa',   dec: 1 },
    { label: 'Tgt Share',  key: 'target_share',    dec: 1, unit: '%', scale: 100 },
  ],
};

function renderStats(position, stats) {
  const defs = STAT_DEFS[position] ?? [];
  document.getElementById('r-stats-grid').innerHTML = defs.map(d => {
    let val = stats[d.key];
    const display = val == null ? '—' : parseFloat(d.scale ? val * d.scale : val).toFixed(d.dec);
    return `
      <div class="stat-card">
        <div class="stat-label">${d.label}</div>
        <div class="stat-value">${display}</div>
        ${d.unit ? `<div class="stat-unit">${d.unit}</div>` : ''}
      </div>`;
  }).join('');
}

// ── Compare ───────────────────────────────────────────────────────────────────

function showCompareSection(player) {
  const section = document.getElementById('compare-section');
  document.getElementById('cmp-p1-pill').textContent = `${player.display_name} (${player.position})`;
  document.getElementById('cmp-result').classList.add('hidden');
  document.getElementById('cmp-search').value = '';
  section.classList.remove('hidden');
}

function initCompareSearch() {
  const cmpInput = document.getElementById('cmp-search');
  const cmpAuto  = document.getElementById('cmp-autocomplete');

  cmpInput.addEventListener('input', () => {
    clearTimeout(cmpDebounce);
    const q = cmpInput.value.trim();
    if (q.length < 2) { hideAuto(cmpAuto); return; }
    cmpDebounce = setTimeout(
      () => fetchSuggestions(q, cmpAuto, (id, name) => loadComparison(id, name, cmpInput)),
      220
    );
  });
}

async function loadComparison(id2, name2, inputEl) {
  if (!currentPlayerId) return;
  inputEl.value = name2;

  const loadingEl = document.getElementById('cmp-loading');
  const resultEl  = document.getElementById('cmp-result');
  loadingEl.classList.remove('hidden');
  resultEl.classList.add('hidden');

  try {
    const res  = await fetch(`/api/compare/${encodeURIComponent(currentPlayerId)}/${encodeURIComponent(id2)}`);
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    renderComparison(data);
  } catch (err) {
    alert('Failed to load comparison.');
    console.error(err);
  } finally {
    loadingEl.classList.add('hidden');
  }
}

function renderComparison(data) {
  const { player1: d1, player2: d2, narrative } = data;
  const sc1 = d1.score.value_score_norm ?? 0;
  const sc2 = d2.score.value_score_norm ?? 0;

  document.getElementById('cmp-col1').innerHTML = cmpColHTML(d1, sc1 >= sc2);
  document.getElementById('cmp-col2').innerHTML = cmpColHTML(d2, sc2 > sc1);

  const narrativeEl = document.getElementById('cmp-narrative');
  narrativeEl.innerHTML = (narrative ?? '').split(/\n\n+/)
    .filter(p => p.trim())
    .map(p => `<p>${p.trim()}</p>`)
    .join('');

  document.getElementById('cmp-result').classList.remove('hidden');
  document.getElementById('cmp-result').scrollIntoView({ behavior: 'smooth' });
}

function cmpColHTML(d, isWinner) {
  const { player, score } = d;
  const tier = score.contract_tier ?? '';
  const tc   = tierClass(tier);
  const rows = [
    ['Value Score', fmt(score.value_score_norm)],
    ['Performance', fmt(score.perf_norm)],
    ['Expected',    fmt(score.expected_perf)],
    ['Delta',       score.value_per_million != null
      ? (score.value_per_million >= 0 ? `+${score.value_per_million.toFixed(1)}` : score.value_per_million.toFixed(1))
      : '—'],
  ];
  return `
    <div class="cmp-col-name">${player.display_name} ${isWinner ? '<span style="color:var(--elite)">✓</span>' : ''}</div>
    <div class="cmp-col-meta">
      <span class="badge pos-badge">${player.position}</span>
      <span class="badge secondary">${player.team ?? '—'}</span>
      <span class="tier-badge ${tc}">${tier}</span>
    </div>
    <div style="font-size:.85rem;color:var(--muted);margin-bottom:.75rem">$${player.apy?.toFixed(1) ?? '—'}M / yr</div>
    ${rows.map(([label, val]) => `
      <div class="cmp-score-row">
        <span class="cmp-score-label">${label}</span>
        <span class="cmp-score-val ${isWinner && label === 'Value Score' ? 'cmp-winner' : ''}">${val}</span>
      </div>`).join('')}`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setBar(id, value, cls) {
  const el = document.getElementById(id);
  el.style.width = `${Math.min(Math.max(value ?? 0, 0), 100)}%`;
  el.className   = `score-bar ${cls}`;
}
function fmt(val) { return val != null ? parseFloat(val).toFixed(1) : '—'; }
function tierClass(tier) {
  if (tier.includes('Elite')) return 'elite';
  if (tier.includes('Fair'))  return 'fair';
  return 'over';
}
function tierColor(tier) {
  if (tier.includes('Elite')) return 'var(--elite)';
  if (tier.includes('Fair'))  return 'var(--fair)';
  return 'var(--over)';
}
