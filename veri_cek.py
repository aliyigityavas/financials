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
    "Vestel": "VESBE.IS",
    "Whirlpool": "WHR"
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
        return df_melted
    return pd.DataFrame()

for ad, sembol in sirketler.items():
    hisse = yf.Ticker(sembol)
    para_birimi = hisse.info.get('financialCurrency', 'Bilinmiyor')
    
    # 1. Historical Data
    hist = hisse.history(period="max")
    if not hist.empty:
        hist['Company'] = ad
        hist['Currency'] = para_birimi
        hist_list.append(hist)
        
    # 2. Financials, Balance Sheet, Cash Flow (Yıllık yapıldı)
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

# Verileri birleştir ve CSV olarak kaydet
if hist_list: pd.concat(hist_list).to_csv("historical_data.csv")
if fin_list: pd.concat(fin_list, ignore_index=True).to_csv("financials.csv", index=False)
if bs_list: pd.concat(bs_list, ignore_index=True).to_csv("balance_sheet.csv", index=False)
if cf_list: pd.concat(cf_list, ignore_index=True).to_csv("cash_flow.csv", index=False)
if stat_list: pd.concat(stat_list, ignore_index=True).to_csv("statistics.csv", index=False)
