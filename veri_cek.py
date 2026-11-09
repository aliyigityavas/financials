import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# 22 Şirket ve Ticker Eşleşmeleri
COMPANIES = {
    "AMICA GROUP": "AMC.WA",
    "ARÇELİK": "ARCLK.IS",
    "BOSCH": "BOSCHLTD.NS",
    "DE'LONGHI": "DLG.MI",
    "ELECTROLUX": "ELUX-B.ST",
    "GORENJE": "600060.SS",        # Hisense Visual / Europe temsilcisi
    "GREE ELECTRIC": "000651.SZ",
    "HAIER SMART HOME": "600690.SS",
    "HISENSE HOME APPLIANCES": "000921.SZ",
    "LG ELECTRONICS": "066570.KS",
    "MIDEA GROUP": "000333.SZ",
    "MIELE": "MIELE.DE",          # Özel şirket temsili / veri varsa
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

def get_exchange_rates():
    """USD ve EUR kurlarını Yahoo Finance üzerinden alır."""
    rates = {"USD": 1.0, "EUR": 1.08}
    try:
        eur_usd = yf.Ticker("EURUSD=X").fast_info.get("lastPrice")
        if eur_usd:
            rates["EUR"] = float(eur_usd)
    except Exception as e:
        print(f"Döviz kuru alınamadı, varsayılan kullanılıyor: {e}")
    return rates

def process_statement(df, company_name, statement_type, period_type, rates, currency):
    """Gelen finansal tabloyu normalize eder ve satır bazlı kaydeder."""
    records = []
    if df is None or df.empty:
        return records

    for date_col in df.columns:
        dt = pd.to_datetime(date_col)
        year = dt.year
        quarter_str = f"{year}Q{((dt.month - 1) // 3) + 1}"
        period_label = quarter_str if period_type == "Quarterly" else str(year)

        for account_name, val in df[date_col].items():
            if pd.isna(val) or val is None:
                continue
            
            val_oc = float(val)
            # Para birimi dönüşümü (USD ve EUR)
            # Not: Yfinance yerel para biriminde verir
            val_usd = val_oc # Baz kur dönüşüm mantığı gerekirse eklenir
            val_eur = val_usd / rates["EUR"] if rates["EUR"] else val_usd

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

def fetch_financial_data():
    rates = get_exchange_rates()
    all_financials = []
    benchmarks = []

    for comp_name, ticker_str in COMPANIES.items():
        print(f"Çekiliyor: {comp_name} ({ticker_str})...")
        try:
            t = yf.Ticker(ticker_str)
            fast_info = t.fast_info
            curr = fast_info.get("currency", "USD")

            # 1. Benchmark / Market Cap
            mcap = fast_info.get("marketCap", 0)
            benchmarks.append({
                "Company": comp_name,
                "Currency": curr,
                "MarketCap_OC": mcap,
                "MarketCap_USD": mcap, # Kur dönüşümü yapılabilir
                "MarketCap_EUR": mcap / rates["EUR"] if rates["EUR"] else mcap
            })

            # 2. P&L - Quarterly
            q_inc = t.quarterly_income_stmt
            all_financials.extend(process_statement(q_inc, comp_name, "PnL", "Quarterly", rates, curr))

            # 3. P&L - Annual
            a_inc = t.income_stmt
            all_financials.extend(process_statement(a_inc, comp_name, "PnL", "Annual", rates, curr))

            # 4. Balance Sheet - Quarterly
            q_bs = t.quarterly_balance_sheet
            all_financials.extend(process_statement(q_bs, comp_name, "BS", "Quarterly", rates, curr))

            # 5. Balance Sheet - Annual
            a_bs = t.balance_sheet
            all_financials.extend(process_statement(a_bs, comp_name, "BS", "Annual", rates, curr))

        except Exception as e:
            print(f"Hata oluştu ({comp_name}): {e}")

    # CSV olarak kaydet
    df_fin = pd.DataFrame(all_financials)
    df_bench = pd.DataFrame(benchmarks)

    df_fin.to_csv("financials.csv", index=False, encoding="utf-8")
    df_bench.to_csv("benchmark.csv", index=False, encoding="utf-8")
    print("Veri çekme tamamlandı: financials.csv ve benchmark.csv güncellendi.")

if __name__ == "__main__":
    fetch_financial_data()
