#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sensibilidades del cuerpo RPMESP (IPW × diseño, bootstrap 2000).

No relanza AIPW, matching, MICE ni la batería suplementaria.
Reutiliza prepare_raw / weights / ipw_wls del pipeline principal.

Uso (desde la raíz del paquete):
    python analysis/sensibilidades_cuerpo.py
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pipeline_informe_final import (  # noqa: E402
    BASE_COVARIATES_CORE,
    CATEGORICAL,
    DATA,
    SEED,
    TAB,
    add_age_polys,
    ipw_wls,
    prepare_raw,
    smd_table,
    weights,
)

OUTCOME = "anemia_modsev"
B_BOOT = int(os.environ.get("B_BOOT", "2000"))
N_JOBS = max(1, min(7, (os.cpu_count() or 2) - 1))
TOMA7D = ["toma7d_jar", "toma7d_got", "toma7d_pol", "toma7d_otr"]
QTOMA12M = ["qtoma12m_jar", "qtoma12m_got", "qtoma12m_pol", "qtoma12m_otr"]
A_COL = "A_expo"


def _make_pre(covs):
    cat = [c for c in CATEGORICAL if c in covs]
    if "dpto" in covs and "dpto" not in cat:
        cat = cat + ["dpto"]
    num = [c for c in covs if c not in cat]
    transformers = []
    if num:
        transformers.append(
            (
                "num",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="median")),
                        ("sc", StandardScaler()),
                    ]
                ),
                num,
            )
        )
    if cat:
        transformers.append(
            (
                "cat",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="most_frequent")),
                        ("oh", OneHotEncoder(drop="first", handle_unknown="ignore")),
                    ]
                ),
                cat,
            )
        )
    return ColumnTransformer(transformers, remainder="drop")


def fit_ps_local(df, covs, a_col=A_COL):
    a = df[a_col].astype(int).values
    pipe = Pipeline(
        [
            ("pre", _make_pre(covs)),
            ("clf", LogisticRegression(max_iter=2000, solver="lbfgs")),
        ]
    )
    pipe.fit(df[covs], a)
    return a, pipe.predict_proba(df[covs])[:, 1], pipe


def exposure_7d(df, missing_as_zero=True):
    mats = [pd.to_numeric(df[c], errors="coerce") for c in TOMA7D if c in df.columns]
    mat = pd.concat(mats, axis=1)
    expo = pd.Series(np.nan, index=df.index, dtype=float)
    expo[(mat == 1).any(axis=1)] = 1.0
    expo[(mat == 0).all(axis=1)] = 0.0
    n_missing = int(expo.isna().sum())
    if missing_as_zero:
        expo = expo.fillna(0.0)
    return expo, n_missing


def exposure_12m(df):
    mats = [pd.to_numeric(df[c], errors="coerce") for c in QTOMA12M if c in df.columns]
    mat = pd.concat(mats, axis=1)
    return ((mat.fillna(0) > 0).any(axis=1)).astype(float)


def analytic_frame(
    df,
    *,
    require_no_dx=True,
    missing_as_zero=True,
    exposure="7d",
    include_dpto=False,
):
    mask = df["received_any"] == 1
    if require_no_dx:
        mask = mask & (pd.to_numeric(df["dx_anemia"], errors="coerce") == 0)
    pop = df.loc[mask].copy()
    if exposure == "7d":
        pop[A_COL], n_miss_expo = exposure_7d(pop, missing_as_zero=missing_as_zero)
    elif exposure == "12m":
        pop[A_COL] = exposure_12m(pop)
        n_miss_expo = 0
    else:
        raise ValueError(exposure)

    covs_base = list(BASE_COVARIATES_CORE)
    keep = list(
        dict.fromkeys(
            [A_COL, OUTCOME, "hv005_norm", "upm", "estrato", "madre_anemia"]
            + covs_base
            + (["dpto"] if include_dpto else [])
        )
    )
    keep = [c for c in keep if c in pop.columns]
    work = add_age_polys(pop[keep].apply(pd.to_numeric, errors="coerce"))
    work = work.dropna().copy()
    covs = [c for c in (covs_base + ["edad_niño_sq", "edad_niño_cu"]) if c in work.columns]
    if include_dpto and "dpto" in work.columns:
        covs = covs + ["dpto"]
    return pop, work, covs, n_miss_expo


