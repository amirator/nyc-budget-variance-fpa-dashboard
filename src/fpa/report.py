"""Compute findings, write PNG figures and a multi-page interactive Plotly dashboard. Author: Amir Khan"""
from __future__ import annotations

import json
import numpy as np
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
from plotly.subplots import make_subplots  # noqa: E402

from fpa import anomalies as A  # noqa: E402
from fpa import forecast as F  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "fpa.duckdb"
OUT = ROOT / "reports"
FIG = OUT / "figures"
NAVY, TEAL, RED, GREY, GOLD = "#1f3b57", "#2a9d8f", "#c8553d", "#9aa5b1", "#e9c46a"
BN = 1e9
TOP_N = 8


def bridge(start_label, start, deltas: pd.Series, end_label, end):
    """Waterfall data: start bar, top-N deltas by |value| + 'All other', end bar."""
    deltas = deltas.sort_values(key=abs, ascending=False)
    top, rest = deltas.iloc[:TOP_N], deltas.iloc[TOP_N:].sum()
    labels = [start_label] + [str(i)[:38] for i in top.index] + ["All other agencies", end_label]
    vals = [start] + list(top.values) + [rest, end]
    measure = ["absolute"] + ["relative"] * (len(top) + 1) + ["total"]
    return labels, vals, measure


def short(name: str) -> str:
    return (name.replace("DEPARTMENT OF ", "DEPT OF ").replace("DEPARTMENT ", "DEPT ")
                .replace("ADMINISTRATION", "ADMIN").title())


def load(con):
    q = lambda s: con.execute(s).df()  # noqa: E731
    d = {
        "life": q("select * from mart.fy_lifecycle order by 1"),
        "agency_stage": q("select * from mart.agency_stage"),
        "inyear": q("select * from mart.agency_in_year_revision"),
        "yoy_agency": q("select * from mart.yoy_adopted_by_agency"),
        "yoy_oc": q("select * from mart.yoy_adopted_by_object_class"),
        "funding": q("select * from mart.funding_source_summary"),
        "rev": q("select * from mart.ua_object_revision"),
        "checks": q("select * from mart.dq_checks"),
        "rows": q("select (select count(*) from mart.fct_budget_line) lines, (select count(*) from mart.fct_funding) funding_rows, "
                  "(select count(*) from mart.dim_agency) agencies, (select count(*) from mart.dim_unit_appropriation) uas"),
    }
    for k in ("agency_stage", "inyear", "yoy_agency", "rev"):
        d[k]["agency_label"] = d[k]["agency_name"].map(short)
    return d


def cycle_bridge(d, fy):
    s = d["agency_stage"][d["agency_stage"].fiscal_year == fy].pivot_table(
        index="agency_label", columns="stage", values="amount", aggfunc="sum").fillna(0)
    if "Preliminary" not in s:
        return None
    delta = (s["Adopted"] - s["Preliminary"]) / BN
    return bridge(f"FY{fy} Preliminary", s["Preliminary"].sum() / BN, delta, f"FY{fy} Adopted", s["Adopted"].sum() / BN)


def inyear_bridge(d, fy):
    s = d["inyear"][d["inyear"].fiscal_year == fy].groupby("agency_label")[["adopted", "modified"]].sum()
    return bridge(f"FY{fy} Adopted", s.adopted.sum() / BN, (s.modified - s.adopted) / BN,
                  f"FY{fy} Modified", s.modified.sum() / BN)


def yoy_bridge(d, fy):
    s = d["yoy_agency"][d["yoy_agency"].fiscal_year == fy].groupby("agency_label")[["prior_adopted", "adopted"]].sum()
    return bridge(f"FY{fy-1} Adopted", s.prior_adopted.sum() / BN, (s.adopted - s.prior_adopted) / BN,
                  f"FY{fy} Adopted", s.adopted.sum() / BN)


