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

# 1. Kurları çek ve hazırla
kur_dict = {}
for pb, ticker in kur_eslesme.items():
    k_data = yf.Ticker(ticker).history(period="max")
    if not k_data.empty:
        k_data.index = k_data.index.tz_localize(None)
        kur_dict[ticker] = k_data['Close']

kur_df = pd.DataFrame(kur_dict)
eur_usd_series = kur_df['EURUSD=X'].dropna()

def id_olustur(metin):
    return int(hashlib.md5(str(metin).encode('utf-8')).hexdigest()[:8], 16)

def tabloyu_duzenle(df, sirket_adi, para_birimi, tip, ytd_hesapla=False):
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    df.index.name = "Metric"
    df['Order'] = range(1, len(df) + 1)
    df = df.reset_index()
    df['Metric_ID'] = df['Metric'].apply(id_olustur)
    
    df_melted = df.melt(id_vars=["Metric_ID", "Metric", "Order"], var_name="Date", value_name="Value")
    df_melted['Company'] = sirket_adi
    df_melted['Currency'] = para_birimi
    df_melted['Value'] = pd.to_numeric(df_melted['Value'], errors='coerce')
    df_melted['Date'] = pd.to_datetime(df_melted['Date'])
    
    # YTD Hesaplama (Gelir Tablosu ve Nakit Akışı için)
    if ytd_hesapla:
        df_melted = df_melted.sort_values(by=['Metric', 'Date'])
        df_melted['Year'] = df_melted['Date'].dt.year
        
        # Yıl içi kümülatif toplam
        ytd_df = df_melted.copy()
        ytd_df['Value'] = ytd_df.groupby(['Metric', 'Year'])['Value'].cumsum()
        ytd_df['Metric'] = ytd_df['Metric'] + " (YTD)"
        ytd_df['Metric_ID'] = ytd_df['Metric'].apply(id_olustur)
        ytd_df['Order'] = ytd_df['Order'] + 1000
        
        df_melted = pd.concat([df_melted, ytd_df], ignore_index=True)
        df_melted.drop(columns=['Year'], inplace=True)

    usd_degerler = []
    eur_degerler = []

    for idx, row in df_melted.iterrows():
        val = row['Value']
        tarih = row['Date']
        
        if pd.isna(val):
            usd_degerler.append(None)
            eur_degerler.append(None)
            continue
        
        # USD Dönüşümü
        val_usd = None
        if para_birimi == "USD":
            val_usd = val
        elif para_birimi in kur_eslesme:
            ticker = kur_eslesme[para_birimi]
            try:
                kur = kur_df[ticker].dropna().asof(tarih)
                val_usd = val * kur
            except:
                val_usd = None
                
        # EUR Dönüşümü (EUR = USD / EURUSD)
        val_eur = None
        if val_usd is not None:
            try:
                eur_kur = eur_usd_series.asof(tarih)
                if pd.notna(eur_kur) and eur_kur > 0:
                    val_eur = val_usd / eur_kur
            except:
                val_eur = None

        usd_degerler.append(val_usd)
        eur_degerler.append(val_eur)
        
    df_melted['Date'] = df_melted['Date'].dt.date
    df_melted['Value_USD'] = (pd.Series(usd_degerler) / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
    df_melted['Value_EUR'] = (pd.Series(eur_degerler) / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
    df_melted['Value'] = (df_melted['Value'] / 1000).apply(lambda x: f"{x:.0f}" if pd.notna(x) else "")
    
    # Sütun sırasını garantiye al
    kolonlar = ['Metric_ID', 'Metric', 'Order', 'Date', 'Value', 'Company', 'Currency', 'Value_USD', 'Value_EUR']
    return df_melted[kolonlar]

hist_list, fin_list, bs_list, cf_list, stat_list = [], [], [], [], []

for ad, sembol in sirketler.items():
    hisse = yf.Ticker(sembol)
    para_birimi = hisse.info.get('financialCurrency', 'Bilinmiyor')
    if para_birimi == 'Bilinmiyor' and sembol in ['WHR', 'CARR', 'TT', 'JCI']: 
        para_birimi = 'USD'
    
    # 1. Historical Data
    hist = hisse.history(period="max")
    if not hist.empty and 'Close' in hist.columns:
        hist = hist[['Close']].copy().reset_index()
        hist['Date'] = pd.to_datetime(hist['Date']).dt.tz_localize(None).dt.date
        hist.rename(columns={'Close': 'Value'}, inplace=True)
        hist['Metric'] = 'Stock'
        hist['Metric_ID'] = id_olustur('Stock')
        hist['Order'] = 1
        hist['Company'] = ad
        hist['Currency'] = para_birimi
        
        usd_vals, eur_vals = [], []
        for _, row in hist.iterrows():
            val = row['Value']
            tarih = pd.to_datetime(row['Date'])
            v_usd, v_eur = None, None
            if para_birimi == "USD":
                v_usd = val
            elif para_birimi in kur_eslesme:
                try:
                    kur = kur_df[kur_eslesme[para_birimi]].dropna().asof(tarih)
                    v_usd = val * kur
                except:
                    pass
            if v_usd is not None:
                try:
                    eur_kur = eur_usd_series.asof(tarih)
                    if pd.notna(eur_kur) and eur_kur > 0:
                        v_eur = v_usd / eur_kur
                except:
                    pass
            usd_vals.append(v_usd)
            eur_vals.append(v_eur)
            
        hist['Value_USD'] = [f"{x:.2f}" if pd.notna(x) else "" for x in usd_vals]
        hist['Value_EUR'] = [f"{x:.2f}" if pd.notna(x) else "" for x in eur_vals]
        hist['Value'] = hist['Value'].apply(lambda x: f"{x:.2f}" if pd.notna(x) else "")
        hist_list.append(hist[['Date', 'Metric_ID', 'Metric', 'Order', 'Value', 'Value_USD', 'Value_EUR', 'Company', 'Currency']])
        
    # 2. Financials (YTD dahil), Balance Sheet (stok veri, YTD yok), Cash Flow (YTD dahil)
    fin_list.append(tabloyu_duzenle(hisse.quarterly_financials, ad, para_birimi, "ortalama", ytd_hesapla=True))
    bs_list.append(tabloyu_duzenle(hisse.quarterly_balance_sheet, ad, para_birimi, "gunluk", ytd_hesapla=False))
    cf_list.append(tabloyu_duzenle(hisse.quarterly_cashflow, ad, para_birimi, "ortalama", ytd_hesapla=True))
    
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
