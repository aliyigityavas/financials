import yfinance as yf
import pandas as pd

hisse = yf.Ticker("ARCLK.IS")

# Hissenin para birimini otomatik çek (Bulamazsa TRY yaz)
currency = hisse.info.get('financialCurrency', 'TRY')

# Veriye Currency kolonu ekleyip CSV'ye çeviren fonksiyon
def formatla_ve_kaydet(df, dosya_adi):
    if not df.empty:
        df['Currency'] = currency
        df.to_csv(dosya_adi)

# 1. Historical Data (Değişmedi)
hisse.history(period="max").to_csv("historical_data.csv")

# 2. Quarterly Financials (Income Statement - Çeyreklik)
formatla_ve_kaydet(hisse.quarterly_financials, "financials.csv")

# 3. Quarterly Balance Sheet (Bilanço - Çeyreklik)
formatla_ve_kaydet(hisse.quarterly_balance_sheet, "balance_sheet.csv")

# 4. Quarterly Cash Flow (Nakit Akışı - Çeyreklik)
formatla_ve_kaydet(hisse.quarterly_cashflow, "cash_flow.csv")

# 5. Statistics (Değişmedi)
try:
    pd.DataFrame([hisse.info]).to_csv("statistics.csv")
except:
    pass
