import numpy as np
import pandas as pd
import pytest

from fpa import forecast as F


@pytest.fixture
def life():
    yrs = np.arange(2017, 2025)
    adopted = 100 * 1.05 ** (yrs - 2017)
    return pd.DataFrame({"fiscal_year": yrs, "adopted": adopted, "preliminary": adopted / 1.01})


def test_models_recover_exact_geometric_growth(life):
    hist = life.iloc[:-1]
    target = life.adopted.iloc[-1]
    assert F.predict("drift", hist) == pytest.approx(target)
    assert F.predict("log_trend", hist) == pytest.approx(target)
    assert F.predict("prelim_anchor", hist, life.preliminary.iloc[-1]) == pytest.approx(target)
    assert F.predict("naive", hist) == pytest.approx(life.adopted.iloc[-2])


def test_backtest_uses_only_prior_years(life):
    bt = F.backtest(life, min_train=3)
    assert (bt.origin_fy < bt.target_fy).all()
    assert set(bt.model) == set(F.MODELS)
    sc = F.score(bt)
    assert sc.loc[sc.model == "log_trend", "mape"].item() < 1e-9


def test_prelim_anchor_needs_a_preliminary(life):
    assert F.predict("prelim_anchor", life, None) is None


def test_next_year_band_orders_correctly(life):
    noisy = life.assign(adopted=life.adopted * (1 + np.array([0, .02, -.01, .03, -.02, .01, 0, .02])))
    nxt = F.next_year(noisy, F.backtest(noisy))
    assert (nxt.target_fy == 2025).all()
    assert (nxt.p10 <= nxt.p90).all()
