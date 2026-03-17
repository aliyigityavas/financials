import yfinance as yf
import pandas as pd
import hashlib
import warnings
warnings.filterwarnings('ignore')

sirketler = {
    "HAIER GROUP": "600690.SS", "MIDEA GROUP": "000333.SZ", "BEKO GROUP": "ARCLK.IS",
    "SAMSUNG GROUP": "005930.KS", "LG ELECTRONICS": "066570.KS", "ELECTROLUX GROUP": "ELUX-B.ST",
    "HISENSE GROUP": "0921.HK", "WHIRLPOOL CORPORATION": "WHR", "PANASONIC HOLDINGS": "6752.T",
    "GREE ELECTRIC": "000651.SZ", "TCL TECHNOLOGY": "1070.HK", "GROUPE SEB": "SK.PA",
    "DE'LONGHI GROUP": "DLG.MI", "AMICA GROUP": "AMC.WA", "VESTEL GROUP": "VESBE.IS",
    "ROYAL PHILIPS": "PHIA.AS", "BREVILLE GROUP": "BRG.AX", "DAIKIN INDUSTRIES": "6367.T",
    "MITSUBISHI ELECTRIC": "6503.T", "HITACHI LTD": "6501.T", "SHARP CORPORATION": "6753.T",
    "CARRIER GLOBAL": "CARR", "TRANE TECHNOLOGIES": "TT", "JOHNSON CONTROLS": "JCI",
    "VOLTAS LIMITED": "VOLTAS.NS"
}

kur_eslesme = {
    "TRY": "TRYUSD=X", "CNY": "CNYUSD=X", "KRW": "KRWUSD=X",
    "SEK": "SEKUSD=X", "HKD": "HKDUSD=X", "JPY": "JPYUSD=X", 
    "EUR": "EURUSD=X", "PLN": "PLNUSD=X", "AUD": "AUDUSD=X",
    "INR": "INRUSD=X"
}

# Kurları çek ve hazırla
kur_dict = {}
for pb, ticker in kur_eslesme.items():
    k_data = yf.Ticker(ticker).history(period="max")
    if not k_data.empty:
        k_data.index = k_data.index.tz_localize(None)
        kur_dict[ticker] = k_data['Close']

kur_df = pd.DataFrame(kur_dict)
kur_yillik = kur_df.resample('YE').mean()

# Benzersiz ve kalıcı ID üreten fonksiyon
def id_olustur(metin):
    return int(hashlib.md5(str(metin).encode('utf-8')).hexdigest()[:8], 16)

hist_list, fin_list, bs_list, cf_list, stat_list = [], [], [], [], []

def tabloyu_duzenle(df, sirket_adi, para_birimi, tip):
    if df is not None and not df.empty:
        df = df.copy()
        df.index.name = "Metric"
        df['Order'] = range(1, len(df) + 1)
        df = df.reset_index()
        
        # ID kolonunu ekle
        df['Metric_ID'] = df['Metric'].apply(id_olustur)
        
        df_melted = df.melt(id_vars=["Metric_ID", "Metric", "Order"], var_name="Date", value_name="Value")
        df_melted['Company'] = sirket_adi
        df_melted['Currency'] = para_birimi
        df_melted['Value'] = pd.to_numeric(df_melted['Value'], errors='coerce')
        
        usd_degerler = []
        for idx, row in df_melted.iterrows():
            val = row['Value']
            tarih = pd.to_datetime(row['Date'])
            if pd.isna(val):
                usd_degerler.append(None)
                continue
            
            if para_birimi == "USD":
                usd_degerler.append(val)
            elif para_birimi in kur_eslesme:
                ticker = kur_eslesme[para_birimi]
                try:
                    if tip == "gunluk":
                        kur = kur_df[ticker].dropna().asof(tarih)
                    else: 
                        yil_sonu = pd.Timestamp(year=tarih.year, month=12, day=31)
                        kur = kur_yillik[ticker].dropna().asof(yil_sonu)
                    usd_degerler.append(val * kur)
                except:
                    usd_degerler.append(None)
            else:
                usd_degerler.append(None)
                
        df_melted['Value_USD'] = (pd.Series(usd_degerler) / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
        df_melted['Value'] = (df_melted['Value'] / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
        return df_melted
    return pd.DataFrame()

for ad, sembol in sirketler.items():
    hisse = yf.Ticker(sembol)
    para_birimi = hisse.info.get('financialCurrency', 'Bilinmiyor')
    if para_birimi == 'Bilinmiyor' and sembol in ['WHR', 'CARR', 'TT', 'JCI']: 
        para_birimi = 'USD'
    
    # 1. Historical Data
    hist = hisse.history(period="max")
    if not hist.empty:
        if 'Close' in hist.columns:
            hist = hist[['Close']].copy()
            hist = hist.reset_index()
            hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None).dt.date
            hist.rename(columns={'Close': 'Value'}, inplace=True)
            hist['Metric'] = 'Stock'
            hist['Metric_ID'] = id_olustur('Stock')
            hist['Order'] = 1
            hist['Company'] = ad
            hist['Currency'] = para_birimi
            
            usd_degerler = []
            for idx, row in hist.iterrows():
                val = row['Value']
                tarih = pd.to_datetime(row['Date'])
                if para_birimi == "USD":
                    usd_degerler.append(val)
                elif para_birimi in kur_eslesme:
                    ticker = kur_eslesme[para_birimi]
                    try:
                        kur = kur_df[ticker].dropna().asof(tarih)
                        usd_degerler.append(val * kur)
                    except:
                        usd_degerler.append(None)
                else:
                    usd_degerler.append(None)
                    
            hist['Value_USD'] = usd_degerler
            hist['Value'] = hist['Value'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            hist['Value_USD'] = hist['Value_USD'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
            hist = hist[['Date', 'Metric_ID', 'Metric', 'Order', 'Value', 'Value_USD', 'Company', 'Currency']]
            hist_list.append(hist)
        
    # 2. Financials, Balance Sheet, Cash Flow
    fin_list.append(tabloyu_duzenle(hisse.financials, ad, para_birimi, "ortalama"))
    bs_list.append(tabloyu_duzenle(hisse.balance_sheet, ad, para_birimi, "gunluk"))
    cf_list.append(tabloyu_duzenle(hisse.cashflow, ad, para_birimi, "ortalama"))
    
    # 3. Statistics
    try:
        stat = pd.DataFrame([hisse.info])
        stat['Company'] = ad
        stat_list.append(stat)
    except:
        pass

if hist_list: pd.concat(hist_list, ignore_index=True).to_csv("historical_data.csv", index=False)
if fin_list: pd.concat(fin_list, ignore_index=True).to_csv("financials.csv", index=False)
if bs_list: pd.concat(bs_list, ignore_index=True).to_csv("balance_sheet.csv", index=False)
if cf_list: pd.concat(cf_list, ignore_index=True).to_csv("cash_flow.csv", index=False)
if stat_list: pd.concat(stat_list, ignore_index=True).to_csv("statistics.csv", index=False)
