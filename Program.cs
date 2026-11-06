using System.Globalization;
using System.Text;

var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls("http://0.0.0.0:8080");
builder.Services.AddSingleton<DataStore>();

var app = builder.Build();

app.UseDefaultFiles();
app.UseStaticFiles();

app.MapGet("/healthz", () => Results.Ok("OK"));

app.MapGet("/api/competitors", (DataStore store) =>
    store.Snapshot().Companies);

app.MapGet("/api/financials", (DataStore store, string? company) =>
{
    var snap = store.Snapshot();
    IEnumerable<QuarterRow> rows = snap.Quarters;
    if (!string.IsNullOrWhiteSpace(company))
        rows = rows.Where(r => string.Equals(r.Company, company, StringComparison.OrdinalIgnoreCase));
    return rows.OrderBy(r => r.Company, StringComparer.OrdinalIgnoreCase).ThenBy(r => r.Date, StringComparer.Ordinal).ToList();
});

app.MapGet("/api/benchmark", (DataStore store) => store.Snapshot().Benchmark);

app.Run();

record QuarterRow(string Company, string Date, double? Revenue, double? OperatingIncome, double? EbitMarginPct,
    double? NetIncome, double? GrossProfit);

record BenchmarkRow(string Company, string? Date, double? MarketCap, double? Revenue, double? OperatingMargin,
    string? Symbol, double? CurrentPrice);

record Snapshot(List<string> Companies, List<QuarterRow> Quarters, List<BenchmarkRow> Benchmark);

class DataStore
{
    private readonly ILogger<DataStore> _log;
    private readonly object _lock = new();
    private Snapshot? _cache;
    private DateTime _loadedAt = DateTime.MinValue;

    public DataStore(ILogger<DataStore> log) => _log = log;

    public Snapshot Snapshot()
    {
        lock (_lock)
        {
            var empty = _cache is null || _cache.Quarters.Count == 0;
            if (_cache is null || (empty && DateTime.UtcNow - _loadedAt > TimeSpan.FromSeconds(30)))
            {
                try { _cache = Build(); }
                catch (Exception ex)
                {
                    _log.LogError(ex, "Failed to build dataset");
                    _cache = new Snapshot(new(), new(), new());
                }
                _loadedAt = DateTime.UtcNow;
            }
            return _cache;
        }
    }

    private string? Locate(string name)
    {
        foreach (var dir in new[] { AppContext.BaseDirectory, Directory.GetCurrentDirectory() })
        {
            var p = Path.Combine(dir, name);
            if (File.Exists(p)) return p;
        }
        return null;
    }

    private List<Dictionary<string, string>> ReadCsv(string name)
    {
        var result = new List<Dictionary<string, string>>();
        try
        {
            var path = Locate(name);
            if (path is null) { _log.LogWarning("{File} not found", name); return result; }

            using var fs = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
            using var sr = new StreamReader(fs, Encoding.UTF8, true);
            string[]? header = null;
            foreach (var rec in Csv.Parse(sr))
            {
                if (header is null)
                {
                    header = rec.Select(h => h.Trim().TrimStart('\uFEFF')).ToArray();
                    continue;
                }
                if (rec.Count == 1 && string.IsNullOrWhiteSpace(rec[0])) continue;
                var d = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                for (var i = 0; i < header.Length && i < rec.Count; i++) d[header[i]] = rec[i];
                result.Add(d);
            }
        }
        catch (Exception ex)
        {
            _log.LogError(ex, "Could not read {File}", name);
            result.Clear();
        }
        return result;
    }

    private static double? Num(Dictionary<string, string> d, string key) =>
        d.TryGetValue(key, out var s) &&
        double.TryParse(s, NumberStyles.Float, CultureInfo.InvariantCulture, out var v) &&
        double.IsFinite(v) ? v : null;

    private static string Str(Dictionary<string, string> d, string key) =>
        d.TryGetValue(key, out var s) ? s.Trim() : "";

    private static string NormDate(string s) => s.Length >= 10 ? s[..10] : s;

    private static readonly Dictionary<string, string[]> MetricAliases = new()
    {
        ["revenue"] = new[] { "total revenue", "operating revenue", "revenue" },
        ["opinc"] = new[] { "operating income", "ebit" },
        ["net"] = new[] { "net income", "net income common stockholders" },
        ["gross"] = new[] { "gross profit" },
    };

