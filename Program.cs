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
    store.Current().Companies);

// periodType = Quarterly | Annual | YTD, comma separated; "yearly" = Annual + YTD. Omitted = all.
app.MapGet("/api/financials", (DataStore store, string? company, string? periodType) =>
{
    var snap = store.Current();
    var pt = DataStore.ParsePeriodTypes(periodType);
    IEnumerable<QuarterRow> rows = snap.Quarters;
    if (!string.IsNullOrWhiteSpace(company))
        rows = rows.Where(r => string.Equals(r.Company, company, StringComparison.OrdinalIgnoreCase));
    if (pt is not null)
        rows = rows.Where(r => pt.Contains(r.PeriodType));
    return rows.OrderBy(r => r.Company, StringComparer.OrdinalIgnoreCase)
        .ThenBy(r => r.PeriodType, StringComparer.Ordinal)
        .ThenBy(r => r.Date, StringComparer.Ordinal).ToList();
});

app.MapGet("/api/benchmark", (DataStore store) => store.Current().Benchmark);

// type=pl (financials.csv, default) or type=bs (balance_sheet.csv); long format, one row per metric and quarter.
app.MapGet("/api/statement", (DataStore store, string? company, string? type, string? periodType) =>
{
    var snap = store.Current();
    var src = string.Equals(type, "bs", StringComparison.OrdinalIgnoreCase) ? snap.BalanceSheet : snap.Pl;
    if (string.IsNullOrWhiteSpace(company) || !src.TryGetValue(company, out var rows)) return new List<StmtRow>();
    var pt = DataStore.ParsePeriodTypes(periodType);
    return pt is null ? rows : rows.Where(r => pt.Contains(r.PeriodType)).ToList();
});

// Corporate metadata from statistics.csv (address, industry, phone, website). Unknown company -> found=false.
app.MapGet("/api/profile", (DataStore store, string? company) =>
{
    var snap = store.Current();
    if (!string.IsNullOrWhiteSpace(company) && snap.Profiles.TryGetValue(company, out var p)) return p;
    return new ProfileRow(false, company ?? "", "", "", "", "", "", "", "", null);
});

app.Run();

// Oc = original currency, Usd = Value_USD, Eur = Value_EUR
record Money(double? Oc, double? Usd, double? Eur);

// PeriodType is "Quarterly" or "Annual", taken as-is from the CSV Period_Type column (no summing).
record QuarterRow(string Company, string PeriodType, string Date, string Quarter, int Year, string Currency,
    Money Revenue, Money GrossProfit, Money OperatingIncome, Money Ebitda, Money NetIncome);

record StmtRow(string Metric, int Order, string PeriodType, string Date, string Quarter, int Year, string Currency,
    double? Oc, double? Usd, double? Eur);

class PivotCell
{
    public string Quarter = "";
    public int Year;
    public string Currency = "";
    public Dictionary<string, (int pri, Money val)> Values = new();
}

record BenchmarkRow(string Company, string? Date, double? MarketCap, double? MarketCapEur, double? MarketCapOc,
    string? MarketCapCurrency, double? Revenue, double? OperatingMargin, string? Symbol, double? CurrentPrice);

record ProfileRow(bool Found, string Company, string Country, string City, string Address, string Industry,
    string Phone, string Website, string Symbol, string? Summary);

record Snapshot(List<string> Companies, List<QuarterRow> Quarters, List<BenchmarkRow> Benchmark,
    Dictionary<string, List<StmtRow>> Pl, Dictionary<string, List<StmtRow>> BalanceSheet,
    Dictionary<string, ProfileRow> Profiles);

class DataStore
{
    private readonly ILogger<DataStore> _log;
    private readonly object _lock = new();
    private Snapshot? _cache;
    private DateTime _loadedAt = DateTime.MinValue;

    public DataStore(ILogger<DataStore> log) => _log = log;

    public Snapshot Current()
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
                    _cache = new Snapshot(new(), new(), new(),
                        new(StringComparer.OrdinalIgnoreCase), new(StringComparer.OrdinalIgnoreCase),
                        new(StringComparer.OrdinalIgnoreCase));
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

    // Accepts the new (Value_OC / Account / Currency_OC) and legacy (Value / Metric / Currency) column names.
    private static string? Raw(Dictionary<string, string> d, string[] keys)
    {
        foreach (var k in keys)
            if (d.TryGetValue(k, out var s) && !string.IsNullOrWhiteSpace(s)) return s;
        return null;
    }

    private static double? Num(Dictionary<string, string> d, params string[] keys) =>
        double.TryParse(Raw(d, keys), NumberStyles.Float, CultureInfo.InvariantCulture, out var v) &&
        double.IsFinite(v) ? v : null;

