"""Flag unusual in-year revisions at unit-of-appropriation x object-class grain.

Score: robust (modified) z-score of revision % within each object class and fiscal year,
z = 0.6745 * (x - median) / MAD (Iglewicz & Hoaglin). Flag when |z| > 3.5 AND |revision| >= $10m,
so that tiny lines with large percentages do not dominate. Author: Amir Khan
"""
from __future__ import annotations

import numpy as np
import pandas as pd

Z_CUT, MIN_ABS = 3.5, 10_000_000


def robust_z(x: pd.Series) -> pd.Series:
    med = x.median()
    mad = (x - med).abs().median()
    if not mad or np.isnan(mad):
        return pd.Series(0.0, index=x.index)
    return 0.6745 * (x - med) / mad


def score(rev: pd.DataFrame) -> pd.DataFrame:
    d = rev[rev["adopted"].abs() >= 1_000_000].copy()   # percentage needs a meaningful base
    d["revision_pct"] = d["revision"] / d["adopted"]
    d["robust_z"] = d.groupby(["fiscal_year", "object_class_number"])["revision_pct"].transform(robust_z)
    d["is_anomaly"] = (d["robust_z"].abs() > Z_CUT) & (d["revision"].abs() >= MIN_ABS)
    return d
