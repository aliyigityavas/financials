import yfinance as yf
import pandas as pd
import numpy as np
import re
from datetime import datetime

# Toplanamayan satırlar (oran / adet): YTD'de son mevcut çeyreğin değeri alınır
NON_ADDITIVE = re.compile(r"tax rate|shares|share issued|\beps\b", re.IGNORECASE)

# 22 Şirket ve Ticker Eşleşmeleri
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
    "XIAOMI": "1810.HK"
}

# Standart P&L Hesap Sıralaması
ACCOUNT_ORDER = {
    "Total Revenue": 1,
    "Operating Revenue": 2,
    "Cost Of Revenue": 3,
    "Gross Profit": 4,
    "Selling General And Administration": 5,
    "Research And Development": 6,
    "Operating Expense": 7,
    "Operating Income": 8,
    "EBIT": 9,
    "EBITDA": 10,
    "Net Non Operating Interest Income Expense": 11,
    "Other Income Expense": 12,
    "Pretax Income": 13,
    "Tax Provision": 14,
    "Net Income Common Stockholders": 15,
    "Net Income": 16
}

# --- KUR MOTORU ---

# API isteklerini minimize etmek için tarihsel kur önbelleği
HISTORICAL_RATE_CACHE = {}

def get_historical_close(ticker, date_obj):
    """Belirli bir tarihteki kapanış kurunu Yahoo Finance history üzerinden çeker."""
    date_str = date_obj.strftime("%Y-%m-%d")
    cache_key = (ticker, date_str)
    
    if cache_key in HISTORICAL_RATE_CACHE:
        return HISTORICAL_RATE_CACHE[cache_key]
        
    # Hafta sonu/tatil ihtimaline karşı 5 gün öncesine kadar tarama aralığı
    start_date = (date_obj - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    end_date = (date_obj + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    
    try:
        hist = yf.Ticker(ticker).history(start=start_date, end=end_date)
        if not hist.empty:
            hist.index = hist.index.tz_localize(None)
            available_dates = hist[hist.index <= date_obj]
            if not available_dates.empty:
                rate = float(available_dates.iloc[-1]["Close"])
                HISTORICAL_RATE_CACHE[cache_key] = rate
                return rate
    except Exception:
        pass
        
    HISTORICAL_RATE_CACHE[cache_key] = None
    return None

def get_historical_usd_rate(currency, date_obj):
    """Bir para biriminin ilgili tarihteki USD karşılığını getirir."""
    curr = str(currency).upper().strip()
    if curr == "USD":
        return 1.0
        
    # 1. Doğrudan Parite (Örn: TRYUSD=X, EURUSD=X)
    rate = get_historical_close(f"{curr}USD=X", date_obj)
    if rate:
        return rate
        
    # 2. Ters Parite (Örn: USDTRY=X)
    inv_rate = get_historical_close(f"USD{curr}=X", date_obj)
    if inv_rate and inv_rate > 0:
        return 1.0 / inv_rate
        
    print(f"Uyarı: {curr} için {date_obj.strftime('%Y-%m-%d')} tarihli kur bulunamadı.")
    return 1.0 # Kesinti anında fallback

def get_current_usd_rate(currency):
    """Market Cap (güncel piyasa değeri) için anlık canlı kuru çeker."""
    curr = str(currency).upper().strip()
    if curr == "USD":
        return 1.0
    try:
        rate = yf.Ticker(f"{curr}USD=X").fast_info.get("lastPrice")
        if rate: return float(rate)
        
        inv_rate = yf.Ticker(f"USD{curr}=X").fast_info.get("lastPrice")
        if inv_rate: return 1.0 / float(inv_rate)
    except:
        pass
    return 1.0

# --- VERİ İŞLEME ---

def process_statement(df, company_name, statement_type, period_type, currency):
    """Gelen finansal tabloyu normalize eder ve satır bazlı kaydeder."""
    records = []
    if df is None or df.empty:
        return records

    for date_col in df.columns:
        dt = pd.to_datetime(date_col)
        year = dt.year
        quarter_str = f"{year}Q{((dt.month - 1) // 3) + 1}"
        period_label = quarter_str if period_type == "Quarterly" else str(year)

        # O çeyreğin kapanış tarihindeki kur değerleri
        usd_rate = get_historical_usd_rate(currency, dt)
        eur_usd_rate = get_historical_usd_rate("EUR", dt)

        for account_name, val in df[date_col].items():
            if pd.isna(val) or val is None:
                continue
            
            val_oc = float(val)
            # Tarihsel Kur Çarpımı
            val_usd = val_oc * usd_rate
            val_eur = val_usd / eur_usd_rate if eur_usd_rate else val_usd

            order = ACCOUNT_ORDER.get(str(account_name).strip(), 99)

            records.append({
                "Company": company_name,
                "Statement_Type": statement_type,   # PnL / BS
                "Period_Type": period_type,         # Quarterly / Annual
                "Period": period_label,             # 2026Q3 veya 2025
                "Date": dt.strftime("%Y-%m-%d"),
                "Year": year,
                "Quarter": quarter_str,
                "Account": str(account_name).strip(),
                "Order": order,
                "Currency_OC": currency,
                "Value_OC": val_oc,
                "Value_USD": val_usd,
                "Value_EUR": val_eur
            })
    return records


def add_ytd_rows(df):
    """Her şirket / tablo / yıl / hesap için çeyrek verilerinden YTD satırları üretir (Period_Type = "YTD").

    PnL: yılın başından o yıldaki son mevcut çeyreğe kadar mevcut çeyreklerin kümülatif toplamı.
    BS : bakiye (stok) olduğu için toplanmaz; son mevcut çeyreğin değeri alınır.
    Eksik çeyrekler atlanır (mevcut olanlar toplanır); hata durumunda orijinal veri korunur.
    """
    try:
        if df is None or df.empty or "Period_Type" not in df.columns:
            return df
        q = df[df["Period_Type"] == "Quarterly"].copy()
        if q.empty:
            return df

        q["Year"] = pd.to_numeric(q["Year"], errors="coerce")
        q["Date_dt"] = pd.to_datetime(q["Date"], errors="coerce")
        q = q.dropna(subset=["Year", "Date_dt"])
        q["Year"] = q["Year"].astype(int)
        value_cols = ["Value_OC", "Value_USD", "Value_EUR"]
        for col in value_cols:
            q[col] = pd.to_numeric(q[col], errors="coerce")

        out = []
        for (company, stmt, year), grp in q.groupby(["Company", "Statement_Type", "Year"]):
            latest_date = grp["Date_dt"].max()
            latest_quarter = grp.loc[grp["Date_dt"] == latest_date, "Quarter"].iloc[0]
            for account, acc in grp.groupby("Account"):
                acc = acc.sort_values("Date_dt")
                ref = acc.iloc[-1]
                if stmt == "BS" or NON_ADDITIVE.search(str(account)):
                    vals = {c: ref[c] for c in value_cols}
                else:
                    vals = {c: acc[c].sum(min_count=1) for c in value_cols}
                if all(pd.isna(v) for v in vals.values()):
                    continue
                out.append({
                    "Company": company,
                    "Statement_Type": stmt,
                    "Period_Type": "YTD",
                    "Period": f"{latest_quarter} YTD",
                    "Date": latest_date.strftime("%Y-%m-%d"),
                    "Year": int(year),
                    "Quarter": latest_quarter,
                    "Account": account,
                    "Order": ref["Order"],
                    "Currency_OC": ref["Currency_OC"],
                    "Value_OC": None if pd.isna(vals["Value_OC"]) else float(vals["Value_OC"]),
                    "Value_USD": None if pd.isna(vals["Value_USD"]) else float(vals["Value_USD"]),
                    "Value_EUR": None if pd.isna(vals["Value_EUR"]) else float(vals["Value_EUR"]),
                })
        if not out:
            return df
        ytd = pd.DataFrame(out, columns=list(df.columns))
        return pd.concat([df[df["Period_Type"] != "YTD"], ytd], ignore_index=True)
    except Exception as e:
        print(f"Uyarı: YTD hesaplanamadı, YTD satırları eklenmeden devam ediliyor: {e}")
        return df


def fetch_financial_data():
    all_financials = []
    benchmarks = []

    for comp_name, ticker_str in COMPANIES.items():
        print(f"Çekiliyor: {comp_name} ({ticker_str})...")
        try:
            t = yf.Ticker(ticker_str)
            fast_info = t.fast_info
            curr = fast_info.get("currency", "USD")

            # 1. Benchmark / Market Cap (Güncel)
            mcap = fast_info.get("marketCap", 0)
            curr_usd_rate = get_current_usd_rate(curr)
            curr_eur_rate = get_current_usd_rate("EUR")
            
            mcap_usd = mcap * curr_usd_rate
            mcap_eur = mcap_usd / curr_eur_rate if curr_eur_rate else mcap_usd

            benchmarks.append({
                "Company": comp_name,
                "Currency": curr,
                "MarketCap_OC": mcap,
                "MarketCap_USD": mcap_usd,
                "MarketCap_EUR": mcap_eur
            })

            # 2. P&L - Quarterly
            q_inc = t.quarterly_income_stmt
            all_financials.extend(process_statement(q_inc, comp_name, "PnL", "Quarterly", curr))

            # 3. P&L - Annual
            a_inc = t.income_stmt
            all_financials.extend(process_statement(a_inc, comp_name, "PnL", "Annual", curr))

            # 4. Balance Sheet - Quarterly
            q_bs = t.quarterly_balance_sheet
            all_financials.extend(process_statement(q_bs, comp_name, "BS", "Quarterly", curr))

            # 5. Balance Sheet - Annual
            a_bs = t.balance_sheet
            all_financials.extend(process_statement(a_bs, comp_name, "BS", "Annual", curr))

        except Exception as e:
            print(f"Hata oluştu ({comp_name}): {e}")

    # CSV olarak kaydet
    df_fin = add_ytd_rows(pd.DataFrame(all_financials))
    df_bench = pd.DataFrame(benchmarks)

    df_fin.to_csv("financials.csv", index=False, encoding="utf-8")
    df_bench.to_csv("benchmark.csv", index=False, encoding="utf-8")
    print("Veri çekme tamamlandı: financials.csv ve benchmark.csv güncellendi.")

if __name__ == "__main__":
    fetch_financial_data()
