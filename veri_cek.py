"""
Yahoo Finance veri çekici (düzeltilmiş sürüm).

Önemli düzeltmeler:
  * Finansal tablolar hisse işlem para birimiyle değil, `financialCurrency` ile çevrilir
    (ör. Xiaomi HKD'de işlem görür ama CNY raporlar).
  * Kur bulunamazsa sessizce 1.0 kullanılmaz; USD/EUR değerleri boş bırakılır.
  * Gelir tablosu / nakit akışı dönem ORTALAMA kuruyla, bilanço dönem SONU kuruyla çevrilir.
  * Kurlar her para birimi için tek seferde indirilir (rate-limit ve tutarsızlık azalır).
  * YTD yalnızca Q1..Qn eksiksizse hesaplanır; hisse adedi / vergi oranı toplanmaz.
  * Hisse adedi ve oran gibi parasal olmayan kalemler kura çevrilmez.
  * statistics.csv'ye marketCap, currency, symbol vb. eklendi (Program.cs bunları okuyor).
"""
import time
import yfinance as yf
import pandas as pd
import numpy as np

COMPANIES = {
    "AMICA GROUP": "AMC.WA",
    "ARÇELİK": "ARCLK.IS",
    "BOSCH": "BOSCHLTD.NS",
    "DE'LONGHI": "DLG.MI",
    "ELECTROLUX": "ELUX-B.ST",
    "GORENJE": "600060.SS",
    "GREE ELECTRIC": "000651.SZ",
    "HAIER SMART HOME": "600690.SS",
    "HISENSE HOME APPLIANCES": "000921.SZ",
    "LG ELECTRONICS": "066570.KS",
    "MIDEA GROUP": "000333.SZ",
    "MIELE": "MIELE.DE",
    "PANASONIC": "6752.T",
    "PHILIPS": "PHIA.AS",
    "SAMSUNG ELECTRONICS": "005930.KS",
    "SEB GROUP": "SK.PA",
    "SHARP": "6753.T",
    "SMEG": "SMEG.MI",
    "TCL ELECTRONICS": "1070.HK",
    "VESTEL": "VESBE.IS",
    "WHIRLPOOL CORPORATION": "WHR",
    "XIAOMI": "1810.HK",
}

ACCOUNT_ORDER = {
    "Total Revenue": 1, "Operating Revenue": 2, "Cost Of Revenue": 3,
    "Gross Profit": 4, "Selling General And Administration": 5,
    "Research And Development": 6, "Operating Expense": 7,
    "Operating Income": 8, "EBIT": 9, "EBITDA": 10,
    "Net Non Operating Interest Income Expense": 11,
    "Other Income Expense": 12, "Pretax Income": 13,
    "Tax Provision": 14, "Net Income Common Stockholders": 15, "Net Income": 16,
}

# Kura çevrilmeyecek kalemler (adet / oran)
def is_non_monetary(account):
    a = account.lower()
    return "shares" in a or "share issued" in a or "tax rate" in a

def is_ratio(account):
    return "tax rate" in account.lower()

def is_eps(account):
    return " eps" in f" {account.lower()}"

HIST_START = "2018-01-01"
FX_SERIES = {}   # currency -> pd.Series (1 birim yabancı para = X USD), günlük


def _download_close(symbol):
    for attempt in range(3):
        try:
            h = yf.Ticker(symbol).history(start=HIST_START, auto_adjust=False)
            if h is not None and not h.empty:
                h.index = pd.to_datetime(h.index).tz_localize(None).normalize()
                s = h["Close"].astype(float)
                return s[s > 0]
        except Exception as e:
            print(f"   FX indirme hatası {symbol}: {e}")
        time.sleep(1 + attempt)
    return None


def fx_series(currency):
    """1 birim `currency` kaç USD eder (günlük seri). Bulunamazsa None."""
    curr = str(currency or "").upper().strip()
    if curr in FX_SERIES:
        return FX_SERIES[curr]
    if curr == "USD":
        s = None
    else:
        s = _download_close(f"{curr}USD=X")
        if s is None:
            inv = _download_close(f"USD{curr}=X")
            if inv is None:
                inv = _download_close(f"{curr}=X")   # Yahoo'nun USD/XXX kısa formatı
            s = (1.0 / inv) if inv is not None else None
        if s is None:
            print(f"   UYARI: {curr} kuru bulunamadı, USD/EUR değerleri boş kalacak.")
    FX_SERIES[curr] = s
    return s


