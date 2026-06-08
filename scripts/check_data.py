import pandas as pd

for ticker in ["ALICORC1", "BUENAVC1"]:
    bvl = pd.read_parquet(f"data/raw/market_{ticker}_bvl.parquet")
    yah = pd.read_parquet(f"data/raw/market_{ticker}_yahoo.parquet")
    m = bvl.merge(yah, on="date", suffixes=("_bvl", "_yah"))
    cmin = bvl["close"].min()
    cmax = bvl["close"].max()
    ymin = yah["close"].min()
    ymax = yah["close"].max()
    print(f"{ticker}: BVL {cmin:.2f}-{cmax:.2f}  Yahoo {ymin:.2f}-{ymax:.2f}")
    if not m.empty:
        m["ratio"] = m["close_yah"] / m["close_bvl"]
        print(f"  ratio Yahoo/BVL: mean={m['ratio'].mean():.3f}  std={m['ratio'].std():.3f}")
        print(m[["date", "close_bvl", "close_yah"]].head(3).to_string())
        print(m[["date", "close_bvl", "close_yah"]].tail(3).to_string())
    print()

print("--- RESUMEN DATASET FINAL ---")
for ticker in ["CREDITC1", "BUENAVC1", "ALICORC1", "SAGAC1", "CORAREC1"]:
    df = pd.read_parquet(f"data/interim/market_{ticker}.parquet")
    bvl_rows = (df["source"] == "bvl").sum()
    yah_rows = (df["source"] == "yahoo").sum()
    d_min = df["date"].min().date()
    d_max = df["date"].max().date()
    nan_vol = df["volume"].isna().sum()
    print(f"{ticker}: total={len(df)}  bvl={bvl_rows}  yahoo={yah_rows}"
          f"  {d_min}..{d_max}  vol_NaN={nan_vol}")