    private static string Str(Dictionary<string, string> d, params string[] keys) =>
        Raw(d, keys)?.Trim() ?? "";

    private static string NormDate(string s) => s.Length >= 10 ? s[..10] : s;

    // Missing Period_Type (legacy files) is treated as Quarterly.
    public static string? NormPeriodType(string? p)
    {
        if (string.IsNullOrWhiteSpace(p)) return null;
        p = p.Trim();
        if (p.Equals("ytd", StringComparison.OrdinalIgnoreCase)) return "YTD";
        if (p.StartsWith("a", StringComparison.OrdinalIgnoreCase) || p.StartsWith("y", StringComparison.OrdinalIgnoreCase)) return "Annual";
        if (p.StartsWith("q", StringComparison.OrdinalIgnoreCase)) return "Quarterly";
        return null;
    }

    // "Quarterly" | "Annual" | "YTD" | comma list; "yearly" expands to Annual + YTD. Null = no filter.
    public static HashSet<string>? ParsePeriodTypes(string? p)
    {
        if (string.IsNullOrWhiteSpace(p)) return null;
        var set = new HashSet<string>(StringComparer.Ordinal);
        foreach (var part in p.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (part.StartsWith("yearly", StringComparison.OrdinalIgnoreCase)) { set.Add("Annual"); set.Add("YTD"); continue; }
            var n = NormPeriodType(part);
            if (n is not null) set.Add(n);
        }
        return set.Count == 0 ? null : set;
    }

    private static string PeriodTypeOf(Dictionary<string, string> r) => NormPeriodType(Str(r, "Period_Type")) ?? "Quarterly";

    private static bool IsBalanceSheet(Dictionary<string, string> r) =>
        Str(r, "Statement_Type").StartsWith("B", StringComparison.OrdinalIgnoreCase);

    // Empty Statement_Type (legacy) = PnL. "CashFlow"/"CF" and "BS" are excluded.
    private static bool IsPnl(Dictionary<string, string> r)
    {
        var s = Str(r, "Statement_Type");
        return s.Length == 0 || s.StartsWith("P", StringComparison.OrdinalIgnoreCase) ||
               s.StartsWith("I", StringComparison.OrdinalIgnoreCase);
    }

    // Statement company names (financials.csv) -> names used in statistics.csv
    private static readonly Dictionary<string, string> StatsAlias = new(StringComparer.OrdinalIgnoreCase)
    {
        ["AR\u00C7EL\u0130K"] = "BEKO GROUP",
        ["DE'LONGHI"] = "DE'LONGHI GROUP",
        ["ELECTROLUX"] = "ELECTROLUX GROUP",
        ["HAIER SMART HOME"] = "HAIER GROUP",
        ["HISENSE HOME APPLIANCES"] = "HISENSE GROUP",
        ["PANASONIC"] = "PANASONIC HOLDINGS",
        ["PHILIPS"] = "ROYAL PHILIPS",
        ["SAMSUNG ELECTRONICS"] = "SAMSUNG GROUP",
        ["SEB GROUP"] = "GROUPE SEB",
        ["SHARP"] = "SHARP CORPORATION",
        ["TCL ELECTRONICS"] = "TCL TECHNOLOGY",
        ["VESTEL"] = "VESTEL GROUP",
    };

    private static readonly Dictionary<string, string[]> MetricAliases = new()
    {
        ["revenue"] = new[] { "total revenue", "operating revenue", "revenue" },
        ["gross"] = new[] { "gross profit" },
        ["opinc"] = new[] { "operating income", "total operating income as reported" },
        ["ebitda"] = new[] { "ebitda", "normalized ebitda" },
        ["net"] = new[] { "net income", "net income common stockholders" },
    };

    private static string QuarterOf(string date, string q)
    {
        if (q.Length > 0) return q;
        return DateTime.TryParse(date, CultureInfo.InvariantCulture, DateTimeStyles.None, out var dt)
            ? $"{dt.Year}Q{(dt.Month + 2) / 3}" : "";
    }

    private static int YearOf(string date, string y)
    {
        if (int.TryParse(y, NumberStyles.Float, CultureInfo.InvariantCulture, out var n)) return n;
        return DateTime.TryParse(date, CultureInfo.InvariantCulture, DateTimeStyles.None, out var dt) ? dt.Year : 0;
    }

