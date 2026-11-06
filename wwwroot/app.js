(() => {
  const CYAN = '#38bdf8', MINT = '#34d399', MUTED = '#94a3b8', GRID = '#334155';
  const $ = id => document.getElementById(id);
  const state = { rows: [], bench: [], sortKey: 'date', sortDir: -1, trend: null, compare: null };

  const cols = [
    ['company', 'Company'], ['date', 'Date'], ['revenue', 'Revenue'], ['operatingIncome', 'Op. Income'],
    ['ebitMarginPct', 'EBIT Margin %'], ['grossProfit', 'Gross Profit'], ['netIncome', 'Net Income']
  ];

  const fmtMoney = v => {
    if (v == null) return '–';
    const a = Math.abs(v), s = v < 0 ? '-' : '';
    if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(1)}M`;
    return `${s}$${a.toLocaleString()}`;
  };
  const fmtPct = v => (v == null ? '–' : `${v.toFixed(2)}%`);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  async function getJson(url) {
    try {
      const r = await fetch(url);
      if (!r.ok) throw new Error(r.status);
      return await r.json();
    } catch (e) {
      $('status').textContent = `Failed to load ${url}`;
      return [];
    }
  }

  function filtered() {
    const from = $('from').value, to = $('to').value;
    return state.rows.filter(r => (!from || r.date >= from) && (!to || r.date <= to));
  }

  function renderKpis(rows) {
    const company = $('company').value;
    const latest = [...rows].sort((a, b) => b.date.localeCompare(a.date))[0];
    $('kRev').textContent = fmtMoney(latest?.revenue);
    $('kEbit').textContent = fmtMoney(latest?.operatingIncome);
    $('kMargin').textContent = fmtPct(latest?.ebitMarginPct);
    const d = latest ? `Quarter ending ${latest.date}` : 'No data';
    $('kRevN').textContent = $('kEbitN').textContent = $('kMarginN').textContent = d;

    const ranked = state.bench.filter(b => b.marketCap != null).sort((a, b) => b.marketCap - a.marketCap);
    const idx = ranked.findIndex(b => b.company === company);
    const b = state.bench.find(x => x.company === company);
    $('kCap').textContent = fmtMoney(b?.marketCap);
    $('kCapN').textContent = idx >= 0 ? `Rank #${idx + 1} of ${ranked.length} by market cap` : 'Rank n/a';
  }

  function baseOptions(tickFmt) {
    return {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: MUTED } } },
      scales: {
        x: { ticks: { color: MUTED }, grid: { color: GRID } },
        y: { ticks: { color: MUTED, callback: tickFmt }, grid: { color: GRID } }
      }
    };
  }

  function renderTrend(rows) {
    const data = [...rows].sort((a, b) => a.date.localeCompare(b.date));
    if (state.trend) state.trend.destroy();
    state.trend = new Chart($('trend'), {
      data: {
        labels: data.map(r => r.date),
        datasets: [
          { type: 'bar', label: 'Revenue', data: data.map(r => r.revenue), backgroundColor: 'rgba(56,189,248,.6)', borderColor: CYAN },
          { type: 'line', label: 'EBIT', data: data.map(r => r.operatingIncome), borderColor: MINT, backgroundColor: MINT, tension: .25 }
        ]
      },
      options: baseOptions(v => fmtMoney(v))
    });
  }

  function renderCompare() {
    const data = state.bench.filter(b => b.operatingMargin != null).sort((a, b) => b.operatingMargin - a.operatingMargin);
    const sel = $('company').value;
    if (state.compare) state.compare.destroy();
    state.compare = new Chart($('compare'), {
      type: 'bar',
      data: {
        labels: data.map(b => b.company),
        datasets: [{
          label: 'Operating Margin %', data: data.map(b => b.operatingMargin),
          backgroundColor: data.map(b => (b.company === sel ? MINT : 'rgba(56,189,248,.6)'))
        }]
      },
      options: { ...baseOptions(v => v + '%'), indexAxis: 'y' }
    });
  }

  function renderTable(rows) {
    const { sortKey, sortDir } = state;
    const sorted = [...rows].sort((a, b) => {
      const x = a[sortKey], y = b[sortKey];
      if (x == null) return 1;
      if (y == null) return -1;
      return (typeof x === 'string' ? x.localeCompare(y) : x - y) * sortDir;
    });
    $('tbl').querySelector('thead').innerHTML = '<tr>' + cols.map(([k, l]) =>
      `<th data-k="${k}">${l}${k === sortKey ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('') + '</tr>';
    $('tbl').querySelector('tbody').innerHTML = sorted.map(r => `<tr>
      <td>${esc(r.company)}</td><td>${r.date}</td><td>${fmtMoney(r.revenue)}</td><td>${fmtMoney(r.operatingIncome)}</td>
      <td>${fmtPct(r.ebitMarginPct)}</td><td>${fmtMoney(r.grossProfit)}</td><td>${fmtMoney(r.netIncome)}</td></tr>`).join('');
    $('tbl').querySelectorAll('th').forEach(th => th.onclick = () => {
      const k = th.dataset.k;
      state.sortDir = state.sortKey === k ? -state.sortDir : 1;
      state.sortKey = k;
      renderTable(filtered());
    });
  }

  async function loadCompany() {
    const company = $('company').value;
    state.rows = company ? await getJson('/api/financials?company=' + encodeURIComponent(company)) : [];
    refresh();
  }

  function refresh() {
    const rows = filtered();
    renderKpis(rows);
    renderTrend(rows);
    renderCompare();
    renderTable(rows);
    if (!rows.length && !$('status').textContent) $('status').textContent = 'No data for the selected filters.';
    else if (rows.length && $('status').textContent.startsWith('No data')) $('status').textContent = '';
  }

  async function init() {
    const [companies, bench] = await Promise.all([getJson('/api/competitors'), getJson('/api/benchmark')]);
    state.bench = bench;
    $('company').innerHTML = companies.map(c => `<option>${esc(c)}</option>`).join('');
    $('company').onchange = loadCompany;
    $('from').onchange = $('to').onchange = refresh;
    $('reset').onclick = () => { $('from').value = ''; $('to').value = ''; refresh(); };
    if (!companies.length) { $('status').textContent = 'No competitor data available.'; refresh(); return; }
    await loadCompany();
  }

  init();
})();