# ---------------------------------------------------------------- findings
def findings(d, bt, sc, nxt, an):
    life = d["life"]
    f = {"rows": d["rows"].iloc[0].to_dict(), "checks": d["checks"].to_dict("records")}
    f["lifecycle_bn"] = life.assign(**{c: life[c] / BN for c in ["preliminary", "executive", "adopted", "modified_latest", "in_year_revision"]})[
        ["fiscal_year", "preliminary", "executive", "adopted", "modified_latest", "in_year_revision", "in_year_revision_pct"]].round(4).to_dict("records")
    a = life.dropna(subset=["adopted"])
    f["adopted_cagr_fy17_fy27"] = float((a.adopted.iloc[-1] / a.adopted.iloc[0]) ** (1 / (len(a) - 1)) - 1)
    inyr = life.dropna(subset=["in_year_revision_pct"])
    f["in_year_revision_pct_range"] = [float(inyr.in_year_revision_pct.min()), float(inyr.in_year_revision_pct.max())]
    for fy in (2026,):
        s = d["inyear"][d["inyear"].fiscal_year == fy].assign(r=lambda x: x.revision / BN).nlargest(5, "r")
        f[f"top_in_year_increases_fy{fy}_bn"] = s[["agency_name", "r"]].round(3).to_dict("records")
    s = d["agency_stage"][d["agency_stage"].fiscal_year == 2027].pivot_table(index="agency_name", columns="stage", values="amount", aggfunc="sum").fillna(0)
    s["prelim_to_adopted_bn"] = (s.Adopted - s.Preliminary) / BN
    f["fy2027_prelim_to_adopted_by_agency_bn"] = (s.prelim_to_adopted_bn.sort_values(key=abs, ascending=False).head(6).round(3).reset_index().to_dict("records"))
    y = d["yoy_agency"][d["yoy_agency"].fiscal_year == 2027].assign(v=lambda x: x.variance / BN)
    f["fy2027_vs_fy2026_adopted_by_agency_bn"] = y.nlargest(6, "v")[["agency_name", "v"]].round(3).to_dict("records")
    o = d["yoy_oc"][d["yoy_oc"].fiscal_year == 2027].assign(v=lambda x: x.variance / BN)
    f["fy2027_vs_fy2026_adopted_by_object_class_bn"] = o.nlargest(6, "v")[["object_class_name", "v"]].round(3).to_dict("records")
    fu = d["funding"].groupby(["fiscal_year", "funding_group"])[["adopted", "in_year_revision"]].sum().div(BN).round(3).reset_index()
    f["funding_by_group_bn"] = fu.to_dict("records")
    fs = d["funding"][d["funding"].fiscal_year == 2026].assign(r=lambda x: x.in_year_revision / BN)
    f["fy2026_in_year_revision_by_funding_source_bn"] = fs[["funding_source_name", "r"]].round(3).to_dict("records")
    f["forecast_backtest"] = sc.round(5).to_dict("records")
    f["forecast_next"] = nxt.assign(**{c: nxt[c] / BN for c in ["forecast", "p10", "p90"]}).round(3).to_dict("records")
    f["anomalies"] = {"scored_lines": int(len(an)), "flagged": int(an.is_anomaly.sum()),
                      "by_year": an[an.is_anomaly].groupby("fiscal_year").size().to_dict()}
    return f


