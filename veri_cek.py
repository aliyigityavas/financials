import yfinance as yf
import pandas as pd
from datetime import datetime

COMPANIES = {
    "AMICA GROUP": "AMC.WA", "ARÇELİK": "ARCLK.IS", "BOSCH": "BOSCHLTD.NS",
    "DE'LONGHI": "DLG.MI", "ELECTROLUX": "ELUX-B.ST", "GORENJE": "600060.SS",
    "GREE ELECTRIC": "000651.SZ", "HAIER SMART HOME": "600690.SS",
    "HISENSE HOME APPLIANCES": "000921.SZ", "LG ELECTRONICS": "066570.KS",
    "MIDEA GROUP": "000333.SZ", "MIELE": "MIELE.DE", "PANASONIC": "6752.T",
    "PHILIPS": "PHIA.AS", "SAMSUNG ELECTRONICS": "005930.KS", "SEB GROUP": "SK.PA",
    "SHARP": "6753.T", "SMEG": "SMEG.MI", "TCL ELECTRONICS": "1070.HK",
    "VESTEL": "VESBE.IS", "WHIRLPOOL CORPORATION": "WHR", "XIAOMI": "1810.HK"
}

ACCOUNT_ORDER = {
    "Total Revenue": 1, "Operating Revenue": 2, "Cost Of Revenue": 3,
    "Gross Profit": 4, "Selling General And Administration": 5,
    "Research And Development": 6, "Operating Expense": 7,
    "Operating Income": 8, "EBIT": 9, "EBITDA": 10,
    "Net Non Operating Interest Income Expense": 11,
    "Other Income Expense": 12, "Pretax Income": 13,
    "Tax Provision": 14, "Net Income Common Stockholders": 15, "Net Income": 16
}

FX_CACHE = {}

