import yfinance as yf
import pandas as pd

sirketler = {
    "Haier": "600690.SS",
    "Midea": "000333.SZ",
    "Beko": "ARCLK.IS",
    "Samsung": "005930.KS",
    "LG": "066570.KS",
    "Electrolux": "ELUX-B.ST",
    "Hisense": "0921.HK",
    "Whirlpool": "WHR",
    "Panasonic": "6752.T",
    "Gree": "000651.SZ",
    "TCL": "1070.HK",
    "Groupe SEB": "SK.PA",
    "De'Longhi": "DLG.MI"
}

hist_list, fin_list, bs_list, cf_list, stat_list = [], [], [], [], []

def tabloyu_duzenle(df, sirket_adi, para_birimi):
    if df is not None and not df.empty:
        df = df.copy()
        df.index.name = "Metric"
        df = df.reset_index()
        df_melted = df.melt(id_vars=["Metric"], var_name="Date", value_name="Value")
        df_melted['Company'] = sirket_adi
        df_melted['Currency'] = para_birimi
        
        df_melted['Value'] = pd.to_numeric(df_melted['Value'], errors='coerce')
        df_melted['Value'] = (df_melted['Value'] / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
        return df_melted
    return pd.DataFrame()

for ad, sembol in sirketler.items():
    hisse = yf.Ticker(sembol)
    para_birimi = hisse.info.get('financialCurrency', 'Bilinmiyor')
    
    # 1. Historical Data
    hist = hisse.history(period="max")
    if not hist.empty:
        hist = hist[['Close']].copy()
        hist = hist.reset_index()
        hist['Date'] = pd.to_datetime(hist['Date']).dt.date
        hist.rename(columns={'Close': 'Value'}, inplace=True)
        hist['Metric'] = 'Stock'
        hist['Company'] = ad
        hist['Currency'] = para_birimi
        hist = hist[['Date', 'Metric', 'Value', 'Company', 'Currency']]
        hist_list.append(hist)
        
    # 2. Financials, Balance Sheet, Cash Flow
    fin_list.append(tabloyu_duzenle(hisse.financials, ad, para_birimi))
    bs_list.append(tabloyu_duzenle(hisse.balance_sheet, ad, para_birimi))
    cf_list.append(tabloyu_duzenle(hisse.cashflow, ad, para_birimi))
    
    # 3. Statistics
    try:
        stat = pd.DataFrame([hisse.info])
        stat['Company'] = ad
        stat_list.append(stat)
    except:
        pass

# CSV olarak kaydet
if hist_list: pd.concat(hist_list, ignore_index=True).to_csv("historical_data.csv", index=False)
if fin_list: pd.concat(fin_list, ignore_index=True).to_csv("financials.csv", index=False)
if bs_list: pd.concat(bs_list, ignore_index=True).to_csv("balance_sheet.csv", index=False)
if cf_list: pd.concat(cf_list, ignore_index=True).to_csv("cash_flow.csv", index=False)
if stat_list: pd.concat(stat_list, ignore_index=True).to_csv("statistics.csv", index=False)