def estimate_ipw_design(work, covs, a_col=A_COL, outcome=OUTCOME):
    a, ps, _ = fit_ps_local(work, covs, a_col)
    w_ipw = weights(a, ps, estimand="ATE")
    w_des = work["hv005_norm"].astype(float).values
    w_des = w_des / np.nanmean(w_des)
    est = ipw_wls(work[outcome].astype(float).values, a, w_ipw * w_des)
    return est, a, w_ipw, w_des, ps


def _stratum_clusters(df):
    out = {}
    for s, g in df.groupby("estrato", dropna=True):
        out[s] = {c: part for c, part in g.groupby("upm", dropna=True)}
    return out


_BOOT_PAYLOAD = None


def _init_worker(payload):
    global _BOOT_PAYLOAD
    _BOOT_PAYLOAD = payload


def _one_replicate(stratum_payload, covs, a_col, outcome, seed):
    rng = np.random.default_rng(seed)
    parts = []
    for clusters in stratum_payload.values():
        keys = list(clusters.keys())
        if not keys:
            continue
        drawn = rng.choice(keys, size=len(keys), replace=True)
        for k in drawn:
            parts.append(clusters[k])
    if not parts:
        return None
    db = pd.concat(parts, ignore_index=True)
    try:
        est, *_ = estimate_ipw_design(db, covs, a_col=a_col, outcome=outcome)
        return float(est["estimate"])
    except Exception:
        return None


def bootstrap_spec(work, covs, seed, b=B_BOOT, n_jobs=N_JOBS):
    payload = _stratum_clusters(work)
    ss = np.random.SeedSequence(int(seed))
    child = ss.spawn(b)
    seeds = [int(s.generate_state(1)[0]) for s in child]
    args = [(covs, A_COL, OUTCOME, sd) for sd in seeds]
    if n_jobs == 1:
        draws = [_one_replicate(payload, *a) for a in args]
    else:
        with ProcessPoolExecutor(
            max_workers=n_jobs, initializer=_init_worker, initargs=(payload,)
        ) as ex:
            draws = list(ex.map(_one_replicate_worker, args, chunksize=8))
    arr = np.array([x for x in draws if x is not None], dtype=float)
    return arr


def _one_replicate_worker(args):
    return _one_replicate(_BOOT_PAYLOAD, *args)


def inclusion_reweight(pop, work, covs_base):
    """IPW de inclusión × IPW de exposición × diseño (punto + HC3)."""
    pop = pop.copy()
    pop["_incluido"] = pop.index.isin(work.index).astype(int)
    covs_incl = [c for c in covs_base if c != "madre_anemia" and c in pop.columns]
    d_mod = pop[covs_incl + ["_incluido"]].apply(pd.to_numeric, errors="coerce").dropna()
    y_incl = d_mod["_incluido"].astype(int).values
    pipe = Pipeline(
        [
            ("pre", _make_pre(covs_incl)),
            ("clf", LogisticRegression(max_iter=2000, solver="lbfgs")),
        ]
    )
    pipe.fit(d_mod[covs_incl], y_incl)
    pi = np.clip(pipe.predict_proba(d_mod[covs_incl])[:, 1], 0.05, 0.95)
    pi_map = pd.Series(pi, index=d_mod.index)
    di = work.loc[work.index.intersection(d_mod.index)].copy()
    if "edad_niño_sq" not in di.columns:
        di = add_age_polys(di)
    covs = [c for c in (covs_base + ["edad_niño_sq", "edad_niño_cu"]) if c in di.columns]
    a, ps, _ = fit_ps_local(di, covs, A_COL)
    w_ipw = weights(a, ps, estimand="ATE")
    w_des = di["hv005_norm"].astype(float).values
    w_des = w_des / np.nanmean(w_des)
    w_incl = 1.0 / pi_map.loc[di.index].values.astype(float)
    est = ipw_wls(di[OUTCOME].astype(float).values, a, w_ipw * w_des * w_incl)
    return est, int((1 - d_mod["_incluido"]).sum()), float(np.mean(pi_map.loc[di.index]))