# ---------------------------------------------------------------- PNGs
def style(ax, title):
    ax.set_title(title, fontsize=12, fontweight="bold", loc="left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def png_waterfall(ax, labels, vals, measure, title):
    cum, bottoms, heights, colors = 0, [], [], []
    for v, m in zip(vals, measure):
        if m == "absolute" or m == "total":
            bottoms.append(0); heights.append(v); colors.append(NAVY); cum = v
        else:
            bottoms.append(cum if v >= 0 else cum + v); heights.append(abs(v)); colors.append(TEAL if v >= 0 else RED); cum += v
    ax.bar(range(len(vals)), heights, bottom=bottoms, color=colors)
    lo = min(b for b, m in zip(bottoms, measure) if m == "relative") if "relative" in measure else 0
    ax.set_ylim(lo * 0.97, max(b + h for b, h in zip(bottoms, heights)) * 1.01)
    ax.set_xticks(range(len(vals)), labels, rotation=40, ha="right", fontsize=8)
    for i, (v, m) in enumerate(zip(vals, measure)):
        ax.text(i, bottoms[i] + heights[i], f"{v:+.2f}" if m == "relative" else f"{v:.1f}", ha="center", va="bottom", fontsize=7)
    ax.set_ylabel("USD bn"); style(ax, title)


def pngs(d, bt, sc, nxt, an):
    FIG.mkdir(parents=True, exist_ok=True)
    life = d["life"]
    fig, ax = plt.subplots(figsize=(10, 5))
    for col, c, lab in [("preliminary", GREY, "Preliminary"), ("executive", GOLD, "Executive"), ("adopted", NAVY, "Adopted"), ("modified_latest", TEAL, "Modified (in-year, latest)")]:
        ax.plot(life.fiscal_year, life[col] / BN, marker="o", color=c, label=lab)
    ax.legend(frameon=False); ax.set_ylabel("USD bn"); style(ax, "NYC expense budget lifecycle by fiscal year")
    fig.tight_layout(); fig.savefig(FIG / "01_budget_lifecycle.png", dpi=130); plt.close(fig)

    for i, (fn, fy, name, title) in enumerate([(cycle_bridge, 2027, "02_bridge_prelim_to_adopted_fy2027.png", "FY2027: Preliminary to Adopted, by agency"),
                                               (inyear_bridge, 2026, "03_bridge_in_year_fy2026.png", "FY2026: Adopted to Modified (in-year revisions), by agency"),
                                               (yoy_bridge, 2027, "04_bridge_yoy_adopted_fy2027.png", "Adopted FY2026 to Adopted FY2027, by agency")]):
        fig, ax = plt.subplots(figsize=(11, 5.5))
        png_waterfall(ax, *fn(d, fy), title); fig.tight_layout(); fig.savefig(FIG / name, dpi=130); plt.close(fig)

    fu = d["funding"].dropna(subset=["in_year_revision"]).pivot_table(index="fiscal_year", columns="funding_source_name", values="in_year_revision", aggfunc="sum") / BN
    fig, ax = plt.subplots(figsize=(10, 5)); fu.plot.bar(stacked=True, ax=ax, colormap="tab10", width=0.8)
    ax.legend(frameon=False, fontsize=8, ncol=2); ax.set_ylabel("USD bn"); ax.set_xlabel("")
    style(ax, "In-year revision (Adopted to Modified) by funding source"); fig.tight_layout(); fig.savefig(FIG / "05_funding_source_revisions.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    a = life.dropna(subset=["adopted"])
    ax.plot(a.fiscal_year, a.adopted / BN, color="black", marker="o", lw=2, label="Actual Adopted")
    for m, c in zip(F.MODELS, [GREY, GOLD, TEAL, RED]):
        b = bt[bt.model == m]
        mape = sc.set_index("model").loc[m, "mape"]
        ax.plot(b.target_fy, b.forecast / BN, marker=".", ls="--", color=c, label=f"{m} backtest (MAPE {mape:.1%})")
    for _, r in nxt.iterrows():
        x = r.target_fy + 0.12 * F.MODELS.index(r.model)
        ax.vlines(x, r.p10 / BN, r.p90 / BN, color=NAVY, lw=2)
        ax.scatter([x], [r.forecast / BN], marker="s", color=NAVY, zorder=3)
        ax.annotate(r.model, (x, r.p90 / BN), fontsize=7, ha="center", va="bottom")
    ax.legend(frameon=False, fontsize=8); ax.set_ylabel("USD bn"); style(ax, "Adopted budget: rolling-origin backtests and FY2028 one-step forecast (80% band)")
    fig.tight_layout(); fig.savefig(FIG / "06_forecast_backtest.png", dpi=130); plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    n = an[~an.is_anomaly]; y = an[an.is_anomaly]
    ax.scatter(n.adopted / 1e6, n.revision_pct * 100, s=4, color=GREY, alpha=0.4, label="scored lines")
    ax.scatter(y.adopted / 1e6, y.revision_pct * 100, s=10, color=RED, label=f"flagged (|robust z|>{A.Z_CUT}, |rev|≥$10m): {len(y)}")
    ax.set_xscale("log"); ax.set_yscale("symlog", linthresh=10); ax.set_xlabel("Adopted amount, USD m (log)"); ax.set_ylabel("In-year revision % (symlog)")
    ax.legend(frameon=False); style(ax, "In-year revision anomalies, unit of appropriation x object class")
    fig.tight_layout(); fig.savefig(FIG / "07_anomalies.png", dpi=130); plt.close(fig)


# ---------------------------------------------------------------- dashboard
def wf_selector(d, fn, years, title):
    fig = go.Figure()
    for i, fy in enumerate(years):
        labels, vals, measure = fn(d, fy)
        fig.add_trace(go.Waterfall(x=labels, y=vals, measure=measure, visible=(i == len(years) - 1), name=f"FY{fy}",
                                   increasing={"marker": {"color": TEAL}}, decreasing={"marker": {"color": RED}},
                                   totals={"marker": {"color": NAVY}}, texttemplate="%{y:.2f}", textposition="outside",
                                   hovertemplate="%{x}: %{y:.3f} bn<extra></extra>"))
    buttons = [dict(label=f"FY{fy}", method="update", args=[{"visible": [j == i for j in range(len(years))]}]) for i, fy in enumerate(years)]
    fig.update_layout(title=title, yaxis_title="USD bn", height=560, template="plotly_white",
                      updatemenus=[dict(buttons=buttons, active=len(years) - 1, x=1, xanchor="right", y=1.15)])
    return fig


def dashboard(d, bt, sc, nxt, an, f):
    life = d["life"]
    pages = []
    # 1 overview
    o = go.Figure()
    for col, c, lab in [("preliminary", GREY, "Preliminary"), ("executive", GOLD, "Executive"), ("adopted", NAVY, "Adopted"), ("modified_latest", TEAL, "Modified (latest)")]:
        o.add_trace(go.Scatter(x=life.fiscal_year, y=life[col] / BN, name=lab, mode="lines+markers", line=dict(color=c)))
    o.update_layout(title="Budget lifecycle by fiscal year (USD bn)", template="plotly_white", height=480)
    r = life[life.fiscal_year == 2027].iloc[0]; r26 = life[life.fiscal_year == 2026].iloc[0]
    kpis = [("FY2027 Adopted", f"${r.adopted / BN:.2f}bn"), ("vs FY2026 Adopted", f"{r.adopted / r26.adopted - 1:+.1%}"),
            ("FY2026 in-year revision", f"{r26.in_year_revision / BN:+.2f}bn ({r26.in_year_revision_pct:+.1%})"),
            ("FY2017–27 Adopted CAGR", f"{f['adopted_cagr_fy17_fy27']:.1%}"), ("Budget lines modelled", f"{int(f['rows']['lines']):,}")]
    pages.append(("Overview", [o], kpis))
    yrs = sorted(d["agency_stage"].query("stage=='Preliminary'").fiscal_year.unique())
    pages.append(("Budget cycle bridge", [wf_selector(d, cycle_bridge, yrs, "Preliminary to Adopted by agency (choose FY)")], None))
    yrs2 = sorted(d["inyear"].fiscal_year.unique())
    fu = d["funding"].dropna(subset=["in_year_revision"])
    ff = go.Figure([go.Bar(x=g.fiscal_year, y=g.in_year_revision / BN, name=n) for n, g in fu.groupby("funding_source_name")])
    ff.update_layout(barmode="relative", title="In-year revision by funding source (USD bn)", template="plotly_white", height=460)
    pages.append(("In-year revisions", [wf_selector(d, inyear_bridge, yrs2, "Adopted to Modified by agency (choose FY)"), ff], None))
    yrs3 = sorted(d["yoy_agency"].fiscal_year.unique())
    oc = d["yoy_oc"]
    oc_fig = go.Figure()
    for i, fy in enumerate(yrs3):
        g = oc[oc.fiscal_year == fy].sort_values("variance")
        oc_fig.add_trace(go.Bar(x=g.variance / BN, y=g.object_class_name, orientation="h", visible=(i == len(yrs3) - 1),
                                marker_color=[TEAL if v >= 0 else RED for v in g.variance], name=f"FY{fy}"))
    oc_fig.update_layout(title="Adopted YoY variance by object class (USD bn)", template="plotly_white", height=700,
                         updatemenus=[dict(buttons=[dict(label=f"FY{fy}", method="update", args=[{"visible": [j == i for j in range(len(yrs3))]}]) for i, fy in enumerate(yrs3)],
                                           active=len(yrs3) - 1, x=1, xanchor="right", y=1.08)])
    pages.append(("Variance decomposition", [wf_selector(d, yoy_bridge, yrs3, "Adopted year-over-year by agency (choose FY)"), oc_fig], None))
    fc = go.Figure()
    a = life.dropna(subset=["adopted"])
    fc.add_trace(go.Scatter(x=a.fiscal_year, y=a.adopted / BN, name="Actual Adopted", line=dict(color="black", width=3)))
    for m, c in zip(F.MODELS, [GREY, GOLD, TEAL, RED]):
        b = bt[bt.model == m]
        fc.add_trace(go.Scatter(x=b.target_fy, y=b.forecast / BN, name=f"{m} (backtest)", line=dict(color=c, dash="dash")))
    for _, rr in nxt.iterrows():
        x = rr.target_fy + 0.12 * F.MODELS.index(rr.model)
        fc.add_trace(go.Scatter(x=[x, x], y=[rr.p10 / BN, rr.p90 / BN], mode="lines", line=dict(color=NAVY, width=3), showlegend=False, hoverinfo="skip"))
        fc.add_trace(go.Scatter(x=[x], y=[rr.forecast / BN], name=f"FY{int(rr.target_fy)} {rr.model}: {rr.forecast / BN:.1f}bn (80% band {rr.p10 / BN:.1f}-{rr.p90 / BN:.1f})", mode="markers", marker=dict(symbol="square", size=9)))
    fc.update_layout(title="Adopted budget forecast: rolling-origin backtests", template="plotly_white", height=480)
    t = go.Figure(go.Table(header=dict(values=["model", "n", "MAPE", "max APE", "bias (bn)", "RMSE (bn)"]),
                           cells=dict(values=[sc.model, sc.n, sc.mape.map("{:.2%}".format), sc.max_ape.map("{:.2%}".format),
                                              (sc.bias / BN).round(2), (sc.rmse / BN).round(2)])))
    t.update_layout(height=260, margin=dict(t=10, b=10))
    pages.append(("Forecast", [fc, t], None))
    flag = an[an.is_anomaly].sort_values("revision", key=abs, ascending=False)
    sc_fig = go.Figure()
    sc_fig.add_trace(go.Scattergl(x=an.adopted / 1e6, y=an.revision_pct * 100, mode="markers", marker=dict(size=4, color=GREY, opacity=0.4), name="scored",
                                  text=an.agency_label + " | " + an.ua_name + " | " + an.object_class_name, hovertemplate="%{text}<br>adopted %{x:.1f}m, rev %{y:.1f}%<extra></extra>"))
    sc_fig.add_trace(go.Scattergl(x=flag.adopted / 1e6, y=flag.revision_pct * 100, mode="markers", marker=dict(size=7, color=RED), name="flagged",
                                  text=flag.agency_label + " | " + flag.ua_name + " | " + flag.object_class_name, hovertemplate="%{text}<br>adopted %{x:.1f}m, rev %{y:.1f}%<extra></extra>"))
    sc_fig.update_layout(title="In-year revision anomalies: unit of appropriation x object class (hover for detail)", xaxis_type="log", yaxis_title="revision %", xaxis_title="adopted, USD m (log)", template="plotly_white", height=520)
    top = flag.head(25)
    tt = go.Figure(go.Table(header=dict(values=["FY", "agency", "unit of appropriation", "object class", "adopted (m)", "revision (m)", "rev %", "robust z"]),
                            cells=dict(values=[top.fiscal_year, top.agency_label, top.ua_name, top.object_class_name, (top.adopted / 1e6).round(1),
                                               (top.revision / 1e6).round(1), (top.revision_pct * 100).round(1), top.robust_z.round(1)])))
    tt.update_layout(height=700, margin=dict(t=10, b=10))
    pages.append(("Anomalies", [sc_fig, tt], None))

    nav, body = [], []
    for i, (name, figs, kpis) in enumerate(pages):
        nav.append(f'<button class="tab{" on" if i == 0 else ""}" onclick="show({i})">{name}</button>')
        html = ""
        if kpis:
            html += '<div class="kpis">' + "".join(f'<div class="kpi"><div class="v">{v}</div><div class="l">{k}</div></div>' for k, v in kpis) + "</div>"
        for fg in figs:
            html += fg.to_html(full_html=False, include_plotlyjs=False, config={"displaylogo": False})
        body.append(f'<section id="p{i}" style="display:{"block" if i == 0 else "none"}">{html}</section>')
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>NYC Budget Revision Variance – FP&A dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#f5f7fa;color:#1f3b57}}header{{background:#1f3b57;color:#fff;padding:14px 24px}}
header h1{{margin:0;font-size:20px}}header p{{margin:4px 0 0;font-size:12px;opacity:.85}}nav{{padding:8px 24px;background:#fff;border-bottom:1px solid #dde}}
.tab{{border:0;background:none;padding:8px 14px;font-size:14px;cursor:pointer;color:#1f3b57}}.tab.on{{border-bottom:3px solid #2a9d8f;font-weight:600}}
section{{padding:12px 24px}}.kpis{{display:flex;gap:12px;flex-wrap:wrap;margin:8px 0}}.kpi{{background:#fff;border-radius:8px;padding:12px 16px;min-width:170px;box-shadow:0 1px 3px #0001}}
.kpi .v{{font-size:22px;font-weight:700}}.kpi .l{{font-size:12px;color:#667}}footer{{font-size:11px;color:#667;padding:12px 24px}}</style></head><body>
<header><h1>NYC Expense Budget – Budget Revision Variance (FY2017–FY2027)</h1>
<p>Source: NYC Open Data, Expense Budget (mwzb-yiwb) and Expense Budget Funding (39g5-gbp3). Budget figures, not actual spending. Built by Amir Khan.</p></header>
<nav>{''.join(nav)}</nav>{''.join(body)}
<footer>Generated by src/fpa/report.py from data/fpa.duckdb. Forecasts are statistical baselines evaluated by rolling-origin backtest, not official projections.</footer>
<script>function show(i){{document.querySelectorAll('section').forEach((s,j)=>s.style.display=j==i?'block':'none');
document.querySelectorAll('.tab').forEach((b,j)=>b.classList.toggle('on',j==i));window.dispatchEvent(new Event('resize'));}}</script></body></html>"""
    (OUT / "dashboard.html").write_text(page, encoding="utf-8")


def _clean(o):
    """Replace NaN/inf with None so findings.json is strict JSON."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, float) and not np.isfinite(o):
        return None
    if isinstance(o, np.generic):
        return _clean(o.item())
    return o


def main(db: Path = DB) -> dict:
    con = duckdb.connect(str(db), read_only=True)
    d = load(con); con.close()
    bt = F.backtest(d["life"]); sc = F.score(bt); nxt = F.next_year(d["life"], bt)
    an = A.score(d["rev"])
    OUT.mkdir(exist_ok=True)
    f = findings(d, bt, sc, nxt, an)
    (OUT / "findings.json").write_text(json.dumps(_clean(f), indent=1, default=str, allow_nan=False))
    bt.to_csv(OUT / "forecast_backtest.csv", index=False)
    an[an.is_anomaly].sort_values("revision", key=abs, ascending=False).to_csv(OUT / "anomalies_flagged.csv", index=False)
    pngs(d, bt, sc, nxt, an)
    dashboard(d, bt, sc, nxt, an, f)
    return f


if __name__ == "__main__":
    print(json.dumps(main(), indent=1, default=str)[:6000])
