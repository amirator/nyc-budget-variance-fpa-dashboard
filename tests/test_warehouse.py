"""Integration tests on the built star schema (skipped if data/fpa.duckdb is absent)."""
from pathlib import Path

import duckdb
import pytest

DB = Path(__file__).resolve().parents[1] / "data" / "fpa.duckdb"
pytestmark = pytest.mark.skipif(not DB.exists(), reason="warehouse not built")


@pytest.fixture(scope="module")
def con():
    c = duckdb.connect(str(DB), read_only=True)
    yield c
    c.close()


def one(con, q):
    return con.execute(q).fetchone()[0]


def test_all_warehouse_checks_pass(con):
    assert one(con, "select count(*) from mart.dq_checks where failing_rows > 0") == 0


def test_full_row_count_loaded(con):
    assert one(con, "select count(*) from mart.fct_budget_line") > 1_000_000


def test_stage_sequence_complete_from_fy2018(con):
    assert one(con, """select count(*) from (select fiscal_year from mart.dim_budget_stage
                       where fiscal_year >= 2018 group by 1 having count(distinct stage) <> 3)""") == 0


def test_cycle_bridge_closes(con):
    gap = one(con, """select max(abs(p.s + d.s - a.s)) from
        (select fiscal_year, sum(amount) s from mart.agency_stage where stage='Preliminary' group by 1) p
        join (select fiscal_year, sum(amount) s from mart.agency_stage where stage='Adopted' group by 1) a using (fiscal_year)
        join (select fiscal_year, sum(a2 - p2) s from (select fiscal_year, agency_number,
               coalesce(sum(amount) filter (where stage='Adopted'),0) a2, coalesce(sum(amount) filter (where stage='Preliminary'),0) p2
               from mart.agency_stage group by 1,2) group by 1) d using (fiscal_year)""")
    assert gap < 1.0


def test_funding_sources_sum_to_total(con):
    gap = one(con, """select max(abs(t - s)) from (
        select f.stage_key, f.ua_key, sum(amount) s,
               any_value(try_cast(r.total_financial_plan_amount as double)) t
        from mart.fct_funding f join stg.funding r
          on r.agency_number || '-' || r.ua_number = f.ua_key and r.publication_date = f.publication_date
        where measure = 'financial_plan' group by 1, 2) x""")
    assert gap < 1.0


def test_python_bridges_close(con):
    from fpa import report
    d = report.load(con)
    for fn, fy in [(report.cycle_bridge, 2027), (report.inyear_bridge, 2026), (report.yoy_bridge, 2027)]:
        labels, vals, measure = fn(d, fy)
        assert measure[0] == "absolute" and measure[-1] == "total"
        assert abs(vals[0] + sum(vals[1:-1]) - vals[-1]) < 1e-6
