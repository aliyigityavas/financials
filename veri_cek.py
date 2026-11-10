import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

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

def process_table(df, company_name, statement_type, period_type, currency):
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

def add_ytd_records(df_records):
    if df_records.empty: return df_records
    df_q = df_records[df_records["Period_Type"] == "Quarterly"]
    if df_q.empty: return df_records

    ytd_list = []
    grouped = df_q.groupby(["Company", "Statement_Type", "Year", "Currency_OC", "Account", "Order"])
    for name, group in grouped:
        group = group.sort_values("Date")
        latest = group.iloc[-1]
        comp, stmt, yr, curr, acc, ordr = name
        l_quarter = latest["Quarter"]

        if stmt in ["PnL", "CashFlow"]:
            v_oc = group["Value_OC"].sum()
            v_usd = group["Value_USD"].sum()
            v_eur = group["Value_EUR"].sum()
        else:
            v_oc = latest["Value_OC"]
            v_usd = latest["Value_USD"]
            v_eur = latest["Value_EUR"]

        ytd_list.append({
            "Company": comp, "Statement_Type": stmt, "Period_Type": "YTD",
            "Period": f"{l_quarter} YTD", "Date": latest["Date"],
            "Year": yr, "Quarter": l_quarter, "Account": acc, "Order": ordr,
            "Currency_OC": curr, "Value_OC": v_oc, "Value_USD": v_usd, "Value_EUR": v_eur
        })
    df_ytd = pd.DataFrame(ytd_list)
    return pd.concat([df_records, df_ytd], ignore_index=True)

def main():
    pnl_records = []
    bs_records = []
    cf_records = []
    benchmarks = []
    statistics = []
    hist_prices = []

    c_eur_rate = get_current_usd_rate("EUR")

    for comp, ticker_str in COMPANIES.items():
        print(f"Çekiliyor: {comp} ({ticker_str})...")
        try:
            t = yf.Ticker(ticker_str)
            curr = t.fast_info.get("currency", "USD")
            c_usd_rate = get_current_usd_rate(curr)
            
            # 1. Benchmark & Market Cap
            mcap = t.fast_info.get("marketCap", 0) or 0
            mcap_usd = mcap * c_usd_rate
            mcap_eur = mcap_usd / c_eur_rate if c_eur_rate else mcap_usd
            benchmarks.append({
                "Company": comp, "Currency": curr, "MarketCap_OC": mcap,
                "MarketCap_USD": mcap_usd, "MarketCap_EUR": mcap_eur
            })

            # 2. Company Info (Statistics)
            try:
                info = t.info
                statistics.append({
                    "Company": comp,
                    "address1": info.get("address1", ""),
                    "address2": info.get("address2", ""),
                    "city": info.get("city", ""),
                    "country": info.get("country", ""),
                    "phone": info.get("phone", ""),
                    "fax": info.get("fax", ""),
                    "website": info.get("website", ""),
                    "industry": info.get("industry", "")
                })
            except Exception:
                pass

            # 3. Income Statement (PnL)
            pnl_records.extend(process_table(t.quarterly_income_stmt, comp, "PnL", "Quarterly", curr))
            pnl_records.extend(process_table(t.income_stmt, comp, "PnL", "Annual", curr))

            # 4. Balance Sheet
            bs_records.extend(process_table(t.quarterly_balance_sheet, comp, "BS", "Quarterly", curr))
            bs_records.extend(process_table(t.balance_sheet, comp, "BS", "Annual", curr))

            # 5. Cash Flow
            cf_records.extend(process_table(t.quarterly_cashflow, comp, "CashFlow", "Quarterly", curr))
            cf_records.extend(process_table(t.cashflow, comp, "CashFlow", "Annual", curr))

            # 6. Historical Prices (Son 1 Yıl)
            try:
                h = t.history(period="1y")
                for dt_idx, row in h.iterrows():
                    hist_prices.append({
                        "Company": comp, "Date": dt_idx.strftime("%Y-%m-%d"),
                        "Close": float(row["Close"]), "Volume": float(row["Volume"])
                    })
            except Exception:
                pass

        except Exception as e:
            print(f"Hata ({comp}): {e}")

    # DataFrame'lere Çevir ve YTD Ekle
    df_pnl = add_ytd_records(pd.DataFrame(pnl_records))
    df_bs = add_ytd_records(pd.DataFrame(bs_records))
    df_cf = add_ytd_records(pd.DataFrame(cf_records))

    # Tüm Finansalları Tek Bir Dosyada da Birleştir
    df_all_fin = pd.concat([df_pnl, df_bs, df_cf], ignore_index=True)

    # 6 Dosyayı da Yaz (GitHub'daki eski dosyaların tümü güncellenecek)
    df_all_fin.to_csv("financials.csv", index=False, encoding="utf-8")
    df_bs.to_csv("balance_sheet.csv", index=False, encoding="utf-8")
    df_cf.to_csv("cash_flow.csv", index=False, encoding="utf-8")
    pd.DataFrame(benchmarks).to_csv("benchmark.csv", index=False, encoding="utf-8")
    pd.DataFrame(statistics).to_csv("statistics.csv", index=False, encoding="utf-8")
    pd.DataFrame(hist_prices).to_csv("historical_data.csv", index=False, encoding="utf-8")

    print("İşlem tamam: Tüm 6 CSV dosyası başarıyla güncellendi.")

if __name__ == "__main__":
    main()
