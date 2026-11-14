"""Cross-sectional regressions on the city table.

Model 1  log(rent)          ~ log(students) + intl_share + east
Model 2  log(jobs per 1000) ~ log(students) + intl_share + log(rent) + east

OLS with heteroskedasticity-robust (HC3) standard errors. With ~60 cities and
no exogenous variation these are descriptive associations, not causal effects;
the write-up in analysis/README.md discusses what would be needed for more.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .config import OUT, ROOT

EAST = {"DE-BB", "DE-MV", "DE-SN", "DE-ST", "DE-TH"}
MODELS = {
    "Rent": "np.log(rent_monthly) ~ np.log(students_total) + intl_share + east",
    "Job density": ("np.log(jobs_per_1000) ~ np.log(students_total) + intl_share"
                    " + np.log(rent_monthly) + east"),
}


def load() -> tuple[pd.DataFrame, dict]:
    df = pd.DataFrame(json.loads((OUT / "cities.json").read_text(encoding="utf-8")))
    meta = json.loads((OUT / "meta.json").read_text(encoding="utf-8"))
    df["east"] = df["state_id"].isin(EAST).astype(int)
    return df, meta


def fit(df: pd.DataFrame, formula: str):
    cols = ["rent_monthly", "students_total", "intl_share", "jobs_per_1000", "east"]
    data = df[cols].apply(pd.to_numeric, errors="coerce")
    data = data[(data[["rent_monthly", "students_total"]] > 0).all(axis=1)]
    if "jobs_per_1000" in formula:
        data = data[data["jobs_per_1000"] > 0]
    if len(data) < 10:
        raise ValueError(f"only {len(data)} cities have rent, student and job figures; "
                         "fill in data/manual/rents.csv and students.csv first")
    return smf.ols(formula, data=data, missing="drop").fit(cov_type="HC3")


def to_markdown(name: str, res) -> str:
    lines = [f"### {name}", "", f"`{res.model.formula}`", "",
             "| term | coef. | robust s.e. | p |", "|---|---:|---:|---:|"]
    for term in res.params.index:
        lines.append(f"| {term} | {res.params[term]:.3f} | {res.bse[term]:.3f} "
                     f"| {res.pvalues[term]:.3f} |")
    lines += ["", f"N = {int(res.nobs)}, R² = {res.rsquared:.3f}", ""]
    return "\n".join(lines)


def run() -> int:
    df, meta = load()
    out = ["# Regression results", "",
           f"Generated from `docs/data/cities.json` ({meta['generated_at']})."]
    if meta.get("sample"):
        out += ["", "> **These results use the synthetic preview data and mean nothing.**",
                "> Run `atlas build` with real inputs, then `atlas analyze` again."]
    out.append("")
    for name, formula in MODELS.items():
        try:
            out.append(to_markdown(name, fit(df, formula)))
        except Exception as exc:
            out += [f"### {name}", "", f"Not estimated: {exc}", ""]
    path = ROOT / "analysis" / "results.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out))
    return 0


__all__ = ["run", "fit", "load", "np"]
