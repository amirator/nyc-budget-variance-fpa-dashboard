"""Forecast the NYC Adopted expense budget total and backtest with rolling origins.

Models (all fitted on Adopted totals FY<=origin-1 only, no leakage):
  naive          A_t = A_{t-1}
  drift          A_t = A_{t-1} * (1 + mean growth)
  log_trend      OLS on log(A) vs year, extrapolated one step
  prelim_anchor  A_t = P_t * median(A/P) over prior years   (uses that year's Preliminary plan, which is
                 published in Jan/Feb before adoption in June, so it is a legitimate leading indicator)
Author: Amir Khan
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = ("naive", "drift", "log_trend", "prelim_anchor")


def predict(model: str, hist: pd.DataFrame, target_prelim: float | None = None) -> float | None:
    """hist: columns fiscal_year, adopted, preliminary (sorted, all before the target year)."""
    a = hist["adopted"].to_numpy(float)
    if len(a) == 0:
        return None
    if model == "naive":
        return float(a[-1])
    if model == "drift":
        if len(a) < 2:
            return None
        g = np.mean(a[1:] / a[:-1] - 1)
        return float(a[-1] * (1 + g))
    if model == "log_trend":
        if len(a) < 3:
            return None
        x = hist["fiscal_year"].to_numpy(float)
        b, c = np.polyfit(x, np.log(a), 1)
        return float(np.exp(c + b * (x[-1] + 1)))
    if model == "prelim_anchor":
        h = hist.dropna(subset=["preliminary"])
        if target_prelim is None or np.isnan(target_prelim) or len(h) < 2:
            return None
        return float(target_prelim * np.median(h["adopted"] / h["preliminary"]))
    raise ValueError(model)


def backtest(life: pd.DataFrame, min_train: int = 3) -> pd.DataFrame:
    life = life.dropna(subset=["adopted"]).sort_values("fiscal_year").reset_index(drop=True)
    rows = []
    for i in range(min_train, len(life)):
        hist, tgt = life.iloc[:i], life.iloc[i]
        for m in MODELS:
            p = predict(m, hist, tgt.get("preliminary"))
            if p is None:
                continue
            rows.append({"origin_fy": int(hist.fiscal_year.iloc[-1]), "target_fy": int(tgt.fiscal_year),
                         "model": m, "forecast": p, "actual": float(tgt.adopted),
                         "error": p - float(tgt.adopted), "ape": abs(p / float(tgt.adopted) - 1)})
    return pd.DataFrame(rows)


def score(bt: pd.DataFrame) -> pd.DataFrame:
    return (bt.groupby("model")
              .agg(n=("ape", "size"), mape=("ape", "mean"), max_ape=("ape", "max"),
                   bias=("error", "mean"), rmse=("error", lambda e: float(np.sqrt(np.mean(np.square(e))))))
              .sort_values("mape").reset_index())


def next_year(life: pd.DataFrame, bt: pd.DataFrame) -> pd.DataFrame:
    """One-step-ahead forecast for the first FY without an Adopted budget, with an empirical
    80% band from that model's backtest percentage errors."""
    hist = life.dropna(subset=["adopted"]).sort_values("fiscal_year")
    tgt_fy = int(hist.fiscal_year.max()) + 1
    nxt = life[life.fiscal_year == tgt_fy]
    prelim = float(nxt.preliminary.iloc[0]) if len(nxt) and pd.notna(nxt.preliminary.iloc[0]) else None
    out = []
    for m in MODELS:
        p = predict(m, hist, prelim)
        if p is None:
            continue
        pe = (bt.loc[bt.model == m, "error"] / bt.loc[bt.model == m, "actual"]).to_numpy()
        # pe = forecast/actual - 1  =>  actual = forecast / (1 + pe)
        q10, q90 = (np.quantile(pe, [0.1, 0.9]) if len(pe) >= 4 else (np.nan, np.nan))
        out.append({"target_fy": tgt_fy, "model": m, "forecast": p,
                    "p10": p / (1 + q90) if not np.isnan(q90) else None,
                    "p90": p / (1 + q10) if not np.isnan(q10) else None})
    return pd.DataFrame(out)