def get_historical_usd_rate(currency, date_obj):
    curr = str(currency).upper().strip()
    if curr == "USD": return 1.0
    
    date_str = date_obj.strftime("%Y-%m-%d")
    cache_key = (curr, date_str)
    if cache_key in FX_CACHE: return FX_CACHE[cache_key]

    start_d = (date_obj - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    end_d = (date_obj + pd.Timedelta(days=2)).strftime("%Y-%m-%d")
    
    rate = 1.0
    try:
        hist = yf.Ticker(f"USD{curr}=X").history(start=start_d, end=end_d)
        if not hist.empty:
            hist.index = hist.index.tz_localize(None)
            valid = hist[hist.index <= date_obj]
            if not valid.empty:
                val = float(valid.iloc[-1]["Close"])
                if val > 0: rate = 1.0 / val
        else:
            hist2 = yf.Ticker(f"{curr}USD=X").history(start=start_d, end=end_d)
            if not hist2.empty:
                hist2.index = hist2.index.tz_localize(None)
                valid2 = hist2[hist2.index <= date_obj]
                if not valid2.empty:
                    rate = float(valid2.iloc[-1]["Close"])
    except:
        pass
        
    FX_CACHE[cache_key] = rate
    return rate

def get_current_usd_rate(currency):
    curr = str(currency).upper().strip()
    if curr == "USD": return 1.0
    try:
        inv = yf.Ticker(f"USD{curr}=X").fast_info.get("lastPrice")
        if inv: return 1.0 / float(inv)
        dr = yf.Ticker(f"{curr}USD=X").fast_info.get("lastPrice")
        if dr: return float(dr)
    except:
        pass
    return 1.0

def process_statement(df, company_name, statement_type, period_type, currency):
    records = []
    if df is None or df.empty: return records

    for date_col in df.columns:
        dt = pd.to_datetime(date_col)
        year = dt.year
        quarter_str = f"{year}Q{((dt.month - 1) // 3) + 1}"
        period_label = quarter_str if period_type == "Quarterly" else str(year)
        
        usd_rate = get_historical_usd_rate(currency, dt)
        eur_usd_rate = get_historical_usd_rate("EUR", dt)

        for account_name, val in df[date_col].items():
            if pd.isna(val) or val is None: continue
            
            val_oc = float(val)
            val_usd = val_oc * usd_rate
            val_eur = val_usd / eur_usd_rate if eur_usd_rate else val_usd
            order = ACCOUNT_ORDER.get(str(account_name).strip(), 99)

            records.append({
                "Company": company_name, "Statement_Type": statement_type,
                "Period_Type": period_type, "Period": period_label,
                "Date": dt.strftime("%Y-%m-%d"), "Year": year, "Quarter": quarter_str,
                "Account": str(account_name).strip(), "Order": order,
                "Currency_OC": currency, "Value_OC": val_oc,
                "Value_USD": val_usd, "Value_EUR": val_eur
            })
    return records

def generate_ytd_records(df_quarterly):
    ytd_records = []
    grouped = df_quarterly.groupby(["Company", "Statement_Type", "Year", "Currency_OC", "Account", "Order"])
    
    for name, group in grouped:
        group = group.sort_values("Date")
        latest_row = group.iloc[-1]
        
        comp, stmt, yr, curr, acc, ordr = name
        latest_q = latest_row["Quarter"]
        
        if stmt == "PnL":
            # Gelir Tablosu: Çeyrekleri topla
            val_oc = group["Value_OC"].sum()
            val_usd = group["Value_USD"].sum()
            val_eur = group["Value_EUR"].sum()
        else:
            # Bilanço: Sadece son çeyreğin değerini al
            val_oc = latest_row["Value_OC"]
            val_usd = latest_row["Value_USD"]
            val_eur = latest_row["Value_EUR"]
            
        ytd_records.append({
            "Company": comp, "Statement_Type": stmt, "Period_Type": "YTD",
            "Period": f"{latest_q} YTD", "Date": latest_row["Date"],
            "Year": yr, "Quarter": latest_q, "Account": acc, "Order": ordr,
            "Currency_OC": curr, "Value_OC": val_oc, "Value_USD": val_usd, "Value_EUR": val_eur
        })
    return pd.DataFrame(ytd_records)

def fetch_financial_data():
    all_financials = []
    benchmarks = []

    for comp_name, ticker_str in COMPANIES.items():
        print(f"İşleniyor: {comp_name}...")
        try:
            t = yf.Ticker(ticker_str)
            curr = t.fast_info.get("currency", "USD")
            
            # Benchmark / Market Cap
            mcap = t.fast_info.get("marketCap", 0)
            c_usd = get_current_usd_rate(curr)
            c_eur = get_current_usd_rate("EUR")
            benchmarks.append({
                "Company": comp_name, "Currency": curr, "MarketCap_OC": mcap,
                "MarketCap_USD": mcap * c_usd,
                "MarketCap_EUR": (mcap * c_usd) / c_eur if c_eur else (mcap * c_usd)
            })

            # Tabloları Çek
            all_financials.extend(process_statement(t.quarterly_income_stmt, comp_name, "PnL", "Quarterly", curr))
            all_financials.extend(process_statement(t.income_stmt, comp_name, "PnL", "Annual", curr))
            all_financials.extend(process_statement(t.quarterly_balance_sheet, comp_name, "BS", "Quarterly", curr))
            all_financials.extend(process_statement(t.balance_sheet, comp_name, "BS", "Annual", curr))
        except Exception as e:
            print(f"Hata ({comp_name}): {e}")

    df_fin = pd.DataFrame(all_financials)
    
    # YTD Hesaplama ve Ekleme
    df_q = df_fin[df_fin["Period_Type"] == "Quarterly"]
    if not df_q.empty:
        df_ytd = generate_ytd_records(df_q)
        df_fin = pd.concat([df_fin, df_ytd], ignore_index=True)

    df_fin.to_csv("financials.csv", index=False, encoding="utf-8")
    pd.DataFrame(benchmarks).to_csv("benchmark.csv", index=False, encoding="utf-8")
    print("İşlem tamamlandı. CSV'ler hazır.")

if __name__ == "__main__":
    fetch_financial_data()
