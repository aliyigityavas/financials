(() => {
  'use strict';

  /* ------------------------------------------------------------------ */
  /* Constants                                                            */
  /* ------------------------------------------------------------------ */
  const CYAN = '#38bdf8', BLUE = '#3b82f6', MINT = '#34d399', MUTED = '#94a3b8', GRID = '#334155', TEXT = '#e2e8f0';

  const LOGO_MAP = {
    "AMICA GROUP": "amica_group", "BEKO GROUP": "arcelik", "ARÇELİK": "arcelik", "ARCELIK": "arcelik",
    "BOSCH": "bsh", "BSH": "bsh",
    "DE'LONGHI GROUP": "delonghi", "DE'LONGHI": "delonghi",
    "ELECTROLUX GROUP": "electrolux", "ELECTROLUX": "electrolux", "GORENJE": "gorenje",
    "GREE ELECTRIC": "gree", "HAIER GROUP": "haier", "HAIER SMART HOME": "haier",
    "HISENSE GROUP": "hisense", "HISENSE": "hisense",
    "LG ELECTRONICS": "lg", "MIDEA GROUP": "midea", "MIELE": "miele",
    "PANASONIC HOLDINGS": "panasonic", "PANASONIC": "panasonic",
    "ROYAL PHILIPS": "philips", "PHILIPS": "philips",
    "SAMSUNG GROUP": "samsung", "SAMSUNG ELECTRONICS": "samsung",
    "GROUPE SEB": "seb_group", "SEB GROUP": "seb_group",
    "SHARP CORPORATION": "sharp", "SHARP": "sharp", "SMEG": "smeg",
    "TCL TECHNOLOGY": "tcl", "TCL ELECTRONICS": "tcl",
    "VESTEL GROUP": "vestel", "VESTEL": "vestel",
    "WHIRLPOOL CORPORATION": "whirlpool", "XIAOMI": "xiaomi"
  };

  // Standard metric order used everywhere: Revenue, GP, OP, EBITDA, Net Profit
  const METRICS = [
    { key: 'rev',    field: 'revenue',         label: 'Revenue',                      short: 'Revenue' },
    { key: 'gp',     field: 'grossProfit',     label: 'Gross Profit (GP)',            short: 'GP' },
    { key: 'op',     field: 'operatingIncome', label: 'Operating Income / EBIT (OP)', short: 'OP' },
    { key: 'ebitda', field: 'ebitda',          label: 'EBITDA',                       short: 'EBITDA' },
    { key: 'net',    field: 'netIncome',       label: 'Net Profit',                   short: 'Net Profit' }
  ];
  const MARGIN_KEYS = ['gp', 'op', 'ebitda', 'net'];

  const SECTION_TITLES = {
    summary: 'Summary', statistics: 'Statistics', profile: 'Profile', financials: 'Financials',
    marketshare: 'Market Share', news: 'News', ai: 'AI Analysis'
  };
  const COMING_SOON = new Set(['profile', 'marketshare', 'news', 'ai']);

  // Non-monetary statement lines: never converted, never prefixed with a currency symbol
  const NON_MONETARY = /shares|share issued|tax rate/i;

  /* ------------------------------------------------------------------ */
  /* State                                                                */
  /* ------------------------------------------------------------------ */
  const S = {
    section: 'summary',
    company: null,
    quarter: null,          // 'YYYYQn'
    mode: 'Q',              // 'Q' | 'Y'
    cur: 'USD',             // 'USD' | 'EUR' | 'OC'
    bm: 'op',
    stmt: 'pl',
    kpiPct: { gp: false, op: false, ebitda: false, net: false },
    companies: [],
    byCo: new Map(),        // company -> { byQk: Map<qk, row> (Quarterly), annual: Map<year, row> (Annual) }
    bench: [],
    stmtCache: new Map(),   // "company|type" -> rows
    sumSort: { key: 'idx', dir: -1 },
    profiles: new Map(),    // company -> profile row from /api/profile
    charts: { trend: null, compare: null }
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ------------------------------------------------------------------ */
  /* Quarter keys: qk = year * 4 + n  (n = 1..4)                          */
  /* ------------------------------------------------------------------ */
  const qkOf = (year, n) => year * 4 + n;
  const qkYear = qk => Math.floor((qk - 1) / 4);
  const qkN = qk => ((qk - 1) % 4) + 1;
  const qkLabel = qk => `${qkYear(qk)}Q${qkN(qk)}`;
  const qkParse = label => {
    const m = /^(\d{4})Q([1-4])$/.exec(label || '');
    return m ? qkOf(+m[1], +m[2]) : null;
  };

  /* ------------------------------------------------------------------ */
  /* Formatting                                                           */
  /* ------------------------------------------------------------------ */
  function compact(v, digits = 2) {
    if (v == null || !Number.isFinite(v)) return '–';
    const a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e12) return `${s}${(a / 1e12).toFixed(digits)}T`;
    if (a >= 1e9) return `${s}${(a / 1e9).toFixed(digits)}B`;
    if (a >= 1e6) return `${s}${(a / 1e6).toFixed(digits)}M`;
    if (a >= 1e3) return `${s}${(a / 1e3).toFixed(digits)}K`;
    return `${s}${a.toFixed(a < 10 && a !== 0 ? 2 : 0)}`;
  }

  function withSymbol(text, sym) {
    if (text === '–' || !sym) return text;
    return text.startsWith('-') ? `-${sym}${text.slice(1)}` : `${sym}${text}`;
  }

  const fmtMoney = (v, sym = '') => withSymbol(compact(v), sym);
  const fmtPct = v => (v == null || !Number.isFinite(v) ? '–' : `${v.toFixed(2)}%`);
  const pct = (x, rev) => (x == null || rev == null || rev === 0 ? null : (x / rev) * 100);

  function ocCode() {
    const rows = S.byCo.get(S.company);
    if (!rows) return '';
    for (const qk of Array.from(rows.byQk.keys()).sort((a, b) => b - a)) {
      const c = rows.byQk.get(qk).currency;
      if (c) return c;
    }
    for (const y of Array.from(rows.annual.keys()).sort((a, b) => b - a)) {
      const c = rows.annual.get(y).currency;
      if (c) return c;
    }
    return '';
  }

  function symbol(cur = S.cur, oc = ocCode()) {
    if (cur === 'USD') return '$';
    if (cur === 'EUR') return '€';
    return oc ? `${oc} ` : '';
  }

  const curLabel = (cur = S.cur) => (cur === 'OC' ? `Original currency${ocCode() ? ' (' + ocCode() + ')' : ''}` : cur);
  const pick = (m, cur = S.cur) => (!m ? null : cur === 'USD' ? m.usd : cur === 'EUR' ? m.eur : m.oc);

  /* ------------------------------------------------------------------ */
  /* Logos                                                                */
  /* ------------------------------------------------------------------ */
  function logoKey(name) {
    const up = (name || '').toUpperCase().trim();
    if (LOGO_MAP[up]) return LOGO_MAP[up];
    const plain = up.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    if (LOGO_MAP[plain]) return LOGO_MAP[plain];
    if (/^BEKO\b/.test(plain)) return 'arcelik';
    return plain.replace(/^(ROYAL|THE)\s+/, '').split(/\s+/)[0].toLowerCase().replace(/[^a-z0-9]/g, '');
  }

  function initials(name) {
    return (name || '?').split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase();
  }

  function renderHeader() {
    const name = S.company || '';
    $('#coName').textContent = name;
    $('#sectionTitle').textContent = SECTION_TITLES[S.section] || '';
    $('#coInitials').textContent = initials(name);
    const img = $('#coLogo'), badge = $('#coBadge');
    if (!name) { badge.classList.add('noimg'); img.hidden = true; return; }
    const key = logoKey(name);
    img.onload = () => { img.hidden = false; badge.classList.remove('noimg'); };
    img.onerror = () => { img.hidden = true; badge.classList.add('noimg'); };
    img.hidden = true;
    badge.classList.add('noimg');
    img.alt = name;
    img.src = `/images/logos/${key}.png`;
  }

  /* ------------------------------------------------------------------ */
  /* Data loading                                                         */
  /* ------------------------------------------------------------------ */
  function setStatus(msg) { $('#status').textContent = msg || ''; }

  async function getJson(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      setStatus(`Failed to load ${url}`);
      return [];
    }
  }

  function entryFor(company) {
    let entry = S.byCo.get(company);
    if (!entry) S.byCo.set(company, entry = { byQk: new Map(), annual: new Map(), ytd: new Map() });
    return entry;
  }

  // Rows come straight from the CSV (Period_Type = Quarterly | Annual | YTD); nothing is summed client-side.
  function indexRows(quarterly, annual, ytd) {
    S.byCo = new Map();
    for (const r of quarterly) {
      const qk = qkParse(r.quarter);
      if (qk != null) entryFor(r.company).byQk.set(qk, r);
    }
    for (const r of annual) {
      if (r.year) entryFor(r.company).annual.set(r.year, r);
    }
    for (const r of ytd) {
      const qk = qkParse(r.quarter);
      if (qk != null) entryFor(r.company).ytd.set(qk, r);
    }
  }

  /* ------------------------------------------------------------------ */
  /* Periods (shared by charts, KPIs, tables and financial statements)    */
  /* ------------------------------------------------------------------ */
  // Yearly / YTD columns: Annual for past full years, plus the current (selected) year as the latest YTD
  // column published in the CSV ("2026Q3 YTD"). If the selected quarter is Q4 and a full-year row exists,
  // the Annual row is used instead. Keys: 'A<year>' for Annual, 'Y<qk>' for YTD.
  function yearlyPeriods(annualYears, ytdQuarters, sel) {
    const selYear = qkYear(sel);
    const out = annualYears.filter(y => y < selYear).sort((a, b) => a - b)
      .map(y => ({ label: String(y), key: `A${y}` }));
    const ytd = ytdQuarters.filter(k => qkYear(k) === selYear && k <= sel).sort((a, b) => b - a)[0];
    if (annualYears.includes(selYear) && (ytd == null || qkN(sel) === 4)) out.push({ label: String(selYear), key: `A${selYear}` });
    else if (ytd != null) out.push({ label: `${qkLabel(ytd)} YTD`, key: `Y${ytd}`, ytd: true });
    return out;
  }

  function makePeriods(company = S.company) {
    const sel = qkParse(S.quarter);
    if (sel == null) return [];
    const selYear = qkYear(sel);

    if (S.mode === 'Q') {
      const out = [];
      for (let k = qkOf(selYear - 1, 1); k <= sel; k++) out.push({ label: qkLabel(k), key: k });
      return out;
    }

    const e = S.byCo.get(company);
    if (!e) return [];
    return yearlyPeriods(Array.from(e.annual.keys()), Array.from(e.ytd.keys()), sel);
  }

  function rowAt(company, p) {
    const e = S.byCo.get(company);
    if (!e) return undefined;
    if (S.mode === 'Q') return e.byQk.get(p.key);
    const n = +String(p.key).slice(1);
    return String(p.key)[0] === 'Y' ? e.ytd.get(n) : e.annual.get(n);
  }

  function seriesFor(company, cur, periods) {
    return periods.map((p, idx) => {
      const row = rowAt(company, p);
      const out = { idx, label: p.label };
      for (const mt of METRICS) out[mt.key] = pick(row?.[mt.field], cur);
      return out;
    });
  }

  /* ------------------------------------------------------------------ */
  /* KPI cards                                                            */
  /* ------------------------------------------------------------------ */
  function renderKpis(series) {
    const last = series[series.length - 1];
    const sym = symbol();
    const cards = METRICS.map(mt => {
      const v = last ? last[mt.key] : null;
      let main, note;
      if (mt.key === 'rev') {
        main = fmtMoney(v, sym);
        note = last ? last.label : 'No data';
      } else if (S.kpiPct[mt.key]) {
        main = fmtPct(pct(v, last?.rev));
        note = `${mt.short} margin · ${last ? last.label : ''}`;
      } else {
        main = fmtMoney(v, sym);
        note = last ? last.label : 'No data';
      }
      const toggle = mt.key === 'rev' ? '' :
        `<button class="pct-toggle${S.kpiPct[mt.key] ? ' on' : ''}" data-k="${mt.key}" title="Toggle amount / % of revenue" aria-label="Toggle percentage">%</button>`;
      return `<div class="card kpi"><div class="label">${esc(mt.label)}</div>${toggle}<div class="value">${main}</div><div class="note">${esc(note)}</div></div>`;
    });

    const b = S.bench.find(x => x.company === S.company);
    const ranked = S.bench.filter(x => x.marketCap != null).sort((a, c) => c.marketCap - a.marketCap);
    const idx = ranked.findIndex(x => x.company === S.company);
    const cap = !b ? null : S.cur === 'USD' ? b.marketCap : S.cur === 'EUR' ? b.marketCapEur : b.marketCapOc;
    const capSym = S.cur === 'OC' ? (b?.marketCapCurrency ? b.marketCapCurrency + ' ' : '') : sym;
    cards.push(`<div class="card kpi"><div class="label">Market Cap / Benchmark Rank</div><div class="value">${fmtMoney(cap, capSym)}</div>` +
      `<div class="note">${idx >= 0 ? `Rank #${idx + 1} of ${ranked.length} (by USD market cap)` : 'Rank n/a'}</div></div>`);

    $('#kpis').innerHTML = cards.join('');
  }

  /* ------------------------------------------------------------------ */
  /* Charts                                                               */
  /* ------------------------------------------------------------------ */
  function chartDefaults() {
    Chart.defaults.color = MUTED;
    Chart.defaults.font.family = '"Segoe UI", system-ui, sans-serif';
    if (window.ChartDataLabels) Chart.register(window.ChartDataLabels);
  }

  // Bars occupy the lower ~55% of the plot and the EBIT line the upper band, so the two label sets never meet.
  function trendScales(series) {
    const rev = series.map(s => s.rev).filter(v => v != null && Number.isFinite(v));
    const op = series.map(s => s.op).filter(v => v != null && Number.isFinite(v));
    const out = {};
    if (rev.length) out.revMax = Math.max(...rev, 0) / 0.55;
    if (op.length) {
      const lo = Math.min(...op), hi = Math.max(...op);
      const span = (hi - lo) || Math.abs(hi) || 1;
      const range = span / 0.28;
      out.opMin = lo - 0.64 * range;
      out.opMax = out.opMin + range;
    }
    return out;
  }

  function renderTrend(series) {
    const sym = symbol();
    $('#trendTitle').textContent = `Revenue & EBIT Trend — ${curLabel()} · ${S.mode === 'Q' ? 'Quarterly' : 'Yearly / YTD'}`;
    if (S.charts.trend) S.charts.trend.destroy();
    const sc = trendScales(series);

    S.charts.trend = new Chart($('#trend'), {
      type: 'bar',
      data: {
        labels: series.map(s => s.label),
        datasets: [
          {
            type: 'bar', label: `Revenue (${S.cur})`, data: series.map(s => s.rev), yAxisID: 'yRev', order: 2,
            backgroundColor: 'rgba(56,189,248,.65)', borderColor: CYAN, borderWidth: 1, borderRadius: 4,
            datalabels: {
              anchor: 'end', align: 'start', offset: 4, clamp: true, color: '#f8fafc', font: { size: 10, weight: '600' },
              formatter: v => (v == null ? '' : compact(v))
            }
          },
          {
            type: 'line', label: `EBIT / Operating Income (${S.cur})`, data: series.map(s => s.op), yAxisID: 'yOp', order: 1,
            borderColor: MINT, backgroundColor: MINT, pointRadius: 4, pointHoverRadius: 6, tension: 0.25, spanGaps: true,
            datalabels: {
              anchor: 'end', align: 'top', offset: 8, clamp: true, color: MINT, font: { size: 10, weight: '600' },
              backgroundColor: 'rgba(11,17,32,.85)', borderRadius: 3, padding: 2,
              formatter: v => (v == null ? '' : compact(v))
            }
          }
        ]
      },
      options: {
        indexAxis: 'x',
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        layout: { padding: { top: 22 } },
        plugins: {
          legend: { labels: { color: MUTED } },
          tooltip: { callbacks: { label: c => `${c.dataset.label}: ${fmtMoney(c.parsed.y, sym)}` } }
        },
        scales: {
          x: { ticks: { color: MUTED }, grid: { color: GRID } },
          yRev: {
            type: 'linear', position: 'left', beginAtZero: true, max: sc.revMax,
            title: { display: true, text: 'Revenue', color: CYAN },
            ticks: { color: CYAN, callback: v => compact(v, 1) }, grid: { color: GRID }
          },
          yOp: {
            type: 'linear', position: 'right', min: sc.opMin, max: sc.opMax,
            title: { display: true, text: 'EBIT', color: MINT },
            ticks: { color: MINT, callback: v => compact(v, 1) }, grid: { drawOnChartArea: false }
          }
        }
      }
    });
  }

  function benchValue(company, metric) {
    const periods = makePeriods(company);
    if (!periods.length) return null;
    // Absolute revenue is not comparable across original currencies; fall back to USD
    const cur = metric === 'rev' && S.cur === 'OC' ? 'USD' : S.cur;
    const last = seriesFor(company, cur, [periods[periods.length - 1]])[0];
    return metric === 'rev' ? last.rev : pct(last[metric], last.rev);
  }

  function renderCompare() {
    const metric = S.bm;
    const isRev = metric === 'rev';
    const names = { rev: 'Revenue', gp: 'GP %', op: 'OP %', ebitda: 'EBITDA %' };
    const cur = isRev && S.cur === 'OC' ? 'USD' : S.cur;
    const periods = makePeriods();
    const label = S.mode === 'Q' ? (periods.length ? periods[periods.length - 1].label : '') : 'latest annual / YTD';
    $('#bmTitle').textContent = `Competitor Benchmarking — ${names[metric]}${isRev ? ' (' + cur + ')' : ''} · ${label}`;

    const data = S.companies
      .map(c => ({ company: c, v: benchValue(c, metric) }))
      .filter(d => d.v != null && Number.isFinite(d.v))
      .sort((a, b) => b.v - a.v);

    const inner = $('#bmInner');
    inner.style.height = `${Math.max(320, data.length * 28 + 40)}px`;
    if (S.charts.compare) S.charts.compare.destroy();

    S.charts.compare = new Chart($('#compare'), {
      type: 'bar',
      data: {
        labels: data.map(d => d.company),
        datasets: [{
          label: names[metric], data: data.map(d => d.v), borderRadius: 4,
          backgroundColor: data.map(d => (d.company === S.company ? MINT : 'rgba(56,189,248,.65)')),
          borderColor: data.map(d => (d.company === S.company ? MINT : CYAN)), borderWidth: 1
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true,
        maintainAspectRatio: false,
        layout: { padding: { right: 56 } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => (isRev ? fmtMoney(c.parsed.x, symbol(cur)) : fmtPct(c.parsed.x)) } },
          datalabels: {
            anchor: 'end', align: 'end', color: TEXT, font: { size: 10 }, clip: false,
            formatter: v => (v == null ? '' : isRev ? compact(v) : `${v.toFixed(1)}%`)
          }
        },
        scales: {
          x: { grid: { color: GRID }, grace: '8%', ticks: { color: MUTED, callback: v => (isRev ? compact(v, 1) : `${v}%`) } },
          y: { grid: { display: false }, ticks: { color: TEXT, autoSkip: false, font: { size: 11 } } }
        }
      }
    });
  }

  /* ------------------------------------------------------------------ */
  /* Sortable summary table                                               */
  /* ------------------------------------------------------------------ */
  function sortRows(rows, key, dir, getter) {
    return [...rows].sort((a, b) => {
      const x = getter(a, key), y = getter(b, key);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * dir;
    });
  }

  function renderSummaryTable(series) {
    const sym = symbol();
    $('#sumTableTitle').textContent = `Financial metrics — ${S.company || ''} · ${curLabel()}`;

    const cols = [{ key: 'idx', label: 'Period' }]
      .concat(METRICS.map(m => ({ key: m.key, label: m.short })))
      .concat(MARGIN_KEYS.map(k => ({ key: 'p_' + k, label: METRICS.find(m => m.key === k).short + ' %' })));

    const rows = series.map(s => {
      const r = { ...s };
      MARGIN_KEYS.forEach(k => { r['p_' + k] = pct(s[k], s.rev); });
      return r;
    });
    const sorted = sortRows(rows, S.sumSort.key, S.sumSort.dir, (r, k) => r[k]);

    $('#sumTbl thead').innerHTML = '<tr>' + cols.map(c =>
      `<th data-k="${c.key}">${esc(c.label)}${c.key === S.sumSort.key ? (S.sumSort.dir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';

    $('#sumTbl tbody').innerHTML = sorted.map(r => {
      const money = k => { const v = r[k]; return `<td class="${v != null && v < 0 ? 'neg' : ''}">${fmtMoney(v, sym)}</td>`; };
      const p = k => { const v = r['p_' + k]; return `<td class="${v != null && v < 0 ? 'neg' : ''}">${fmtPct(v)}</td>`; };
      return `<tr><td>${esc(r.label)}</td>${METRICS.map(m => money(m.key)).join('')}${MARGIN_KEYS.map(p).join('')}</tr>`;
    }).join('');

    $$('#sumTbl th').forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      S.sumSort.dir = S.sumSort.key === k ? -S.sumSort.dir : -1;
      S.sumSort.key = k;
      renderSummaryTable(series);
    });
  }

  function renderSummary() {
    const periods = makePeriods();
    const series = seriesFor(S.company, S.cur, periods);
    if (!series.some(s => METRICS.some(m => s[m.key] != null))) {
      setStatus(`No ${S.cur} data for ${S.company} in the selected range.`);
    } else if ($('#status').textContent.startsWith('No ')) {
      setStatus('');
    }
    renderKpis(series);
    renderTrend(series);
    renderCompare();
    renderSummaryTable(series);
  }

  /* ------------------------------------------------------------------ */
  /* Statistics = Company Profile Card (from /api/profile, statistics.csv) */
  /* ------------------------------------------------------------------ */
  async function loadProfile(company) {
    if (!S.profiles.has(company)) {
      let p = null;
      try {
        const r = await fetch(`/api/profile?company=${encodeURIComponent(company)}`);
        if (r.ok) p = await r.json();
      } catch (e) { /* handled as missing profile */ }
      S.profiles.set(company, p && p.found ? p : { found: false });
    }
    return S.profiles.get(company);
  }

  function setField(sel, text) {
    const el = $(sel);
    el.textContent = text || 'Not available';
    el.classList.toggle('empty', !text);
  }

  function webUrl(raw) {
    if (!raw) return null;
    const s = /^[a-z][a-z0-9+.-]*:/i.test(raw) ? raw : `https://${raw}`;
    try {
      const u = new URL(s);
      return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
    } catch (e) { return null; }
  }

  async function renderStatistics() {
    const company = S.company;
    $('#pcName').textContent = company;
    $('#pcSub').textContent = 'Company profile';
    const p = await loadProfile(company);
    if (company !== S.company) return; // superseded while loading

    const found = !!p.found;
    $('#pcSub').textContent = found && p.symbol ? `Ticker: ${p.symbol}` : 'Company profile';
    setField('#pcLocation', found ? [p.country, p.city].filter(Boolean).join(' · ') : '');
    setField('#pcIndustry', found ? p.industry : '');
    setField('#pcAddress', found ? p.address : '');
    setField('#pcPhone', found ? p.phone : '');

    const web = $('#pcWebsite');
    const href = found ? webUrl(p.website) : null;
    web.textContent = '';
    web.classList.toggle('empty', !href);
    if (href) {
      const a = document.createElement('a');
      a.href = href; a.target = '_blank'; a.rel = 'noopener noreferrer';
      a.textContent = p.website;
      web.appendChild(a);
    } else {
      web.textContent = 'Not available';
    }

    const note = $('#pcNote');
    note.hidden = found;
    note.textContent = found ? '' : `No corporate profile for ${company} was found in statistics.csv.`;
  }

  /* ------------------------------------------------------------------ */
  /* Financials (P&L / Balance Sheet)                                     */
  /* ------------------------------------------------------------------ */
  async function loadStatement(company, type) {
    const pt = S.mode === 'Q' ? 'Quarterly' : 'Annual,YTD';
    const key = `${company}|${type}|${pt}`;
    if (!S.stmtCache.has(key)) {
      const rows = await getJson(`/api/statement?company=${encodeURIComponent(company)}&type=${type}&periodType=${pt}`);
      S.stmtCache.set(key, Array.isArray(rows) ? rows : []);
    }
    return S.stmtCache.get(key);
  }

  function fmtStmt(metric, v, cur, sym) {
    if (v == null || !Number.isFinite(v)) return '–';
    if (/tax rate/i.test(metric)) return `${(v * 100).toFixed(1)}%`;
    if (NON_MONETARY.test(metric)) return compact(v);
    if (/\beps\b/i.test(metric)) return withSymbol(v.toFixed(2), sym);
    return fmtMoney(v, sym);
  }

  async function renderFinancials() {
    const company = S.company, type = S.stmt, mode = S.mode;
    if (!company) return;
    const rows = await loadStatement(company, type);
    if (company !== S.company || type !== S.stmt || mode !== S.mode) return; // superseded while loading

    const sym = symbol();
    $('#finHint').textContent =
      `${type === 'pl' ? 'Income statement' : 'Balance sheet'} · ${curLabel()} · ${S.mode === 'Q' ? 'Quarterly' : 'Yearly / YTD'}` +
      (type === 'bs' ? ' · period-end balances' : '');

    // Row key: quarter key (Quarterly), 'A<year>' (Annual) or 'Y<qk>' (YTD), as published in the CSV
    const keyOf = r => {
      if (S.mode === 'Q') return r.periodType === 'Quarterly' ? qkParse(r.quarter) : null;
      if (r.periodType === 'Annual') return r.year ? `A${r.year}` : null;
      if (r.periodType === 'YTD') { const q = qkParse(r.quarter); return q == null ? null : `Y${q}`; }
      return null;
    };
    const lines = new Map(); // metric -> { order, orderKey, byKey }
    const annualYears = new Set(), ytdQuarters = new Set();
    let seq = 0;
    for (const r of rows) {
      const k = keyOf(r);
      if (k == null) continue;
      if (typeof k === 'string') (k[0] === 'A' ? annualYears.add(+k.slice(1)) : ytdQuarters.add(+k.slice(1)));
      let ln = lines.get(r.metric);
      if (!ln) lines.set(r.metric, ln = { metric: r.metric, order: r.order, orderSeq: seq, byKey: new Map() });
      if (seq++ >= ln.orderSeq) ln.order = r.order;
      ln.byKey.set(k, r);
    }

    let periods;
    const sel = qkParse(S.quarter);
    if (S.mode === 'Q') periods = makePeriods();
    else periods = sel == null ? [] : yearlyPeriods(Array.from(annualYears), Array.from(ytdQuarters), sel);

    const computed = [];
    let idx = 0;
    for (const ln of lines.values()) {
      const useCur = NON_MONETARY.test(ln.metric) ? 'OC' : S.cur;
      const vals = periods.map(p => pick(ln.byKey.get(p.key), useCur));
      if (vals.some(v => v != null)) computed.push({ ln, vals, useCur, idx: idx++ });
    }
    // Account order follows the Order column (ascending = statement top-down); ties keep CSV order
    computed.sort((a, b) => (a.ln.order - b.ln.order) || (a.idx - b.idx));

    // Annual view: hide columns with no data at all
    const keep = periods.map((p, i) => S.mode === 'Q' || computed.some(c => c.vals[i] != null));
    const shown = periods.filter((p, i) => keep[i]);

    // YoY base: Quarterly = same quarter a year earlier. Yearly = previous YTD (same quarter) if present,
    // otherwise the previous year's Annual value.
    const curP = shown[shown.length - 1];
    const prevKeys = !curP ? [] : S.mode === 'Q' ? [curP.key - 4]
      : curP.ytd ? [`Y${+curP.key.slice(1) - 4}`, `A${qkYear(+curP.key.slice(1)) - 1}`]
      : [`A${+curP.key.slice(1) - 1}`];
    const yoyLabel = curP ? `${curP.label} vs ${S.mode === 'Q' ? qkLabel(prevKeys[0]) : 'prior year'}` : '';

    const yoyCells = ({ ln, useCur }) => {
      if (!curP) return ['<td class="yoy na">-</td>', '<td class="na">-</td>'];
      const cur = pick(ln.byKey.get(curP.key), useCur);
      let prev = null;
      for (const k of prevKeys) { prev = pick(ln.byKey.get(k), useCur); if (prev != null) break; }
      if (cur == null || prev == null || !Number.isFinite(cur) || !Number.isFinite(prev)) return ['<td class="yoy na">-</td>', '<td class="na">-</td>'];
      const d = cur - prev;
      const cls = d > 0 ? 'pos' : d < 0 ? 'neg' : 'na';
      const dTxt = (d > 0 ? '+' : '') + fmtStmt(ln.metric, d, S.cur, sym);
      const pTxt = prev === 0 ? '-' : `${d > 0 ? '+' : ''}${((d / Math.abs(prev)) * 100).toFixed(1)}%`;
      return [`<td class="yoy ${cls}">${dTxt}</td>`, `<td class="${prev === 0 ? 'na' : cls}">${pTxt}</td>`];
    };

    $('#stmtTbl thead').innerHTML = '<tr><th>Account</th>' + shown.map(p => `<th>${esc(p.label)}</th>`).join('') +
      `<th class="yoy" title="${esc(yoyLabel)}">YoY Delta</th><th title="${esc(yoyLabel)}">YoY %</th></tr>`;
    $('#stmtTbl tbody').innerHTML = computed.length
      ? computed.map(c =>
        `<tr><td title="${esc(c.ln.metric)}">${esc(c.ln.metric)}</td>` +
        c.vals.filter((v, i) => keep[i]).map(v => `<td class="${v != null && v < 0 ? 'neg' : ''}">${fmtStmt(c.ln.metric, v, S.cur, sym)}</td>`).join('') +
        yoyCells(c).join('') + '</tr>').join('')
      : `<tr><td colspan="${shown.length + 3}">No data available.</td></tr>`;
  }

  /* ------------------------------------------------------------------ */
  /* Orchestration                                                        */
  /* ------------------------------------------------------------------ */
  function renderAll() {
    renderHeader();
    $('#controls').style.display = COMING_SOON.has(S.section) ? 'none' : '';
    if (!S.company) return;
    if (S.section === 'summary') renderSummary();
    else if (S.section === 'statistics') renderStatistics();
    else if (S.section === 'financials') renderFinancials();
  }

  function showSection(name) {
    S.section = name;
    $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.section === name));
    $$('.section').forEach(s => s.classList.toggle('active', s.id === `sec-${name}`));
    renderAll();
  }

  function onCompanyChange() {
    S.company = $('#company').value;
    renderAll();
  }

  function populateQuarters() {
    const qks = new Set();
    for (const { byQk } of S.byCo.values()) for (const k of byQk.keys()) qks.add(k);
    const list = Array.from(qks).sort((a, b) => b - a);
    $('#quarter').innerHTML = list.map(k => `<option value="${qkLabel(k)}">${qkLabel(k)}</option>`).join('');
    S.quarter = list.length ? qkLabel(list[0]) : null;
    if (S.quarter) $('#quarter').value = S.quarter;
  }

  function bindEvents() {
    $('#nav').addEventListener('click', e => {
      const b = e.target.closest('.nav-item');
      if (b) showSection(b.dataset.section);
    });
    $('#collapseBtn').onclick = () => $('#sidebar').classList.toggle('collapsed');
    $('#company').onchange = onCompanyChange;
    $('#quarter').onchange = e => { S.quarter = e.target.value; renderAll(); };

    $('#modeSeg').addEventListener('click', e => {
      const b = e.target.closest('button[data-mode]');
      if (!b) return;
      S.mode = b.dataset.mode;
      $$('#modeSeg button').forEach(x => x.classList.toggle('active', x === b));
      renderAll();
    });
    $('#curSeg').addEventListener('click', e => {
      const b = e.target.closest('button[data-cur]');
      if (!b) return;
      S.cur = b.dataset.cur;
      $$('#curSeg button').forEach(x => x.classList.toggle('active', x === b));
      renderAll();
    });
    $('#stmtSeg').addEventListener('click', e => {
      const b = e.target.closest('button[data-stmt]');
      if (!b) return;
      S.stmt = b.dataset.stmt;
      $$('#stmtSeg button').forEach(x => x.classList.toggle('active', x === b));
      renderFinancials();
    });
    $('#bmMetric').onchange = e => { S.bm = e.target.value; renderCompare(); };
    $('#kpis').addEventListener('click', e => {
      const b = e.target.closest('.pct-toggle');
      if (!b) return;
      S.kpiPct[b.dataset.k] = !S.kpiPct[b.dataset.k];
      renderSummary();
    });

    // Corporate logo: /images/beko_logo.png, then the Arçelik logo; text only if both are missing
    const brand = $('.sidebar-logo');
    if (brand) {
      const textFallback = () => { brand.style.display = 'none'; $('#brandFallback').classList.add('show'); };
      let retried = false;
      brand.addEventListener('error', () => {
        if (!retried) { retried = true; brand.src = '/images/logos/arcelik.png'; } else textFallback();
      });
      if (brand.complete && brand.naturalWidth === 0) brand.dispatchEvent(new Event('error'));
    }
  }

  async function init() {
    chartDefaults();
    bindEvents();

    const [companies, quarterly, annual, ytd, bench] = await Promise.all([
      getJson('/api/competitors'), getJson('/api/financials?periodType=Quarterly'),
      getJson('/api/financials?periodType=Annual'), getJson('/api/financials?periodType=YTD'), getJson('/api/benchmark')
    ]);
    S.companies = Array.isArray(companies) ? companies : [];
    S.bench = Array.isArray(bench) ? bench : [];
    const arr = x => (Array.isArray(x) ? x : []);
    indexRows(arr(quarterly), arr(annual), arr(ytd));
    populateQuarters();

    if (!S.companies.length) {
      setStatus('No competitor data available.');
      renderHeader();
      return;
    }
    $('#company').innerHTML = S.companies.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    S.company = S.companies.find(c => logoKey(c) === 'arcelik') || S.companies[0];
    $('#company').value = S.company;
    renderAll();
  }

  init();
})();