    private static Dictionary<string, List<StmtRow>> BuildStatement(List<Dictionary<string, string>> src)
    {
        var res = new Dictionary<string, List<StmtRow>>(StringComparer.OrdinalIgnoreCase);
        foreach (var r in src)
        {
            var company = Str(r, "Company");
            var metric = Str(r, "Account", "Metric");
            if (company.Length == 0 || metric.Length == 0) continue;
            var oc = Num(r, "Value_OC", "Value");
            var usd = Num(r, "Value_USD");
            var eur = Num(r, "Value_EUR");
            if (oc is null && usd is null && eur is null) continue;
            var date = NormDate(Str(r, "Date"));
            if (!res.TryGetValue(company, out var list)) res[company] = list = new();
            list.Add(new StmtRow(metric, (int)(Num(r, "Order") ?? 0), PeriodTypeOf(r), date, QuarterOf(date, Str(r, "Quarter")),
                YearOf(date, Str(r, "Year")), Str(r, "Currency_OC", "Currency"), oc, usd, eur));
        }
        return res;
    }

    private static double Median(List<double> v)
    {
        var s = v.OrderBy(x => x).ToList();
        return s[s.Count / 2];
    }

    private Snapshot Build()
    {
        var fin = ReadCsv("financials.csv");
        var stats = ReadCsv("statistics.csv");
        var benchCsv = ReadCsv("benchmark.csv");
        // New financials.csv carries PnL, BS and CashFlow rows (Statement_Type); legacy files keep BS in balance_sheet.csv.
        // FIX: CashFlow rows must not be mixed into the income statement.
        var finPl = fin.Where(IsPnl).ToList();
        var finBs = fin.Where(IsBalanceSheet).ToList();
        var bs = finBs.Count > 0 ? finBs : ReadCsv("balance_sheet.csv");

        // (company, periodType, date) -> cell with metricKey -> value (aliases resolved by priority)
        var pivot = new Dictionary<(string company, string pt, string date), PivotCell>();
        var fxSamples = new Dictionary<string, List<double>>(StringComparer.OrdinalIgnoreCase);
        var fxEurSamples = new Dictionary<string, List<double>>(StringComparer.OrdinalIgnoreCase);

        foreach (var r in finPl)
        {
            var company = Str(r, "Company");
            if (company.Length == 0) continue;
            var metric = Str(r, "Account", "Metric").ToLowerInvariant();
            var key = MetricAliases.FirstOrDefault(kv => kv.Value.Contains(metric)).Key;
            if (key is null) continue;
            var local = Num(r, "Value_OC", "Value");
            var usd = Num(r, "Value_USD");
            var eur = Num(r, "Value_EUR");
            if (local is null && usd is null && eur is null) continue;

            if (local is not null && Math.Abs(local.Value) > 1000)
            {
                if (usd is not null)
                {
                    if (!fxSamples.TryGetValue(company, out var list)) fxSamples[company] = list = new();
                    if (list.Count < 200) list.Add(usd.Value / local.Value);
                }
                if (eur is not null)
                {
                    if (!fxEurSamples.TryGetValue(company, out var list)) fxEurSamples[company] = list = new();
                    if (list.Count < 200) list.Add(eur.Value / local.Value);
                }
            }

            var date = NormDate(Str(r, "Date"));
            var k3 = (company, PeriodTypeOf(r), date);
            if (!pivot.TryGetValue(k3, out var cell)) pivot[k3] = cell = new PivotCell();
            cell.Quarter = QuarterOf(date, Str(r, "Quarter"));
            cell.Year = YearOf(date, Str(r, "Year"));
            cell.Currency = Str(r, "Currency_OC", "Currency");
            var pri = Array.IndexOf(MetricAliases[key], metric);
            if (!cell.Values.TryGetValue(key, out var existing) || pri < existing.pri) cell.Values[key] = (pri, new Money(local, usd, eur));
        }

        var quarters = new List<QuarterRow>();
        foreach (var (k3, cell) in pivot)
        {
            Money Get(string k) => cell.Values.TryGetValue(k, out var v) ? v.val : new Money(null, null, null);
            quarters.Add(new QuarterRow(k3.company, k3.pt, k3.date, cell.Quarter, cell.Year, cell.Currency,
                Get("revenue"), Get("gross"), Get("opinc"), Get("ebitda"), Get("net")));
        }

        var fx = fxSamples.ToDictionary(kv => kv.Key, kv => Median(kv.Value), StringComparer.OrdinalIgnoreCase);
        var fxEur = fxEurSamples.ToDictionary(kv => kv.Key, kv => Median(kv.Value), StringComparer.OrdinalIgnoreCase);

        var statsByCompany = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in stats)
        {
            var c = Str(s, "Company");
            if (c.Length > 0) statsByCompany[c] = s;
        }

        var finCompanies = quarters.Select(q => q.Company).Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        var aliased = new HashSet<string>(
            finCompanies.Where(StatsAlias.ContainsKey).Select(c => StatsAlias[c]), StringComparer.OrdinalIgnoreCase);