    private Snapshot Build()
    {
        var fin = ReadCsv("financials.csv");
        var stats = ReadCsv("statistics.csv");

        // company -> date -> metricKey -> value (aliases resolved by priority)
        var pivot = new Dictionary<string, SortedDictionary<string, Dictionary<string, (int pri, double val)>>>(StringComparer.OrdinalIgnoreCase);
        var fxSamples = new Dictionary<string, List<double>>(StringComparer.OrdinalIgnoreCase);

        foreach (var r in fin)
        {
            var company = Str(r, "Company");
            if (company.Length == 0) continue;
            var metric = Str(r, "Metric").ToLowerInvariant();
            var key = MetricAliases.FirstOrDefault(kv => kv.Value.Contains(metric)).Key;
            if (key is null) continue;
            var usd = Num(r, "Value_USD");
            if (usd is null) continue;

            var local = Num(r, "Value");
            if (local is not null && Math.Abs(local.Value) > 1000)
            {
                if (!fxSamples.TryGetValue(company, out var list)) fxSamples[company] = list = new();
                if (list.Count < 200) list.Add(usd.Value / local.Value);
            }

            var date = NormDate(Str(r, "Date"));
            if (!pivot.TryGetValue(company, out var byDate)) pivot[company] = byDate = new(StringComparer.Ordinal);
            if (!byDate.TryGetValue(date, out var m)) byDate[date] = m = new();
            var pri = Array.IndexOf(MetricAliases[key], metric);
            if (!m.TryGetValue(key, out var existing) || pri < existing.pri) m[key] = (pri, usd.Value);
        }

        var quarters = new List<QuarterRow>();
        foreach (var (company, byDate) in pivot)
            foreach (var (date, m) in byDate)
            {
                double? Get(string k) => m.TryGetValue(k, out var v) ? v.val : null;
                var rev = Get("revenue");
                var op = Get("opinc");
                double? margin = rev is > 0 && op is not null ? Math.Round(op.Value / rev.Value * 100, 2) : null;
                quarters.Add(new QuarterRow(company, date, rev, op, margin, Get("net"), Get("gross")));
            }

        var fx = fxSamples.ToDictionary(kv => kv.Key,
            kv => { var s = kv.Value.OrderBy(x => x).ToList(); return s[s.Count / 2]; },
            StringComparer.OrdinalIgnoreCase);

        var statsByCompany = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in stats)
        {
            var c = Str(s, "Company");
            if (c.Length > 0) statsByCompany[c] = s;
        }

        var companies = quarters.Select(q => q.Company)
            .Concat(statsByCompany.Keys)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(c => c, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var benchmark = new List<BenchmarkRow>();
        foreach (var c in companies)
        {
            var latest = quarters.Where(q => q.Company.Equals(c, StringComparison.OrdinalIgnoreCase) && q.Revenue is not null)
                .OrderByDescending(q => q.Date, StringComparer.Ordinal).FirstOrDefault();
            statsByCompany.TryGetValue(c, out var st);

            double? mcap = st is null ? null : Num(st, "marketCap");
            if (mcap is not null)
            {
                var cur = Str(st!, "currency");
                if (!cur.Equals("USD", StringComparison.OrdinalIgnoreCase))
                    mcap = fx.TryGetValue(c, out var rate) ? mcap * rate : null;
            }

            var rev = latest?.Revenue;
            var opm = latest?.EbitMarginPct;
            if (opm is null && st is not null && Num(st, "operatingMargins") is { } om) opm = Math.Round(om * 100, 2);

            benchmark.Add(new BenchmarkRow(c, latest?.Date, mcap, rev, opm,
                st is null ? null : Str(st, "symbol"), st is null ? null : Num(st, "currentPrice")));
        }

        _log.LogInformation("Loaded {Q} quarter rows for {C} companies", quarters.Count, companies.Count);
        return new Snapshot(companies, quarters, benchmark);
    }
}

static class Csv
{
    // RFC 4180 reader supporting quoted fields with embedded commas, quotes and newlines.
    public static IEnumerable<List<string>> Parse(TextReader reader)
    {
        var fields = new List<string>();
        var sb = new StringBuilder();
        var inQuotes = false;
        var any = false;
        int ch;
        while ((ch = reader.Read()) != -1)
        {
            var c = (char)ch;
            if (inQuotes)
            {
                if (c == '"')
                {
                    if (reader.Peek() == '"') { sb.Append('"'); reader.Read(); }
                    else inQuotes = false;
                }
                else sb.Append(c);
                continue;
            }
            switch (c)
            {
                case '"': inQuotes = true; any = true; break;
                case ',': fields.Add(sb.ToString()); sb.Clear(); any = true; break;
                case '\r': break;
                case '\n':
                    if (any || sb.Length > 0) { fields.Add(sb.ToString()); yield return fields; }
                    fields = new(); sb.Clear(); any = false;
                    break;
                default: sb.Append(c); any = true; break;
            }
        }
        if (any || sb.Length > 0) { fields.Add(sb.ToString()); yield return fields; }
    }
}