def spot_rate(currency, date):
    if str(currency).upper() == "USD":
        return 1.0
    s = fx_series(currency)
    if s is None:
        return None
    v = s.asof(pd.Timestamp(date))
    return float(v) if pd.notna(v) else None


def avg_rate(currency, start, end):
    if str(currency).upper() == "USD":
        return 1.0
    s = fx_series(currency)
    if s is None:
        return None
    w = s[(s.index > pd.Timestamp(start)) & (s.index <= pd.Timestamp(end))]
    return float(w.mean()) if not w.empty else spot_rate(currency, end)


def process_table(df, company_name, statement_type, period_type, currency):
    records = []
    if df is None or df.empty:
        return records

    df = df.loc[:, ~df.columns.duplicated()]
    for date_col in df.columns:
        dt = pd.Timestamp(date_col).tz_localize(None) if pd.Timestamp(date_col).tzinfo else pd.Timestamp(date_col)
        year = dt.year
        quarter_str = f"{year}Q{((dt.month - 1) // 3) + 1}"
        period_label = quarter_str if period_type == "Quarterly" else str(year)

        if statement_type == "BS":
            r_oc = spot_rate(currency, dt)
            r_eur = spot_rate("EUR", dt)
        else:
            months = 3 if period_type == "Quarterly" else 12
            start = dt - pd.DateOffset(months=months)
            r_oc = avg_rate(currency, start, dt)
            r_eur = avg_rate("EUR", start, dt)

        for account_name, val in df[date_col].items():
            if val is None or pd.isna(val):
                continue
            acc = str(account_name).strip()
            val_oc = float(val)
            if is_non_monetary(acc):
                val_usd = val_eur = val_oc
            else:
                val_usd = val_oc * r_oc if r_oc else np.nan
                val_eur = val_usd / r_eur if (r_eur and pd.notna(val_usd)) else np.nan

            records.append({
                "Company": company_name, "Statement_Type": statement_type,
                "Period_Type": period_type, "Period": period_label,
                "Date": dt.strftime("%Y-%m-%d"), "Year": year, "Quarter": quarter_str,
                "Account": acc, "Order": ACCOUNT_ORDER.get(acc, 99),
                "Currency_OC": currency, "Value_OC": val_oc,
                "Value_USD": val_usd, "Value_EUR": val_eur,
            })
    return records


def add_ytd_records(df_records):
    if df_records.empty:
        return df_records
    df_q = df_records[df_records["Period_Type"] == "Quarterly"].copy()
    if df_q.empty:
        return df_records
    df_q["QN"] = df_q["Quarter"].str[-1].astype(int)

    ytd_list = []
    for (comp, stmt, yr, curr, acc), group in df_q.groupby(
            ["Company", "Statement_Type", "Year", "Currency_OC", "Account"]):
        group = group.sort_values("Date").drop_duplicates("QN", keep="last")
        qns = list(group["QN"])
        # Sadece Q1'den başlayan kesintisiz çeyrekler için YTD üret
        if not qns or qns != list(range(1, len(qns) + 1)):
            continue
        latest = group.iloc[-1]
        if stmt in ("PnL", "CashFlow") and not is_non_monetary(acc):
            v_oc, v_usd, v_eur = (group[c].sum(min_count=len(group)) for c in ("Value_OC", "Value_USD", "Value_EUR"))
        elif is_ratio(acc):
            continue
        else:
            v_oc, v_usd, v_eur = latest["Value_OC"], latest["Value_USD"], latest["Value_EUR"]

        ytd_list.append({
            "Company": comp, "Statement_Type": stmt, "Period_Type": "YTD",
            "Period": f"{latest['Quarter']} YTD", "Date": latest["Date"],
            "Year": yr, "Quarter": latest["Quarter"], "Account": acc, "Order": latest["Order"],
            "Currency_OC": curr, "Value_OC": v_oc, "Value_USD": v_usd, "Value_EUR": v_eur,
        })
    if not ytd_list:
        return df_records
    return pd.concat([df_records, pd.DataFrame(ytd_list)], ignore_index=True)


def safe_info(t):
    for attempt in range(3):
        try:
            info = t.info
            if info:
                return info
        except Exception as e:
            print(f"   info hatası: {e}")
        time.sleep(1 + attempt)
    return {}