def _row(spec_id, label, work, est, boot=None, extra=None):
    rec = {
        "spec_id": spec_id,
        "etiqueta": label,
        "n": int(len(work)),
        "n_consumo": int(work[A_COL].sum()),
        "n_sin_consumo": int((1 - work[A_COL]).sum()),
        "prev_ajustada_consumo": est.get("mean_do1"),
        "prev_ajustada_sin_consumo": est.get("mean_do0"),
        "estimate": est["estimate"],
        "hc3_ci_low": est["ci_low"],
        "hc3_ci_high": est["ci_high"],
        "hc3_p": est["p_value"],
        "boot_ci_low": np.nan,
        "boot_ci_high": np.nan,
        "boot_n": 0,
        "inferencia": "HC3",
    }
    if boot is not None and len(boot) > 0:
        rec["boot_ci_low"] = float(np.percentile(boot, 2.5))
        rec["boot_ci_high"] = float(np.percentile(boot, 97.5))
        rec["boot_n"] = int(len(boot))
        rec["inferencia"] = "bootstrap percentil"
    if extra:
        rec.update(extra)
    return rec


def main() -> int:
    print("=" * 60)
    print(f"SENSIBILIDADES CUERPO — seed {SEED}  B={B_BOOT}  n_jobs={N_JOBS}")
    print("=" * 60)
    raw = pd.read_stata(DATA, convert_categoricals=False)
    df = prepare_raw(raw)

    specs_boot = []
    rows = []

    # 1. Principal: sin dx, 7d, missing=0 (equivale a T5>=1 actual), sin dpto
    pop_p, work_p, covs_p, nmiss_p = analytic_frame(
        df, require_no_dx=True, missing_as_zero=True, exposure="7d", include_dpto=False
    )
    est_p, a_p, w_ipw_p, w_des_p, _ = estimate_ipw_design(work_p, covs_p)
    print(
        f"Principal: n={len(work_p)} exp={int(work_p[A_COL].sum())} "
        f"RD={est_p['estimate']:.5f}  faltantes_toma_en_pop={nmiss_p}"
    )
    specs_boot.append(("principal", "Principal: receptores sin diagnóstico previo", work_p, covs_p, est_p, SEED + 1))

    bal = smd_table(work_p, a_p, w_ipw_p, covs_p)
    bal["abs_smd_post"] = bal["smd_post"].abs()
    bal["abs_smd_pre"] = bal["smd_pre"].abs()
    bal.to_csv(TAB / "tabla_S2_balance_smd_cuerpo.csv", index=False)

    # 2. Conservadora: + departamento
    _, work_d, covs_d, _ = analytic_frame(
        df, require_no_dx=True, missing_as_zero=True, exposure="7d", include_dpto=True
    )
    est_d, *_ = estimate_ipw_design(work_d, covs_d)
    print(f"Departamental: n={len(work_d)} RD={est_d['estimate']:.5f}")
    specs_boot.append(("departamental", "Con ajuste departamental", work_d, covs_d, est_d, SEED + 2))

    # 3. Sin restricción por diagnóstico
    _, work_u, covs_u, _ = analytic_frame(
        df, require_no_dx=False, missing_as_zero=True, exposure="7d", include_dpto=False
    )
    est_u, *_ = estimate_ipw_design(work_u, covs_u)
    print(f"Sin restricción: n={len(work_u)} exp={int(work_u[A_COL].sum())} RD={est_u['estimate']:.5f}")
    specs_boot.append(
        ("sin_restriccion", "Todos los receptores, sin restricción por diagnóstico", work_u, covs_u, est_u, SEED + 3)
    )

    # 4. Ventana alternativa real: consumo 12 meses
    _, work_12, covs_12, _ = analytic_frame(
        df, require_no_dx=True, missing_as_zero=True, exposure="12m", include_dpto=False
    )
    est_12, *_ = estimate_ipw_design(work_12, covs_12)
    print(f"Consumo 12 meses: n={len(work_12)} exp={int(work_12[A_COL].sum())} RD={est_12['estimate']:.5f}")
    specs_boot.append(
        ("consumo_12m", "Exposición alternativa: consumo reportado en 12 meses", work_12, covs_12, est_12, SEED + 4)
    )

    print(f"\n>>> Bootstrap estratificado B={B_BOOT} (solo anemia moderada o severa)")
    boot_map = {}
    for spec_id, label, work, covs, est, seed in specs_boot:
        print(f"  · {spec_id} ...", flush=True)
        arr = bootstrap_spec(work, covs, seed=seed, b=B_BOOT, n_jobs=N_JOBS)
        boot_map[spec_id] = arr
        print(f"    réplicas válidas={len(arr)}  IC=[{np.percentile(arr, 2.5):.5f}; {np.percentile(arr, 97.5):.5f}]")
        rows.append(_row(spec_id, label, work, est, boot=arr))

    # 5. Faltantes de exposición como missing (punto + HC3; bootstrap solo si n cambia)
    _, work_m, covs_m, nmiss_m = analytic_frame(
        df, require_no_dx=True, missing_as_zero=False, exposure="7d", include_dpto=False
    )
    est_m, *_ = estimate_ipw_design(work_m, covs_m)
    print(f"Faltantes como missing: n={len(work_m)} (vs {len(work_p)}) RD={est_m['estimate']:.5f} nmiss_pop={nmiss_m}")
    rows.append(
        _row(
            "faltantes_missing",
            "Faltantes de toma tratados como missing",
            work_m,
            est_m,
            extra={"n_faltantes_toma_pop": nmiss_m, "delta_vs_principal": est_m["estimate"] - est_p["estimate"]},
        )
    )

    # 6. Reponderación por caso completo (punto + HC3; ya casi idéntico)
    est_incl, n_excl, mean_pi = inclusion_reweight(pop_p, work_p, BASE_COVARIATES_CORE)
    print(f"Inclusión IPW: RD={est_incl['estimate']:.5f} n_excl={n_excl}")
    rows.append(
        _row(
            "inclusion_ipw",
            "Reponderación por probabilidad de caso completo",
            work_p,
            est_incl,
            extra={"n_excluidos_modelo": n_excl, "mean_pi_incluido": mean_pi},
        )
    )

    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_sensibilidades_cuerpo.csv", index=False)

    # Prevalencias del principal (ancla de Tabla 3 / resumen)
    prev = pd.DataFrame(
        [
            {
                "outcome": OUTCOME,
                "prev_ajustada_consumo": est_p["mean_do1"],
                "prev_ajustada_sin_consumo": est_p["mean_do0"],
                "diferencia_prevalencias": est_p["estimate"],
                "n": len(work_p),
                "n_consumo": int(work_p[A_COL].sum()),
                "n_sin_consumo": int((1 - work_p[A_COL]).sum()),
                "bootstrap_iterations": B_BOOT,
                "seed": SEED,
            }
        ]
    )
    prev.to_csv(TAB / "tabla_S_prevalencias_ajustadas_cuerpo.csv", index=False)

    summary = {
        "seed": SEED,
        "bootstrap_iterations": B_BOOT,
        "bootstrap_method": "stratified cluster (hv001 within hv022)",
        "n_jobs": N_JOBS,
        "rows": out.to_dict("records"),
        "max_abs_smd_principal": float(bal["abs_smd_post"].max()),
        "principal_matches_t5": bool(
            np.array_equal(
                work_p[A_COL].astype(int).values,
                (pd.to_numeric(df.loc[work_p.index, "T5"], errors="coerce") >= 1).astype(int).values,
            )
        ),
    }
    (TAB / "resumen_sensibilidades_cuerpo.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\nOK →", TAB / "tabla_sensibilidades_cuerpo.csv")
    print(out[["spec_id", "n", "n_consumo", "estimate", "boot_ci_low", "boot_ci_high"]].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
