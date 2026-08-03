import csv
from data.storage import MarketDataStorage
from data.models import Candle

CSV_FILE = "BTCUSDT_1h_full.csv"

storage = MarketDataStorage ("marketmind.db")

candles = []

with open(CSV_FILE, newline="") as f:
    reader = csv.DictReader(f)

    for row in reader:
        candles.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1h",
                open_time=int(row["open_time"]),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                close_time=int(row["close_time"]),
                quote_volume=float(row["quote_volume"]),
                trades=int(row["trades"]),
                taker_buy_base=float(row["taker_buy_base"]),
                taker_buy_quote=float(row["taker_buy_quote"]),
            )
        )

count = storage.insert_candles(candles)

print(f"Inserted {count} candles")

storage.close()

