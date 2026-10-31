import pandas as pd

from fpa import anomalies as A


def test_robust_z_flags_the_planted_outlier():
    base = [0.01, 0.02, -0.01, 0.0, 0.015, -0.02, 0.01, 0.005]
    rows = [{"fiscal_year": 2025, "object_class_number": "60", "adopted": 50e6, "revision": 50e6 * p} for p in base]
    rows.append({"fiscal_year": 2025, "object_class_number": "60", "adopted": 50e6, "revision": 40e6})
    out = A.score(pd.DataFrame(rows))
    assert out.is_anomaly.sum() == 1
    assert out.loc[out.is_anomaly, "revision"].item() == 40e6


def test_small_base_lines_are_excluded():
    df = pd.DataFrame([{"fiscal_year": 2025, "object_class_number": "10", "adopted": 1000, "revision": 1e6}])
    assert A.score(df).empty


def test_constant_series_gives_zero_scores():
    s = A.robust_z(pd.Series([1.0, 1.0, 1.0]))
    assert (s == 0).all()