def main():
    pnl_records, bs_records, cf_records = [], [], []
    benchmarks, statistics, hist_prices = [], [], []

    today = pd.Timestamp.today().normalize()
    eur_now = spot_rate("EUR", today)

    for comp, ticker_str in COMPANIES.items():
        if not ticker_str:
            print(f"Atlanıyor: {comp} (borsada işlem görmüyor)")
            continue
        print(f"Çekiliyor: {comp} ({ticker_str})...")
        try:
            t = yf.Ticker(ticker_str)
            info = safe_info(t)
            trade_curr = (info.get("currency") or t.fast_info.get("currency") or "USD").upper()
            fin_curr = (info.get("financialCurrency") or trade_curr).upper()
            if fin_curr != trade_curr:
                print(f"   Not: işlem para birimi {trade_curr}, raporlama para birimi {fin_curr}")

            # 1. Benchmark & Market Cap (piyasa değeri işlem para birimindedir)
            mcap = info.get("marketCap") or t.fast_info.get("marketCap") or None
            r_now = spot_rate(trade_curr, today)
            mcap_usd = mcap * r_now if (mcap and r_now) else None
            mcap_eur = mcap_usd / eur_now if (mcap_usd and eur_now) else None
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            benchmarks.append({
                "Company": comp, "Symbol": ticker_str, "Currency": trade_curr,
                "MarketCap_OC": mcap, "MarketCap_USD": mcap_usd, "MarketCap_EUR": mcap_eur,
                "CurrentPrice": price,
            })

            # 2. Company Info (Statistics)
            statistics.append({
                "Company": comp, "symbol": ticker_str,
                "address1": info.get("address1", ""), "address2": info.get("address2", ""),
                "city": info.get("city", ""), "state": info.get("state", ""), "zip": info.get("zip", ""),
                "country": info.get("country", ""), "phone": info.get("phone", ""),
                "fax": info.get("fax", ""), "website": info.get("website", ""),
                "industry": info.get("industry", ""), "industryDisp": info.get("industryDisp", ""),
                "currency": trade_curr, "financialCurrency": fin_curr,
                "marketCap": mcap, "currentPrice": price,
                "operatingMargins": info.get("operatingMargins"),
                "longBusinessSummary": info.get("longBusinessSummary", ""),
            })

            # 3-5. Tablolar: raporlama para birimiyle
            pnl_records.extend(process_table(t.quarterly_income_stmt, comp, "PnL", "Quarterly", fin_curr))
            pnl_records.extend(process_table(t.income_stmt, comp, "PnL", "Annual", fin_curr))
            bs_records.extend(process_table(t.quarterly_balance_sheet, comp, "BS", "Quarterly", fin_curr))
            bs_records.extend(process_table(t.balance_sheet, comp, "BS", "Annual", fin_curr))
            cf_records.extend(process_table(t.quarterly_cashflow, comp, "CashFlow", "Quarterly", fin_curr))
            cf_records.extend(process_table(t.cashflow, comp, "CashFlow", "Annual", fin_curr))

            # 6. Historical Prices (Son 1 Yıl)
            try:
                h = t.history(period="1y")
                for dt_idx, row in h.iterrows():
                    hist_prices.append({
                        "Company": comp, "Date": dt_idx.strftime("%Y-%m-%d"),
                        "Close": float(row["Close"]), "Volume": float(row["Volume"]),
                    })
            except Exception as e:
                print(f"   Fiyat geçmişi alınamadı: {e}")

        except Exception as e:
            print(f"Hata ({comp}): {e}")
        time.sleep(0.5)

    df_pnl = add_ytd_records(pd.DataFrame(pnl_records))
    df_bs = add_ytd_records(pd.DataFrame(bs_records))
    df_cf = add_ytd_records(pd.DataFrame(cf_records))

    df_all_fin = pd.concat([df_pnl, df_bs, df_cf], ignore_index=True)

    df_all_fin.to_csv("financials.csv", index=False, encoding="utf-8")
    df_bs.to_csv("balance_sheet.csv", index=False, encoding="utf-8")
    df_cf.to_csv("cash_flow.csv", index=False, encoding="utf-8")
    pd.DataFrame(benchmarks).to_csv("benchmark.csv", index=False, encoding="utf-8")
    pd.DataFrame(statistics).to_csv("statistics.csv", index=False, encoding="utf-8")
    pd.DataFrame(hist_prices).to_csv("historical_data.csv", index=False, encoding="utf-8")

    print("İşlem tamam: Tüm 6 CSV dosyası başarıyla güncellendi.")


if __name__ == "__main__":
    main()