        var companies = finCompanies
            .Concat(statsByCompany.Keys.Where(k => !aliased.Contains(k)))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(c => c, StringComparer.OrdinalIgnoreCase)
            .ToList();

        var benchByCompany = new Dictionary<string, Dictionary<string, string>>(StringComparer.OrdinalIgnoreCase);
        foreach (var b in benchCsv)
        {
            var c = Str(b, "Company");
            if (c.Length > 0) benchByCompany[c] = b;
        }

        var benchmark = new List<BenchmarkRow>();
        foreach (var c in companies)
        {
            var latest = quarters.Where(q => q.PeriodType == "Quarterly" && q.Company.Equals(c, StringComparison.OrdinalIgnoreCase) && q.Revenue.Usd is not null)
                .OrderByDescending(q => q.Date, StringComparer.Ordinal).FirstOrDefault();
            Dictionary<string, string>? st = null;
            if (!statsByCompany.TryGetValue(c, out st) && StatsAlias.TryGetValue(c, out var statsName))
                statsByCompany.TryGetValue(statsName, out st);

            // FIX: prefer benchmark.csv (market cap converted with today's FX in the trading currency).
            benchByCompany.TryGetValue(c, out var bm);
            double? mcapOc = bm is not null ? Num(bm, "MarketCap_OC") : st is null ? null : Num(st, "marketCap");
            var mcapCur = bm is not null ? Str(bm, "Currency") : st is null ? null : Str(st, "currency");
            double? mcapUsd = bm is not null ? Num(bm, "MarketCap_USD") : null;
            double? mcapEur = bm is not null ? Num(bm, "MarketCap_EUR") : null;
            // Fallback: statement FX ratio is only valid when trading currency == reporting currency.
            var finCur = st is null ? "" : Str(st, "financialCurrency");
            var sameCur = finCur.Length == 0 || string.Equals(finCur, mcapCur, StringComparison.OrdinalIgnoreCase);
            if (mcapOc is not null && mcapUsd is null)
                mcapUsd = string.Equals(mcapCur, "USD", StringComparison.OrdinalIgnoreCase) ? mcapOc
                    : sameCur && fx.TryGetValue(c, out var rate) && Math.Abs(rate - 1) > 0.001 ? mcapOc * rate : null;
            if (mcapOc is not null && mcapEur is null)
                mcapEur = string.Equals(mcapCur, "EUR", StringComparison.OrdinalIgnoreCase) ? mcapOc
                    : sameCur && fxEur.TryGetValue(c, out var rateEur) && Math.Abs(rateEur - 1) > 0.001 ? mcapOc * rateEur : null;

            var rev = latest?.Revenue.Usd;
            double? opm = rev is > 0 && latest?.OperatingIncome.Usd is { } oi ? Math.Round(oi / rev.Value * 100, 2) : null;
            if (opm is null && st is not null && Num(st, "operatingMargins") is { } om) opm = Math.Round(om * 100, 2);

            benchmark.Add(new BenchmarkRow(c, latest?.Date, mcapUsd, mcapEur, mcapOc, mcapCur, rev, opm,
                bm is not null ? Str(bm, "Symbol") : st is null ? null : Str(st, "symbol"),
                bm is not null ? Num(bm, "CurrentPrice") : st is null ? null : Num(st, "currentPrice")));
        }

        var profiles = new Dictionary<string, ProfileRow>(StringComparer.OrdinalIgnoreCase);
        foreach (var c in companies)
        {
            Dictionary<string, string>? st = null;
            if (!statsByCompany.TryGetValue(c, out st) && StatsAlias.TryGetValue(c, out var statsName))
                statsByCompany.TryGetValue(statsName, out st);
            if (st is null) continue;
            var street = string.Join(", ", new[] { Str(st, "address1"), Str(st, "address2") }.Where(x => x.Length > 0));
            var full = string.Join(", ", new[] { street, Str(st, "city"), Str(st, "state"), Str(st, "zip"), Str(st, "country") }
                .Where(x => x.Length > 0));
            var summary = Str(st, "longBusinessSummary");
            profiles[c] = new ProfileRow(true, c, Str(st, "country"), Str(st, "city"), full,
                Str(st, "industryDisp", "industry"), Str(st, "phone"), Str(st, "website"), Str(st, "symbol"),
                summary.Length > 0 ? summary : null);
        }

        _log.LogInformation("Loaded {Q} period rows for {C} companies", quarters.Count, companies.Count);
        return new Snapshot(companies, quarters, benchmark, BuildStatement(finPl), BuildStatement(bs), profiles);
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
