import yfinance as yf
import pandas as pd

hisse = yf.Ticker("ARCLK.IS")

hisse.history(period="max").to_csv("historical_data.csv")
hisse.financials.to_csv("financials.csv")
hisse.balance_sheet.to_csv("balance_sheet.csv")
hisse.cashflow.to_csv("cash_flow.csv")

try:
    pd.DataFrame([hisse.info]).to_csv("statistics.csv")
except:
    pass
