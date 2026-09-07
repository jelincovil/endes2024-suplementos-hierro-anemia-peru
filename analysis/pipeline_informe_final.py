#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
PIPELINE FINAL — Inferencia causal aplicada (ENDES 2024)
Efecto del consumo efectivo de suplementos con hierro sobre la anemia infantil.
================================================================================

Genera TODAS las tablas (CSV) y figuras (PNG) del paper APA7 / Q1:
  - Primario: IPW × diseño ENDES con bootstrap estratificado por conglomerado.
  - Confirmatorio: IPW, AIPW, matching ATT (5 outcomes) en receptores sin dx previo.
  - Robustez: placebo, subsampling, E-value, trimming, PS logit vs GBM,
    leave-one-covariate-out, estratificación, MICE, T3-nulo.
  - Nuevas: flujo muestral, codebook exposición, positividad, Holm-Bonferroni,
    NNT, dosis-respuesta, overlap ATO, misclassification sim.

Fuente : ./anemia_valor.dta   (ENDES 2024; N = 14 428)
Semilla: 20260710
Salidas: tablas/*.csv , figuras/*.png

Ejecutar desde la raíz del proyecto:
    python pipeline_informe_final.py
================================================================================
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

# --- Portabilidad de consola -------------------------------------------------
# En Windows la consola por defecto es cp1252 y el pipeline imprime caracteres
# no-latin1 ("→", "≥", "±"). Sin esto, el proceso muere con UnicodeEncodeError
# a mitad de la corrida. No altera ningún cálculo.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.experimental import enable_iterative_imputer  # noqa: F401
from sklearn.impute import IterativeImputer, SimpleImputer
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.model_selection import KFold
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

warnings.filterwarnings("ignore")

# ================================================================== CONFIGURACIÓN
SEED = 20260710
RNG = np.random.default_rng(SEED)
np.random.seed(SEED)

# Raíz del paquete (…/anemia-endes-2023-main), no analysis/
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "anemia_valor.dta"
TAB = ROOT / "paper" / "tablas"
FIG = ROOT / "paper" / "figuras"
for p in (TAB, FIG):
    p.mkdir(parents=True, exist_ok=True)

ENDES_LABEL = "ENDES 2024"

plt.rcParams.update({"figure.dpi": 120, "font.size": 10, "savefig.bbox": "tight"})

# ---- Covariables: core (sin diarrea post-tratamiento) y extendida (con diarrea) ----
BASE_COVARIATES_CORE = [
    "edad_niño", "niña", "bajo_peso", "edad_madre", "educa_madre",
    "madre_anemia", "control_pren", "quintil", "agua_potable",
    "saneamiento", "area",
]
BASE_COVARIATES_WITH_DIARRHEA = BASE_COVARIATES_CORE + ["eda_14d_ant"]
# Por defecto, el PS se construye SIN diarrea (post-tratamiento)
BASE_COVARIATES = BASE_COVARIATES_CORE

CATEGORICAL = ["bajo_peso", "educa_madre", "quintil", "area"]
OUTCOMES = [
    ("anemia", "binary"),
    ("anemia_modsev", "binary"),
    ("hb_minsa", "continuous"),
    ("hb_oms", "continuous"),
    ("sev_anemia_score", "continuous"),
]
OUT_LABELS = {
    "anemia": "Anemia (RD)",
    "anemia_modsev": "Anemia moderada/severa (RD)",
    "hb_minsa": "Hemoglobina MINSA (g/L)",
    "hb_oms": "Hemoglobina OMS (g/L)",
    "sev_anemia_score": "Índice de severidad",
}

# ================================================================== UTILIDADES
def weighted_mean(x, w):
    """Media ponderada segura."""
    x, w = np.asarray(x, float), np.asarray(w, float)
    return float(np.sum(w * x) / np.sum(w))


def add_age_polys(d):
    """Añade polinomios centrados de edad al DataFrame."""
    d = d.copy()
    c = pd.to_numeric(d["edad_niño"], errors="coerce")
    c = c - c.mean()
    d["edad_niño_sq"] = c ** 2
    d["edad_niño_cu"] = c ** 3
    return d


def make_pre(covs):
    """Preprocesador: imputación simple + escalado numérico / one-hot cat."""
    cat = [c for c in CATEGORICAL if c in covs]
    num = [c for c in covs if c not in cat]
    return ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("sc", StandardScaler())]), num),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                              ("oh", OneHotEncoder(drop="first", handle_unknown="ignore"))]), cat),
        ],
        remainder="drop",
    )


def prepare_raw(raw):
    """Limpieza y derivación de variables desde el .dta crudo."""
    df = raw.copy()
    df["anemia"] = pd.to_numeric(df["anemia"], errors="coerce")
    df["anemia_modsev"] = (pd.to_numeric(df["niveles_anemia"], errors="coerce") == 2).astype(float)
    df["hb_minsa"] = pd.to_numeric(df["res_hemog_minsa"], errors="coerce")
    df["hb_oms"] = pd.to_numeric(df["res_hemog_oms"], errors="coerce")
    df["sev_anemia_score"] = pd.to_numeric(df["niveles_anemia"], errors="coerce")
    df["received_any"] = (
        (pd.to_numeric(df["T1"], errors="coerce").fillna(0) == 1)
        | (pd.to_numeric(df["n_recibidos"], errors="coerce").fillna(0) >= 1)
        | (pd.to_numeric(df["total_rec"], errors="coerce").fillna(0) > 0)
    ).astype(float)
    df["T3"] = pd.to_numeric(df["T3"], errors="coerce")
    df["T5_ge1"] = (pd.to_numeric(df["T5"], errors="coerce") >= 1).astype(float)
    # bajo_peso en el .dta es ordinal DHS (1/2/3); usar recode binario bajo_peso_r
    if "bajo_peso_r" in df.columns:
        df["bajo_peso"] = pd.to_numeric(df["bajo_peso_r"], errors="coerce")
    else:
        bp = pd.to_numeric(df["bajo_peso"], errors="coerce")
        df["bajo_peso"] = bp.map({1: 1.0, 2: 1.0, 3: 0.0})  # 1/2 ≈ sí; 3 ≈ no
    df["hv005_norm"] = pd.to_numeric(df["hv005"], errors="coerce") / 1e6
    df["upm"] = pd.to_numeric(df["hv001"], errors="coerce")
    df["estrato"] = pd.to_numeric(df["hv022"], errors="coerce")
    # Macro-región a partir de dpto (códigos INEI 1–25)
    if "dpto" in df.columns:
        df["dpto"] = pd.to_numeric(df["dpto"], errors="coerce")
        df["macro_region"] = df["dpto"].map(_macro_region_from_dpto)
    return df


# Costa / Sierra / Selva (agrupación estándar de departamentos INEI)
_DPTO_MACRO = {
    1: "selva", 2: "sierra", 3: "sierra", 4: "sierra", 5: "sierra",
    6: "sierra", 7: "costa", 8: "sierra", 9: "sierra", 10: "sierra",
    11: "costa", 12: "sierra", 13: "costa", 14: "costa", 15: "costa",
    16: "selva", 17: "selva", 18: "costa", 19: "sierra", 20: "costa",
    21: "sierra", 22: "selva", 23: "costa", 24: "costa", 25: "selva",
}


def _macro_region_from_dpto(code):
    try:
        return _DPTO_MACRO.get(int(code), "otro")
    except (TypeError, ValueError):
        return np.nan


def build_eligibility(df, require_received=True, require_no_dx=True):
    """
    Elegibilidad exportable (protocolo target trial).

    Criterios operativos (preespecificados):
      - Universo del archivo de análisis (niños con Hb en ENDES analítico)
      - received_any == 1  (receptores del programa) si require_received
      - dx_anemia == 0     (sin diagnóstico previo autorreportado del niño)
    No aplica complete-case aquí: eso es make_analytic_sample().
    """
    out = df.copy()
    out["_elig_received"] = (out["received_any"] == 1).astype(int)
    out["_elig_no_dx"] = (pd.to_numeric(out["dx_anemia"], errors="coerce") == 0).astype(int)
    mask = pd.Series(True, index=out.index)
    if require_received:
        mask &= out["_elig_received"] == 1
    if require_no_dx:
        mask &= out["_elig_no_dx"] == 1
    out["eligible"] = mask.astype(int)
    return out, mask


def make_analytic_sample(df, covariates=None, outcomes=None, include_design=True, include_dpto=False):
    """
    Muestra confirmatoria: elegibles + complete-case en covs/outcomes/diseño.
    Retorna (focus_pop, focus, covs_list).
    """
    covariates = list(covariates or BASE_COVARIATES_CORE)
    outcomes = outcomes or [y for y, _ in OUTCOMES]
    _, mask = build_eligibility(df, require_received=True, require_no_dx=True)
    focus_pop = df.loc[mask].copy()
    num_cols = list(dict.fromkeys(
        ["T5_ge1", "T5"] + outcomes + covariates + ["eda_14d_ant"]
        + (["hv005_norm", "upm", "estrato"] if include_design else [])
        + (["dpto"] if include_dpto and "dpto" in df.columns else [])
    ))
    num_cols = [c for c in num_cols if c in focus_pop.columns]
    focus = add_age_polys(focus_pop[num_cols].apply(pd.to_numeric, errors="coerce")).dropna().copy()
    if include_dpto and "macro_region" in focus_pop.columns:
        focus["macro_region"] = focus_pop.loc[focus.index, "macro_region"].values
        if "dpto" in focus_pop.columns:
            focus["dpto"] = pd.to_numeric(focus_pop.loc[focus.index, "dpto"], errors="coerce").values
    covs = [c for c in (covariates + ["edad_niño_sq", "edad_niño_cu"]) if c in focus.columns]
    return focus_pop, focus, covs


def fit_ps(df, covs, A_col="T5_ge1", model="logit"):
    """Ajusta propensity score (logit o GBM)."""
    A = df[A_col].astype(int).values
    clf = (LogisticRegression(max_iter=2000, solver="lbfgs") if model == "logit"
           else GradientBoostingClassifier(n_estimators=100, max_depth=3,
                                           learning_rate=0.05, random_state=SEED))
    pipe = Pipeline([("pre", make_pre(covs)), ("clf", clf)])
    pipe.fit(df[covs], A)
    return A, pipe.predict_proba(df[covs])[:, 1], pipe


def weights(A, ps, trim=(0.05, 0.95), estimand="ATE", cap=None):
    """Pesos IPW (ATE o ATT) con trimming y cap opcional."""
    ps = np.clip(ps, trim[0], trim[1])
    pA = A.mean()
    if estimand == "ATE":
        w = np.where(A == 1, pA / ps, (1 - pA) / (1 - ps))
    else:  # ATT
        w = np.where(A == 1, 1.0, ps / (1 - ps))
        w = np.where(A == 1, w / w[A == 1].mean(), w / w[A == 0].mean())
    if cap is not None:
        w = np.minimum(w, cap)
    return w


def overlap_weights_ato(A, ps):
    """Pesos de overlap (ATO): e(x) * (1 - e(x))."""
    ps = np.clip(ps, 1e-6, 1 - 1e-6)
    w = np.where(A == 1, 1 - ps, ps)
    w = w / w.sum() * len(A)
    return w


def ipw_wls(Y, A, w):
    """IPW via WLS con errores HC3."""
    X = sm.add_constant(pd.DataFrame({"A": A}))
    fit = sm.WLS(Y, X, weights=w).fit(cov_type="HC3")
    est, se, p = float(fit.params["A"]), float(fit.bse["A"]), float(fit.pvalues["A"])
    return {
        "estimate": est, "se": se,
        "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se,
        "p_value": p,
        "mean_do1": weighted_mean(Y[A == 1], w[A == 1]) if (A == 1).any() else np.nan,
        "mean_do0": weighted_mean(Y[A == 0], w[A == 0]) if (A == 0).any() else np.nan,
    }


def smd_table(df, A, w, covs):
    """Tabla de SMD pre/post ponderación."""
    rows = []
    for c in covs:
        if c in CATEGORICAL:
            levs = sorted(pd.Series(df[c].dropna().unique()).astype(float).tolist())
            for lev in levs[1:]:
                x = (df[c].values == lev).astype(float)
                rows.append({"covariable": f"{c}={lev:g}",
                             "smd_pre": _smd(x, A, None), "smd_post": _smd(x, A, w)})
        else:
            x = df[c].astype(float).values
            rows.append({"covariable": c, "smd_pre": _smd(x, A, None), "smd_post": _smd(x, A, w)})
    return pd.DataFrame(rows)


def _smd(x, A, w):
    """Diferencia media estandarizada (con o sin pesos)."""
    if w is None:
        m1, m0 = np.nanmean(x[A == 1]), np.nanmean(x[A == 0])
    else:
        m1, m0 = weighted_mean(x[A == 1], w[A == 1]), weighted_mean(x[A == 0], w[A == 0])
    s = np.sqrt((np.nanvar(x[A == 1], ddof=1) + np.nanvar(x[A == 0], ddof=1)) / 2)
    return float((m1 - m0) / s) if s > 0 else 0.0


def estimate_aipw(d, treatment, outcome, covs, otype, ps_model="logit"):
    """AIPW con cross-fitting 5-fold."""
    A = d[treatment].astype(int).values
    Y = d[outcome].astype(float).values
    n = len(d)
    mu1, mu0, ehat = np.zeros(n), np.zeros(n), np.zeros(n)
    for tr, te in KFold(5, shuffle=True, random_state=SEED).split(d):
        _, _, pipe = fit_ps(d.iloc[tr], covs, treatment, ps_model)
        ehat[te] = np.clip(pipe.predict_proba(d.iloc[te][covs])[:, 1], 0.05, 0.95)
        Xtr = d.iloc[tr][covs].copy(); Xtr["A"] = A[tr]
        X1 = d.iloc[te][covs].copy(); X1["A"] = 1
        X0 = d.iloc[te][covs].copy(); X0["A"] = 0
        yc = covs + ["A"]
        if otype == "binary":
            m = Pipeline([("pre", make_pre(yc)), ("logit", LogisticRegression(max_iter=2000))])
            m.fit(Xtr[yc], Y[tr].astype(int))
            mu1[te] = m.predict_proba(X1[yc])[:, 1]
            mu0[te] = m.predict_proba(X0[yc])[:, 1]
        else:
            m = Pipeline([("pre", make_pre(yc)), ("ridge", RidgeCV(alphas=[0.1, 1, 10, 100]))])
            m.fit(Xtr[yc], Y[tr])
            mu1[te] = m.predict(X1[yc])
            mu0[te] = m.predict(X0[yc])
    psi = (mu1 + A * (Y - mu1) / ehat) - (mu0 + (1 - A) * (Y - mu0) / (1 - ehat))
    est, se = float(psi.mean()), float(psi.std(ddof=1) / np.sqrt(n))
    p = float(2 * (1 - stats.norm.cdf(abs(est / se)))) if se > 0 else np.nan
    return {"estimate": est, "se": se, "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se, "p_value": p}


def evalue_rr(rr):
    """E-value a partir de RR."""
    if not np.isfinite(rr) or rr <= 0:
        return np.nan
    r = 1 / rr if rr < 1 else rr
    return float(r + np.sqrt(r * (r - 1)))


def matching_att(df, covs, outcome, caliper=0.2):
    """Matching ATT por propensity score (nearest-neighbour con caliper)."""
    A, ps, _ = fit_ps(df, covs, model="logit")
    ps = np.clip(ps, 1e-6, 1 - 1e-6)
    lg = np.log(ps / (1 - ps))
    cal = caliper * lg.std(ddof=1)
    tidx, cidx = np.where(A == 1)[0], np.where(A == 0)[0]
    nn = NearestNeighbors(n_neighbors=1).fit(lg[cidx].reshape(-1, 1))
    dist, ind = nn.kneighbors(lg[tidx].reshape(-1, 1))
    pairs, used = [], set()
    for i, t_i in enumerate(tidx):
        c_i = cidx[ind[i, 0]]
        if dist[i, 0] <= cal and c_i not in used:
            pairs.append((t_i, c_i))
            used.add(c_i)
    if len(pairs) < 50:
        return {"estimate": np.nan, "p_value": np.nan, "n_pairs": len(pairs)}
    yt = df.iloc[[p[0] for p in pairs]][outcome].astype(float).values
    yc = df.iloc[[p[1] for p in pairs]][outcome].astype(float).values
    d = yt - yc
    est, se = float(d.mean()), float(d.std(ddof=1) / np.sqrt(len(d)))
    p = float(2 * (1 - stats.norm.cdf(abs(est / se)))) if se > 0 else np.nan
    return {"estimate": est, "se": se, "ci_low": est - 1.96 * se, "ci_high": est + 1.96 * se,
            "p_value": p, "n_pairs": len(pairs), "caliper": float(cal)}


def holm_bonferroni(p_values, primary_idx=1):
    """
    Corrección de Holm-Bonferroni para 4 outcomes secundarios.
    primary_idx apunta a 'anemia_modsev' (índice 1 en OUTCOMES), que NO se corrige.
    Retorna lista del mismo largo que OUTCOMES con p corregida (o NaN para primario).
    """
    n = len(p_values)
    adjusted = [np.nan] * n
    secondary = [(i, p_values[i]) for i in range(n) if i != primary_idx]
    secondary_sorted = sorted(secondary, key=lambda x: (np.nan if x[1] is None else x[1]))
    m = len(secondary_sorted)
    # Holm: p ordenados crecientes; adjusted no-decreciente; arrancar en 0 (no en 1)
    prev = 0.0
    for rank, (orig_idx, p) in enumerate(secondary_sorted):
        if p is None or (isinstance(p, float) and np.isnan(p)):
            adjusted[orig_idx] = np.nan
            continue
        holm_p = min(float(p) * (m - rank), 1.0)
        holm_p = max(holm_p, prev)
        adjusted[orig_idx] = holm_p
        prev = holm_p
    return adjusted


def nnt(rd):
    """Number Needed to Treat = 1 / |RD|."""
    if rd is None or not np.isfinite(rd) or abs(rd) < 1e-10:
        return np.nan
    return float(np.ceil(1.0 / abs(rd)))


def mde_rd(n1, n0, p0, alpha=0.05, power=0.80):
    """
    Mínima diferencia detectable (RD) a dos colas para diferencia de proporciones
    (aproximación normal, sin cluster). Útil como cota inferior del MDE real.
    """
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    # bajo H0: p1=p0; se de la diferencia
    se0 = np.sqrt(p0 * (1 - p0) * (1 / n1 + 1 / n0))
    return float((z_a + z_b) * se0)


def inclusion_ipw_analysis(focus_pop, focus, covs_base, outcome="anemia_modsev"):
    """
    P2 — IPW de inclusión: P(caso completo | X) entre receptores sin dx previo.

    Nota: la exclusión a casos completos se debe casi solo a missing de
    `madre_anemia` (~202/205). El modelo de inclusión usa predictores con
    cobertura casi total (sin madre_anemia) para no colapsar la muestra
    de excluidos al hacer dropna.
    """
    pop = focus_pop.copy()
    pop["_incluido"] = pop.index.isin(focus.index).astype(int)

    # Predictores de selección disponibles también entre excluidos
    covs_incl = [c for c in covs_base if c != "madre_anemia" and c in pop.columns]
    need = covs_incl + ["_incluido", "T5_ge1", outcome, "hv005_norm"]
    # Traer edad etc. numéricos
    d_mod = pop[need].copy()
    for c in need:
        d_mod[c] = pd.to_numeric(d_mod[c], errors="coerce")
    d_mod = d_mod.dropna(subset=covs_incl + ["_incluido"])
    n_excl = int((1 - d_mod["_incluido"]).sum())
    n_incl = int(d_mod["_incluido"].sum())
    print(f"  Modelo inclusión: n_incl={n_incl}, n_excl={n_excl}, covs={covs_incl}")
    if n_incl < 100 or n_excl < 20:
        print("  Inclusión IPW: muestra insuficiente para modelar exclusión.")
        return pd.DataFrame()

    y_incl = d_mod["_incluido"].astype(int).values
    # Categóricas del subset de inclusión
    cat_incl = [c for c in CATEGORICAL if c in covs_incl]
    num_incl = [c for c in covs_incl if c not in cat_incl]
    pre = ColumnTransformer(
        [
            ("num", Pipeline([("imp", SimpleImputer(strategy="median")),
                              ("sc", StandardScaler())]), num_incl),
            ("cat", Pipeline([("imp", SimpleImputer(strategy="most_frequent")),
                              ("oh", OneHotEncoder(drop="first", handle_unknown="ignore"))]), cat_incl),
        ],
        remainder="drop",
    ) if cat_incl else Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())])

    if cat_incl:
        pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, solver="lbfgs"))])
        pipe.fit(d_mod[covs_incl], y_incl)
        pi = np.clip(pipe.predict_proba(d_mod[covs_incl])[:, 1], 0.05, 0.95)
    else:
        pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=2000, solver="lbfgs"))])
        pipe.fit(d_mod[covs_incl], y_incl)
        pi = np.clip(pipe.predict_proba(d_mod[covs_incl])[:, 1], 0.05, 0.95)

    # Efecto en incluidos reponderados por 1/π
    incl_mask = (d_mod["_incluido"] == 1) & d_mod[outcome].notna() & d_mod["T5_ge1"].notna()
    di = d_mod.loc[incl_mask].copy()
    # Re-adjuntar covariables de tratamiento desde focus (con madre_anemia)
    di = focus.loc[focus.index.intersection(di.index)].copy()
    pi_map = pd.Series(pi, index=d_mod.index)
    pi_incl = pi_map.loc[di.index].values.astype(float)
    w_incl = 1.0 / pi_incl

    covs = [c for c in (covs_base + ["edad_niño_sq", "edad_niño_cu"]) if c in di.columns]
    if "edad_niño_sq" not in di.columns:
        di = add_age_polys(di)
        covs = [c for c in (covs_base + ["edad_niño_sq", "edad_niño_cu"]) if c in di.columns]
    A, ps, _ = fit_ps(di, covs, "T5_ge1")
    w_ipw = weights(A, ps, estimand="ATE")
    Y = di[outcome].astype(float).values

    est_base = ipw_wls(Y, A, w_ipw)
    est_incl = ipw_wls(Y, A, w_ipw * w_incl)
    w_des = di["hv005_norm"].values
    w_des = w_des / np.nanmean(w_des)
    est_des = ipw_wls(Y, A, w_ipw * w_des)
    est_both = ipw_wls(Y, A, w_ipw * w_des * w_incl)

    rows = [
        {"modelo": "IPW tratamiento (base complete-case)", "ate": est_base["estimate"],
         "p": est_base["p_value"], "ci_low": est_base["ci_low"], "ci_high": est_base["ci_high"],
         "n": len(di), "mean_pi_incluido": float(np.mean(pi_incl)), "n_excluidos_modelo": n_excl},
        {"modelo": "IPW tratamiento × 1/P(incluido|X)", "ate": est_incl["estimate"],
         "p": est_incl["p_value"], "ci_low": est_incl["ci_low"], "ci_high": est_incl["ci_high"],
         "n": len(di), "mean_pi_incluido": float(np.mean(pi_incl)), "n_excluidos_modelo": n_excl},
        {"modelo": "IPW × diseño", "ate": est_des["estimate"],
         "p": est_des["p_value"], "ci_low": est_des["ci_low"], "ci_high": est_des["ci_high"],
         "n": len(di), "mean_pi_incluido": float(np.mean(pi_incl)), "n_excluidos_modelo": n_excl},
        {"modelo": "IPW × diseño × 1/P(incluido|X)", "ate": est_both["estimate"],
         "p": est_both["p_value"], "ci_low": est_both["ci_low"], "ci_high": est_both["ci_high"],
         "n": len(di), "mean_pi_incluido": float(np.mean(pi_incl)), "n_excluidos_modelo": n_excl},
    ]
    out = pd.DataFrame(rows)
    out["signo_protegido"] = out["ate"] < 0
    out["delta_vs_base"] = out["ate"] - est_base["estimate"]
    out.to_csv(TAB / "tabla_S_inclusion_ipw.csv", index=False)
    print(out[["modelo", "ate", "p", "signo_protegido"]].to_string(index=False))
    return out


def evalue_benchmark(focus, outcome="anemia_modsev"):
    """
    Benchmark del E-value con OR de confusores observados (educa_madre, quintil)
    sobre el desenlace primario (VanderWeele-style contextualization).
    """
    d = focus.copy()
    y = d[outcome].astype(float)
    rows = []

    # Quintil: alto (4-5) vs bajo (1)
    if "quintil" in d.columns:
        m = d["quintil"].isin([1, 4, 5])
        sub = d.loc[m].copy()
        sub["q_high"] = (sub["quintil"] >= 4).astype(int)
        X = sm.add_constant(sub[["q_high"]])
        try:
            fit = sm.Logit(sub[outcome].astype(float), X).fit(disp=0)
            or_ = float(np.exp(fit.params["q_high"]))
            rows.append({"confusor": "quintil 4-5 vs 1", "OR_outcome": or_,
                         "OR_away_from_1": max(or_, 1 / or_) if or_ > 0 else np.nan,
                         "p": float(fit.pvalues["q_high"]), "n": len(sub)})
        except Exception:
            pass

    # Educación materna: superior (max) vs resto si ordinal
    if "educa_madre" in d.columns:
        edu = pd.to_numeric(d["educa_madre"], errors="coerce")
        hi = edu.max()
        sub = d.loc[edu.notna()].copy()
        sub["edu_hi"] = (pd.to_numeric(sub["educa_madre"], errors="coerce") >= hi).astype(int)
        if sub["edu_hi"].sum() >= 30 and (1 - sub["edu_hi"]).sum() >= 30:
            X = sm.add_constant(sub[["edu_hi"]])
            try:
                fit = sm.Logit(sub[outcome].astype(float), X).fit(disp=0)
                or_ = float(np.exp(fit.params["edu_hi"]))
                rows.append({"confusor": f"educa_madre={int(hi)} vs resto", "OR_outcome": or_,
                             "OR_away_from_1": max(or_, 1 / or_) if or_ > 0 else np.nan,
                             "p": float(fit.pvalues["edu_hi"]), "n": len(sub)})
            except Exception:
                pass

    # Área urbana
    if "area" in d.columns:
        X = sm.add_constant(d[["area"]].astype(float))
        try:
            fit = sm.Logit(y, X).fit(disp=0)
            or_ = float(np.exp(fit.params["area"]))
            rows.append({"confusor": "area urbana vs rural", "OR_outcome": or_,
                         "OR_away_from_1": max(or_, 1 / or_) if or_ > 0 else np.nan,
                         "p": float(fit.pvalues["area"]), "n": len(d)})
        except Exception:
            pass

    # Madre anemia
    if "madre_anemia" in d.columns:
        sub = d.dropna(subset=["madre_anemia"])
        X = sm.add_constant(sub[["madre_anemia"]].astype(float))
        try:
            fit = sm.Logit(sub[outcome].astype(float), X).fit(disp=0)
            or_ = float(np.exp(fit.params["madre_anemia"]))
            rows.append({"confusor": "madre_anemia", "OR_outcome": or_,
                         "OR_away_from_1": max(or_, 1 / or_) if or_ > 0 else np.nan,
                         "p": float(fit.pvalues["madre_anemia"]), "n": len(sub)})
        except Exception:
            pass

    out = pd.DataFrame(rows)
    if len(out):
        out.to_csv(TAB / "tabla_S_evalue_benchmark.csv", index=False)
        print(out.to_string(index=False))
    return out


def population_impact(df, focus, rd_design, boot_ci_low, boot_ci_high):
    """
    Impacto poblacional escalado con pesos de diseño ENDES.
    Estima N ponderado de receptores sin dx sin consumo y casos prevenibles.
    """
    # Universo analítico: received_any=1, dx=0
    pop = df[
        (df["received_any"] == 1)
        & (pd.to_numeric(df["dx_anemia"], errors="coerce") == 0)
    ].copy()
    w = pop["hv005_norm"].astype(float)
    # Escala de pesos ENDES: sum(w) ≈ tamaño de población de referencia
    N_w_receivers_nodx = float(w.sum())
    # No consumidores entre ellos
    no_cons = (pd.to_numeric(pop["T5"], errors="coerce").fillna(0) < 1)
    N_w_no_cons = float(w[no_cons].sum())
    N_w_cons = float(w[~no_cons].sum())

    # Muestra confirmatoria cruda
    n_no_cons_sample = int((focus["T5_ge1"] == 0).sum())
    n_sample = len(focus)

    # Casos prevenibles si se convirtiera a todos los no-consumidores receptores
    # (bajo supuestos del modelo y generalización del RD de diseño)
    rd = float(rd_design)
    cases_point = abs(rd) * N_w_no_cons if np.isfinite(rd) else np.nan
    cases_lo = abs(float(boot_ci_high)) * N_w_no_cons  # |RD| menor si CI high más cerca de 0
    cases_hi = abs(float(boot_ci_low)) * N_w_no_cons

    # Referencia ~1.5e6 niños 6–35 m: aplicar share ponderada ENDES del grupo elegible sin consumo
    N_ref_lit = 1_500_000
    W_total = float(pd.to_numeric(df["hv005_norm"], errors="coerce").sum())
    share_nocons_w = N_w_no_cons / W_total if W_total > 0 else np.nan
    N_nocons_nat = N_ref_lit * share_nocons_w if np.isfinite(share_nocons_w) else np.nan
    cases_nat = abs(rd) * N_nocons_nat if np.isfinite(N_nocons_nat) else np.nan
    cases_nat_lo = abs(float(boot_ci_high)) * N_nocons_nat if np.isfinite(N_nocons_nat) else np.nan
    cases_nat_hi = abs(float(boot_ci_low)) * N_nocons_nat if np.isfinite(N_nocons_nat) else np.nan

    rows = [{
        "N_endes_muestra": 14428,
        "n_confirmatorio": n_sample,
        "n_no_consumo_muestra": n_no_cons_sample,
        "sum_hv005_norm_total": W_total,
        "N_ponderado_receptores_sin_dx": N_w_receivers_nodx,
        "N_ponderado_receptores_sin_dx_sin_consumo": N_w_no_cons,
        "N_ponderado_receptores_sin_dx_con_consumo": N_w_cons,
        "share_ponderada_no_consumo_elegible": share_nocons_w,
        "rd_diseno_modsev": rd,
        "boot_ci_low": float(boot_ci_low),
        "boot_ci_high": float(boot_ci_high),
        "casos_modsev_prevenibles_muestra_ponderada": cases_point,
        "casos_modsev_prevenibles_IC_low_muestra": min(cases_lo, cases_hi),
        "casos_modsev_prevenibles_IC_high_muestra": max(cases_lo, cases_hi),
        "nnt": nnt(rd),
        "N_ref_literatura_6_35m": N_ref_lit,
        "N_no_consumo_elegible_escala_1_5M": N_nocons_nat,
        "casos_modsev_prevenibles_escala_1_5M": cases_nat,
        "casos_IC_low_escala_1_5M": min(cases_nat_lo, cases_nat_hi) if np.isfinite(cases_nat_lo) else np.nan,
        "casos_IC_high_escala_1_5M": max(cases_nat_lo, cases_nat_hi) if np.isfinite(cases_nat_lo) else np.nan,
        "nota": "Escenario 1.5M = share ponderada ENDES de receptores sin dx sin consumo × 1.5e6 × |RD|.",
    }]
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_impacto_poblacional.csv", index=False)
    print(out[["share_ponderada_no_consumo_elegible", "N_no_consumo_elegible_escala_1_5M",
               "casos_modsev_prevenibles_escala_1_5M", "nnt"]].to_string(index=False))
    return out


def power_mde_table(focus, outcome="anemia_modsev"):
    """MDE al 80% y poder post-hoc para el RD primario (aproximación iid)."""
    A = focus["T5_ge1"].astype(int).values
    Y = focus[outcome].astype(float).values
    n1, n0 = int(A.sum()), int((1 - A).sum())
    p0 = float(Y[A == 0].mean())
    p1 = float(Y[A == 1].mean())
    rd_obs = p1 - p0
    mde80 = mde_rd(n1, n0, p0, alpha=0.05, power=0.80)
    # poder post-hoc para RD observado (crudo)
    se = np.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
    z = abs(rd_obs) / se if se > 0 else np.nan
    power_post = float(stats.norm.cdf(z - stats.norm.ppf(0.975)) +
                       stats.norm.cdf(-z - stats.norm.ppf(0.975))) if se > 0 else np.nan
    # también reportar MDE relativo al control
    out = pd.DataFrame([{
        "outcome": outcome,
        "n_treated": n1,
        "n_control": n0,
        "p0_control": p0,
        "p1_treated_crude": p1,
        "rd_crude": rd_obs,
        "mde_80pct_alpha05": mde80,
        "power_posthoc_crude_rd": power_post,
        "nota": "Aprox. iid (sin cluster); MDE real con diseño suele ser mayor.",
    }])
    out.to_csv(TAB / "tabla_S_mde_poder.csv", index=False)
    print(out.to_string(index=False))
    return out


def heterogeneity_dpto_macro(df, focus, covs, outcome="anemia_modsev"):
    """Heterogeneidad por macro-región (costa/sierra/selva) y top dptos con n suficiente."""
    rows = []
    # Asegurar macro en focus
    if "macro_region" not in focus.columns and "dpto" in df.columns:
        focus = focus.copy()
        focus["macro_region"] = df.loc[focus.index, "macro_region"]
        focus["dpto"] = pd.to_numeric(df.loc[focus.index, "dpto"], errors="coerce")

    if "macro_region" in focus.columns:
        for reg, g in focus.groupby("macro_region"):
            if reg is None or (isinstance(reg, float) and np.isnan(reg)):
                continue
            g = add_age_polys(g.copy())
            if g["T5_ge1"].sum() < 80 or (1 - g["T5_ge1"]).sum() < 80:
                rows.append({"estrato_tipo": "macro_region", "estrato": reg, "n": len(g),
                             "n_t": int(g["T5_ge1"].sum()), "ipw_ate": np.nan, "ipw_p": np.nan,
                             "nnt": np.nan, "nota": "n insuficiente"})
                continue
            try:
                Ag, psg, _ = fit_ps(g, covs)
                wg = weights(Ag, psg, estimand="ATE")
                est = ipw_wls(g[outcome].astype(float).values, Ag, wg)
                rows.append({"estrato_tipo": "macro_region", "estrato": reg, "n": len(g),
                             "n_t": int(g["T5_ge1"].sum()), "ipw_ate": est["estimate"],
                             "ipw_p": est["p_value"], "nnt": nnt(est["estimate"]), "nota": ""})
            except Exception as e:
                rows.append({"estrato_tipo": "macro_region", "estrato": reg, "n": len(g),
                             "n_t": int(g["T5_ge1"].sum()), "ipw_ate": np.nan, "ipw_p": np.nan,
                             "nnt": np.nan, "nota": str(e)[:80]})

    # Interacciones formales: outcome ~ A + Z + A*Z con PS-IPW residualizado vía WLS en muestra completa
    # Test de interacción en modelo lineal de outcome con A, Z, A×Z sin re-PS por simplicidad
    # (exploratorio; reportado como tal)
    inter_rows = []
    for zname, zcol in [("area", "area"), ("quintil_alto", None), ("macro_sierra", None)]:
        d = focus.copy()
        if zname == "quintil_alto":
            d["z"] = (pd.to_numeric(d["quintil"], errors="coerce") >= 4).astype(float)
            label = "quintil_4_5"
        elif zname == "macro_sierra":
            if "macro_region" not in d.columns:
                continue
            d["z"] = (d["macro_region"] == "sierra").astype(float)
            label = "macro_sierra_vs_resto"
        else:
            d["z"] = pd.to_numeric(d[zcol], errors="coerce")
            label = zname
        d = d.dropna(subset=["T5_ge1", outcome, "z"])
        if d["z"].nunique() < 2:
            continue
        A = d["T5_ge1"].astype(float).values
        Z = d["z"].astype(float).values
        Y = d[outcome].astype(float).values
        X = pd.DataFrame({"A": A, "Z": Z, "AZ": A * Z})
        X = sm.add_constant(X)
        try:
            fit = sm.OLS(Y, X).fit(cov_type="HC3")
            inter_rows.append({
                "moderador": label,
                "coef_A": float(fit.params["A"]),
                "coef_Z": float(fit.params["Z"]),
                "coef_AxZ": float(fit.params["AZ"]),
                "p_interaccion": float(fit.pvalues["AZ"]),
                "n": len(d),
                "nota": "OLS HC3 exploratorio (no IPW); test de heterogeneidad",
            })
        except Exception:
            continue

    het = pd.DataFrame(rows)
    het.to_csv(TAB / "tabla_S_heterogeneidad_dpto.csv", index=False)
    inter = pd.DataFrame(inter_rows)
    inter.to_csv(TAB / "tabla_S_interacciones.csv", index=False)
    print("  Macro-regiones:", het.to_string(index=False) if len(het) else "(vacío)")
    print("  Interacciones:", inter.to_string(index=False) if len(inter) else "(vacío)")
    return het, inter


def nnt_by_subgroup(focus, covs, outcome="anemia_modsev"):
    """NNT por subgrupos preespecificados (área, quintil, edad)."""
    focus = focus.copy()
    focus["edad_grp"] = pd.cut(focus["edad_niño"], [5, 11, 23, 35, 60],
                               labels=["6-11", "12-23", "24-35", "36+"])
    focus["quintil_alto"] = (focus["quintil"] >= 4).astype(int)
    strata = [
        ("total", focus.index == focus.index),
        ("urbano", focus.area == 1),
        ("rural", focus.area == 0),
        ("quintil_4_5", focus.quintil_alto == 1),
        ("quintil_1_3", focus.quintil_alto == 0),
        ("edad_6_11", focus.edad_grp == "6-11"),
        ("edad_12_23", focus.edad_grp == "12-23"),
        ("edad_24_35", focus.edad_grp == "24-35"),
    ]
    rows = []
    for lab, mask in strata:
        d = add_age_polys(focus.loc[mask].copy())
        if d["T5_ge1"].sum() < 50 or (1 - d["T5_ge1"]).sum() < 50:
            continue
        try:
            Ad, psd, _ = fit_ps(d, covs)
            wd = weights(Ad, psd, estimand="ATE")
            est = ipw_wls(d[outcome].astype(float).values, Ad, wd)
            rows.append({"subgrupo": lab, "n": len(d), "n_t": int(d["T5_ge1"].sum()),
                         "ipw_ate": est["estimate"], "ipw_p": est["p_value"],
                         "nnt": nnt(est["estimate"])})
        except Exception:
            continue
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_nnt_subgrupos.csv", index=False)
    print(out.to_string(index=False))
    return out


def pate_like_exploratory(df, covs_base, outcome="anemia_modsev"):
    """
    Análisis exploratorio tipo PATE muestral: todos los niños con complete-case,
    sin filtrar por received_any (tratamiento = T5≥1 vs 0).
    Contrasta con SATE en receptores sin dx.
    """
    cols = list(dict.fromkeys(
        ["T5_ge1", "T5", "received_any", "dx_anemia", "hv005_norm"]
        + [outcome] + covs_base
    ))
    cols = [c for c in cols if c in df.columns]
    d = add_age_polys(df[cols].apply(pd.to_numeric, errors="coerce")).dropna().copy()
    covs = [c for c in (covs_base + ["edad_niño_sq", "edad_niño_cu"]) if c in d.columns]
    rows = []
    # PATE-like full sample
    A, ps, _ = fit_ps(d, covs)
    w = weights(A, ps, estimand="ATE")
    est = ipw_wls(d[outcome].astype(float).values, A, w)
    rows.append({"muestra": "todos_complete_case (PATE-like)", "n": len(d),
                 "n_t": int(d["T5_ge1"].sum()), "ipw_ate": est["estimate"],
                 "ipw_p": est["p_value"], "nota": "exploratorio; posible colisionador/selección"})
    # Solo no-receptores (si hay tratados entre ellos — normalmente T5=0)
    d_nr = d[d["received_any"] == 0]
    if d_nr["T5_ge1"].sum() >= 30 and (1 - d_nr["T5_ge1"]).sum() >= 30:
        An, psn, _ = fit_ps(d_nr, covs)
        wn = weights(An, psn, estimand="ATE")
        estn = ipw_wls(d_nr[outcome].astype(float).values, An, wn)
        rows.append({"muestra": "no_receptores", "n": len(d_nr),
                     "n_t": int(d_nr["T5_ge1"].sum()), "ipw_ate": estn["estimate"],
                     "ipw_p": estn["p_value"], "nota": "exploratorio"})
    # Receptores con dx (ampliada)
    d_dx = d[(d["received_any"] == 1) & (d["dx_anemia"] == 1)]
    if len(d_dx) >= 200 and d_dx["T5_ge1"].sum() >= 30:
        # incluir dx como covariable no aplica (constante); solo IPW
        Adx, psdx, _ = fit_ps(d_dx, covs)
        wdx = weights(Adx, psdx, estimand="ATE")
        estdx = ipw_wls(d_dx[outcome].astype(float).values, Adx, wdx)
        rows.append({"muestra": "receptores_con_dx_previo", "n": len(d_dx),
                     "n_t": int(d_dx["T5_ge1"].sum()), "ipw_ate": estdx["estimate"],
                     "ipw_p": estdx["p_value"], "nota": "sensibilidad; dx endógeno"})
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_pate_exploratorio.csv", index=False)
    print(out.to_string(index=False))
    return out


def design_weighted_ps_sensitivity(focus, covs, outcome="anemia_modsev"):
    """
    Sensibilidad: PS logit ponderado por hv005_norm (survey-weighted PS aproximado)
    y luego IPW×diseño sobre el primario.
    """
    d = focus.copy()
    A = d["T5_ge1"].astype(int).values
    w_surv = d["hv005_norm"].astype(float).values
    w_surv = np.clip(w_surv, 1e-8, None)
    # sample weights for logistic via sklearn: no nativo fácil; usar statsmodels GLM binomial
    try:
        from sklearn.utils.class_weight import compute_sample_weight
        # reescalar pesos de diseño como sample_weight
        sw = w_surv / w_surv.mean()
        pre = make_pre(covs)
        X = pre.fit_transform(d[covs])
        # dense
        if hasattr(X, "toarray"):
            X = X.toarray()
        clf = LogisticRegression(max_iter=2000, solver="lbfgs")
        clf.fit(X, A, sample_weight=sw)
        ps = np.clip(clf.predict_proba(X)[:, 1], 0.05, 0.95)
        w_ipw = weights(A, ps, estimand="ATE")
        w_des = w_surv / np.nanmean(w_surv)
        est_ipw = ipw_wls(d[outcome].astype(float).values, A, w_ipw)
        est_des = ipw_wls(d[outcome].astype(float).values, A, w_ipw * w_des)
        out = pd.DataFrame([
            {"modelo": "PS survey-weighted + IPW", "ate": est_ipw["estimate"],
             "p": est_ipw["p_value"], "ci_low": est_ipw["ci_low"], "ci_high": est_ipw["ci_high"]},
            {"modelo": "PS survey-weighted + IPW×diseño", "ate": est_des["estimate"],
             "p": est_des["p_value"], "ci_low": est_des["ci_low"], "ci_high": est_des["ci_high"]},
        ])
    except Exception as e:
        out = pd.DataFrame([{"modelo": "error", "ate": np.nan, "p": np.nan,
                             "ci_low": np.nan, "ci_high": np.nan, "nota": str(e)[:120]}])
    out.to_csv(TAB / "tabla_S_ps_survey_weighted.csv", index=False)
    print(out.to_string(index=False))
    return out


def worst_case_scenarios(rd_design, boot_lo, boot_hi, e_value, nnt_val):
    """Tabla de peores escenarios y recomendaciones condicionales (para paper)."""
    rows = [
        {
            "escenario": "Estimación puntual (IPW×diseño)",
            "RD_modsev": rd_design,
            "implicacion": f"NNT≈{nnt_val}; efecto protector modesto de implementación",
            "recomendacion_condicional": "Priorizar indicadores de consumo reportado, no solo entrega",
        },
        {
            "escenario": "Límite inferior del IC bootstrap (efecto más débil)",
            "RD_modsev": boot_hi,  # closer to 0 if negative effect
            "implicacion": "Si el efecto real está en el borde del IC, magnitud poblacional cae ~60%",
            "recomendacion_condicional": "No escalar políticas solo con el punto; usar rango del IC",
        },
        {
            "escenario": "Límite superior del IC (efecto más fuerte)",
            "RD_modsev": boot_lo,
            "implicacion": "Mejor caso bajo incertidumbre muestral; sigue siendo <3–5 pp",
            "recomendacion_condicional": "Aun en mejor caso, no sustituye RCTs de eficacia con adherencia controlada",
        },
        {
            "escenario": f"Confusor no medido con RR≥E-value ({e_value:.2f})",
            "RD_modsev": 0.0,
            "implicacion": "El efecto puntual podría anularse (dieta, parasitosis, literacidad en salud)",
            "recomendacion_condicional": "Triangular con indicadores de dieta/parasitosis en futuras ENDES",
        },
        {
            "escenario": "Mala clasificación no diferencial de exposición",
            "RD_modsev": np.nan,
            "implicacion": "Sesgo hacia el nulo; el RD observado es cota inferior de adherencia real",
            "recomendacion_condicional": "Invertir en medición de consumo (registros, sachet count) no solo auto-reporte",
        },
    ]
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_peores_escenarios.csv", index=False)
    return out


# ================================================================== MEJORAS REPO-ONLY (post meta 95)
def lee_bounds_selection(focus_pop, focus, outcome="anemia_modsev", treatment="T5_ge1"):
    """
    Cotas de Lee (2009) bajo selección diferencial a casos completos.

    Entre receptores sin dx (focus_pop), S = incluido en muestra confirmatoria.
    Si P(S=1|A) difiere entre brazos, se recorta el brazo con mayor tasa de
    observación y se acotan E[Y|A=1,S=1] − E[Y|A=0,S=1] (RD sobre anemia).
    Sensibilidad de selección; no reemplaza el primario.
    """
    pop = focus_pop.copy()
    pop["_S"] = pop.index.isin(focus.index).astype(int)
    need = [treatment, outcome, "_S"]
    d = pop[[c for c in need if c in pop.columns]].apply(pd.to_numeric, errors="coerce")
    d = d.dropna(subset=[treatment, "_S"])
    A = d[treatment].astype(int)
    S = d["_S"].astype(int)
    p1 = float(S[A == 1].mean()) if (A == 1).sum() else np.nan
    p0 = float(S[A == 0].mean()) if (A == 0).sum() else np.nan
    obs = focus[[treatment, outcome]].apply(pd.to_numeric, errors="coerce").dropna()
    y1 = obs.loc[obs[treatment] == 1, outcome].astype(float).values
    y0 = obs.loc[obs[treatment] == 0, outcome].astype(float).values
    if len(y1) < 50 or len(y0) < 50 or not np.isfinite(p1) or not np.isfinite(p0) or max(p1, p0) <= 0:
        out = pd.DataFrame([{"metodo": "Lee bounds", "nota": "muestra insuficiente", "ate_point": np.nan}])
        out.to_csv(TAB / "tabla_S_lee_bounds.csv", index=False)
        return out

    rd_raw = float(y1.mean() - y0.mean())
    p_lo, p_hi = min(p1, p0), max(p1, p0)
    keep_frac = p_lo / p_hi if p_hi > 0 else 1.0
    trim_frac = 1.0 - keep_frac

    def _trimmed_mean(y, keep, which="lower"):
        y = np.sort(np.asarray(y, dtype=float))
        n = len(y)
        k = max(int(np.floor(n * keep)), 1)
        if which == "lower":
            return float(y[:k].mean())
        return float(y[-k:].mean())

    if p1 >= p0:
        mu1_lo = _trimmed_mean(y1, keep_frac, "lower")
        mu1_hi = _trimmed_mean(y1, keep_frac, "upper")
        mu0 = float(y0.mean())
        bound_lo, bound_hi = mu1_lo - mu0, mu1_hi - mu0
        trimmed_arm = "tratados"
    else:
        mu0_lo = _trimmed_mean(y0, keep_frac, "lower")
        mu0_hi = _trimmed_mean(y0, keep_frac, "upper")
        mu1 = float(y1.mean())
        bound_lo, bound_hi = mu1 - mu0_hi, mu1 - mu0_lo
        trimmed_arm = "controles"

    lo, hi = (bound_lo, bound_hi) if bound_lo <= bound_hi else (bound_hi, bound_lo)
    rows = [{
        "metodo": "Lee_2009_selection",
        "outcome": outcome,
        "p_S_treated": p1,
        "p_S_control": p0,
        "trim_frac": trim_frac,
        "keep_frac": keep_frac,
        "trimmed_arm": trimmed_arm,
        "rd_selected_raw": rd_raw,
        "lee_bound_low": lo,
        "lee_bound_high": hi,
        "interval_covers_zero": bool(lo <= 0 <= hi),
        "n_treated_obs": int(len(y1)),
        "n_control_obs": int(len(y0)),
        "nota": "Cotas bajo monotonía de selección; RD crudo en seleccionados (no IPW).",
    }]
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_lee_bounds.csv", index=False)
    print(out[["p_S_treated", "p_S_control", "trim_frac", "lee_bound_low", "lee_bound_high",
               "interval_covers_zero"]].to_string(index=False))
    return out


def mediation_diarrhea_analysis(focus, covs, outcome="anemia_modsev"):
    """
    Mediación exploratoria: diarrea 14d como mediador post-exposición.
    TE = IPW; CDE = WLS Y~A+M con pesos IPW; NIE≈TE−CDE (diferencia, no g-fórmula).
    """
    d = focus.copy()
    if "eda_14d_ant" not in d.columns:
        out = pd.DataFrame([{"nota": "eda_14d_ant ausente"}])
        out.to_csv(TAB / "tabla_S_mediacion_diarrea.csv", index=False)
        return out
    keep_covs = [c for c in covs if c in d.columns]
    d = d.dropna(subset=[outcome, "T5_ge1", "eda_14d_ant"] + keep_covs)
    A, ps, _ = fit_ps(d, keep_covs, model="logit")
    w = weights(A, ps, estimand="ATE")
    Y = d[outcome].astype(float).values
    M = d["eda_14d_ant"].astype(float).values
    te = ipw_wls(Y, A, w)
    X = sm.add_constant(np.column_stack([A.astype(float), M]))
    try:
        fit = sm.WLS(Y, X, weights=w).fit(cov_type="HC3")
        cde = float(np.asarray(fit.params).ravel()[1])
        cde_p = float(np.asarray(fit.pvalues).ravel()[1])
        ci = np.asarray(fit.conf_int())
        cde_lo = float(ci[1, 0])
        cde_hi = float(ci[1, 1])
    except Exception as e:
        print(f"  CDE WLS falló: {e}")
        cde, cde_p, cde_lo, cde_hi = np.nan, np.nan, np.nan, np.nan
    tm = ipw_wls(M, A, w)
    nie_approx = te["estimate"] - cde if np.isfinite(cde) else np.nan
    prop_mediated = (
        nie_approx / te["estimate"]
        if (np.isfinite(nie_approx) and abs(te["estimate"]) > 1e-8)
        else np.nan
    )
    rows = [
        {"estimando": "TE_IPW (total)", "estimate": te["estimate"], "p_value": te["p_value"],
         "ci_low": te["ci_low"], "ci_high": te["ci_high"], "nota": "PS sin diarrea"},
        {"estimando": "CDE_WLS (directo controlado A|M)", "estimate": cde, "p_value": cde_p,
         "ci_low": cde_lo, "ci_high": cde_hi, "nota": "Y~A+M con pesos IPW; exploratorio"},
        {"estimando": "NIE_approx (TE-CDE)", "estimate": nie_approx, "p_value": np.nan,
         "ci_low": np.nan, "ci_high": np.nan, "nota": "aproximación diferencia; no g-fórmula"},
        {"estimando": "T_to_M (IPW diarrea)", "estimate": tm["estimate"], "p_value": tm["p_value"],
         "ci_low": tm["ci_low"], "ci_high": tm["ci_high"], "nota": "efecto exposición→mediador"},
        {"estimando": "prop_mediada_approx", "estimate": prop_mediated, "p_value": np.nan,
         "ci_low": np.nan, "ci_high": np.nan, "nota": "NIE/TE aproximado"},
    ]
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_mediacion_diarrea.csv", index=False)
    print(out[["estimando", "estimate", "p_value"]].to_string(index=False))
    return out


def transport_weights_analysis(df, focus, covs_base, outcome="anemia_modsev"):
    """
    Pesos de transporte (IOSW-like) del SATE confirmatorio hacia el universo
    complete-case ENDES. Exploratorio; complementa PATE-like.
    """
    cols = list(dict.fromkeys(
        ["T5_ge1", outcome, "hv005_norm", "received_any", "dx_anemia"] + list(covs_base)
    ))
    cols = [c for c in cols if c in df.columns]
    univ = add_age_polys(df[cols].apply(pd.to_numeric, errors="coerce")).dropna().copy()
    univ["_S"] = univ.index.isin(focus.index).astype(int)
    covs = [c for c in (list(covs_base) + ["edad_niño_sq", "edad_niño_cu"]) if c in univ.columns]
    y_s = univ["_S"].astype(int).values
    if y_s.sum() < 100 or (1 - y_s).sum() < 50:
        out = pd.DataFrame([{"nota": "universo insuficiente para transporte"}])
        out.to_csv(TAB / "tabla_S_transporte.csv", index=False)
        return out
    pre = make_pre(covs)
    Xs = pre.fit_transform(univ[covs])
    if hasattr(Xs, "toarray"):
        Xs = Xs.toarray()
    clf = LogisticRegression(max_iter=2000, solver="lbfgs")
    clf.fit(Xs, y_s)
    pi_s = np.clip(clf.predict_proba(Xs)[:, 1], 0.05, 0.95)
    p_s = float(y_s.mean())
    mask_s = univ["_S"] == 1
    d = univ.loc[mask_s].copy()
    pi = pi_s[mask_s]
    w_tr = (p_s / pi)
    w_tr = w_tr / np.mean(w_tr)
    A, ps, _ = fit_ps(d, covs, model="logit")
    w_ipw = weights(A, ps, estimand="ATE")
    Y = d[outcome].astype(float).values
    est_base = ipw_wls(Y, A, w_ipw)
    est_tr = ipw_wls(Y, A, w_ipw * w_tr)
    w_des = d["hv005_norm"].values.astype(float)
    w_des = w_des / np.nanmean(w_des)
    est_tr_des = ipw_wls(Y, A, w_ipw * w_tr * w_des)
    rows = [
        {"modelo": "IPW SATE confirmatorio (ref)", "n": int(len(d)), "n_universo": int(len(univ)),
         "ate": est_base["estimate"], "p": est_base["p_value"],
         "ci_low": est_base["ci_low"], "ci_high": est_base["ci_high"]},
        {"modelo": "IPW × transporte (IOSW-like)", "n": int(len(d)), "n_universo": int(len(univ)),
         "ate": est_tr["estimate"], "p": est_tr["p_value"],
         "ci_low": est_tr["ci_low"], "ci_high": est_tr["ci_high"]},
        {"modelo": "IPW × transporte × diseño", "n": int(len(d)), "n_universo": int(len(univ)),
         "ate": est_tr_des["estimate"], "p": est_tr_des["p_value"],
         "ci_low": est_tr_des["ci_low"], "ci_high": est_tr_des["ci_high"]},
    ]
    out = pd.DataFrame(rows)
    out["delta_vs_sate"] = out["ate"] - est_base["estimate"]
    out.to_csv(TAB / "tabla_S_transporte.csv", index=False)
    print(out[["modelo", "ate", "p", "delta_vs_sate"]].to_string(index=False))
    return out


def sandwich_survey_se(focus, covs, outcome="anemia_modsev"):
    """SE cluster-robusto (sandwich) por UPM del IPW×diseño (sensibilidad al bootstrap)."""
    d = focus.copy()
    A, ps, _ = fit_ps(d, covs, model="logit")
    w_ipw = weights(A, ps, estimand="ATE")
    w_des = d["hv005_norm"].astype(float).values
    w_des = w_des / np.nanmean(w_des)
    w = w_ipw * w_des
    Y = d[outcome].astype(float).values
    X = sm.add_constant(A.astype(float))
    try:
        groups = d["upm"].values if "upm" in d.columns else d["hv001"].values
        fit = sm.WLS(Y, X, weights=w).fit(cov_type="cluster", cov_kwds={"groups": groups})
        params = np.asarray(fit.params).ravel()
        bse = np.asarray(fit.bse).ravel()
        pvals = np.asarray(fit.pvalues).ravel()
        ci = np.asarray(fit.conf_int())
        row = {
            "outcome": outcome,
            "estimate": float(params[1]),
            "se_cluster": float(bse[1]),
            "p_cluster": float(pvals[1]),
            "ci_low": float(ci[1, 0]),
            "ci_high": float(ci[1, 1]),
            "n_clusters": int(pd.Series(groups).nunique()),
            "metodo": "WLS IPW×diseño + SE cluster(hv001)",
        }
    except Exception as e:
        row = {"outcome": outcome, "estimate": np.nan, "nota": str(e)[:160]}
    out = pd.DataFrame([row])
    out.to_csv(TAB / "tabla_S_sandwich_survey.csv", index=False)
    print(out.to_string(index=False))
    return out


def literature_comparison_table():
    """Tabla comparativa de anclas de literatura ya citadas (cobertura vs consumo)."""
    rows = [
        {
            "fuente": "Este estudio (ENDES 2024, IPW×diseño)",
            "tipo": "observacional causal / implementación",
            "exposicion": "Consumo reportado T5≥1 entre receptores sin dx",
            "desenlace": "Anemia mod/sev (RD)",
            "magnitud": "RD≈−0.028; NNT≈36; E-value 1.69",
            "mensaje": "Brecha entrega→consumo; no eficacia farmacológica",
        },
        {
            "fuente": "ENDES 2024 / INEI (prevalencia)",
            "tipo": "encuesta nacional",
            "exposicion": "—",
            "desenlace": "Anemia 6–35 m",
            "magnitud": "≈36.6% prevalencia",
            "mensaje": "Carga alta; justifica evaluación programática",
        },
        {
            "fuente": "WHO iron supplementation guidelines",
            "tipo": "guía / síntesis",
            "exposicion": "Suplementación con hierro en lactantes/niños",
            "desenlace": "Anemia / Hb",
            "magnitud": "Eficacia esperable con adherencia supervisada",
            "mensaje": "Benchmark de eficacia ≠ implementación en campo",
        },
        {
            "fuente": "Low et al. / Neuberger et al. (síntesis RCTs hierro)",
            "tipo": "revisión / meta-análisis (citados)",
            "exposicion": "Hierro en ensayos",
            "desenlace": "Hb / anemia",
            "magnitud": "Efectos Hb típicamente > error HemoCue con adherencia",
            "mensaje": "Contraste: aquí Hb +0.07 g/dL clínicamente nula",
        },
        {
            "fuente": "Munares et al. (programa Perú, cit.)",
            "tipo": "evaluación nacional / implementación",
            "exposicion": "Cobertura y prácticas de suplementación",
            "desenlace": "Proceso / cobertura",
            "magnitud": "Énfasis en entrega; validación de auto-reporte limitada",
            "mensaje": "Ancla de error de clasificación y brecha de proceso",
        },
        {
            "fuente": "MINSA normas de suplementación",
            "tipo": "normativa",
            "exposicion": "Gotas / jarabe / MNP",
            "desenlace": "Indicadores de programa",
            "magnitud": "Indicadores históricos centrados en entrega",
            "mensaje": "Política: migrar a consumo + resultado hematológico",
        },
    ]
    out = pd.DataFrame(rows)
    out.to_csv(TAB / "tabla_S_literatura_comparativa.csv", index=False)
    return out


# ================================================================== NUEVAS FUNCIONALIDADES

def document_treatment_construction(df):
    """
    P0.5 — Codebook de construcción de exposición.
    Imprime y guarda frecuencias, cross-tabs y definiciones en codebook_exposicion.csv.
    """
    print("\n===== CODEBOOK: CONSTRUCCIÓN DE EXPOSICIÓN =====")

    expo_vars = ["T1", "T2", "T3", "T4", "T5", "n_consumidos", "n_recibidos", "total_toma", "total_rec"]
    records = []

    for v in expo_vars:
        if v not in df.columns:
            continue
        col = pd.to_numeric(df[v], errors="coerce")
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "n",
                        "valor": int(col.notna().sum())})
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "n_missing",
                        "valor": int(col.isna().sum())})
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "mean",
                        "valor": float(round(col.mean(), 4))})
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "sd",
                        "valor": float(round(col.std(ddof=1), 4))})
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "min",
                        "valor": float(col.min())})
        records.append({"seccion": "frecuencias", "variable": v, "estadistico": "max",
                        "valor": float(col.max())})

    if "T5" in df.columns:
        t5 = pd.to_numeric(df["T5"], errors="coerce")
        for lev in sorted(t5.dropna().unique()):
            n_lev = int((t5 == lev).sum())
            pct = round(100 * n_lev / t5.notna().sum(), 1)
            lbl_map = {0: "Sin consumo efectivo", 1: "1 tipo vehículo (jarabe/tableta/etc.)",
                       2: "2 tipos", 3: "3 tipos", 4: "4 tipos",
                       5: "4 tipos + intensidad alta (N_consumidos=2 o 3)"}
            label = lbl_map.get(int(lev), f"Nivel {int(lev)}")
            records.append({"seccion": "niveles_T5", "variable": f"T5={int(lev)}",
                            "estadistico": "n", "valor": n_lev})
            records.append({"seccion": "niveles_T5", "variable": f"T5={int(lev)}",
                            "estadistico": "pct", "valor": pct})
            records.append({"seccion": "niveles_T5", "variable": f"T5={int(lev)}",
                            "estadistico": "definicion", "valor": label})
            print(f"  T5={int(lev)}: n={n_lev} ({pct}%) — {label}")

    if "T5" in df.columns and "n_consumidos" in df.columns:
        ct = pd.crosstab(pd.to_numeric(df["T5"], errors="coerce"),
                         pd.to_numeric(df["n_consumidos"], errors="coerce"),
                         margins=True)
        print("\n--- T5 × n_consumidos ---")
        print(ct.to_string())
        for t5_val, row in ct.iterrows():
            for nc_val in row.index[:-1]:
                if row[nc_val] > 0:
                    records.append({"seccion": "xtab_T5_n_consumidos",
                                    "variable": f"T5={t5_val}_nc={nc_val}",
                                    "estadistico": "n", "valor": int(row[nc_val])})

    if "T5" in df.columns and "T4" in df.columns:
        ct4 = pd.crosstab(pd.to_numeric(df["T5"], errors="coerce"),
                          pd.to_numeric(df["T4"], errors="coerce"),
                          margins=True)
        print("\n--- T5 × T4 ---")
        print(ct4.to_string())
        for t5_val, row in ct4.iterrows():
            for t4_val in row.index[:-1]:
                if row[t4_val] > 0:
                    records.append({"seccion": "xtab_T5_T4",
                                    "variable": f"T5={t5_val}_T4={t4_val}",
                                    "estadistico": "n", "valor": int(row[t4_val])})

    defs = [
        ("T1", "Recibió suplemento de hierro (auto-reporte binario)"),
        ("T2", "Número de tipos de vehículo (jarabe, tableta, etc.)"),
        ("T3", "Alguna vez tomó el suplemento"),
        ("T4", "Número de vehículos consumidos"),
        ("T5", "Índice ordinal 0–5: 0=sin consumo efectivo, 1–4=n_consumidos=niveles, "
               "5=4 tipos + alta intensidad (n_consumidos∈{2,3})"),
        ("n_consumidos", "Número de tipos de vehículo consumidos (rango en datos)"),
        ("n_recibidos", "Número de tipos de vehículo recibidos"),
        ("total_toma", "Total de tomas del suplemento"),
        ("total_rec", "Total de suplementos recibidos"),
        ("received_any", "T1==1 OR n_recibidos>=1 OR total_rec>0"),
        ("T5_ge1", "Consumo efectivo: T5 >= 1 (exposición principal)"),
    ]
    for var, desc in defs:
        records.append({"seccion": "definiciones", "variable": var, "estadistico": "definicion", "valor": desc})

    cb = pd.DataFrame(records)
    cb.to_csv(TAB / "codebook_exposicion.csv", index=False)
    print("\nCodebook guardado en tablas/codebook_exposicion.csv")
    return cb


def bootstrap_ipw_design(df, covs, B=500):
    """
    P1.1 — Bootstrap estratificado por conglomerado.
    Resamplea clusters (upm/hv001) DENTRO de cada estrato (estrato/hv022).
    En cada remuestreo: ajusta PS, calcula w_ipw, multiplica por w_design, estima ATE.
    Retorna dict {outcome: [B estimaciones]}.
    """
    strata_vals = df["estrato"].dropna().unique()
    stratum_clusters = {}
    for s in strata_vals:
        mask_s = df["estrato"] == s
        clusters = df.loc[mask_s, "upm"].unique()
        stratum_clusters[s] = {c: df[mask_s & (df["upm"] == c)] for c in clusters}

    store = {y: [] for y, _ in OUTCOMES}
    for b in range(B):
        sampled_dfs = []
        for s in strata_vals:
            clusters = list(stratum_clusters[s].keys())
            if len(clusters) == 0:
                continue
            n_cl = len(clusters)
            sampled_clusters = RNG.choice(clusters, size=n_cl, replace=True)
            for cl in sampled_clusters:
                sampled_dfs.append(stratum_clusters[s][cl])
        if not sampled_dfs:
            continue
        db = pd.concat(sampled_dfs, ignore_index=True)
        try:
            Ab, psb, _ = fit_ps(db, covs)
            w_ipw = weights(Ab, psb, estimand="ATE")
            w_design_b = db["hv005_norm"].values
            w_design_b = w_design_b / np.nanmean(w_design_b)
            w_prim = w_ipw * w_design_b
            for y, _ in OUTCOMES:
                store[y].append(ipw_wls(db[y].astype(float).values, Ab, w_prim)["estimate"])
        except Exception:
            continue
    return store


def make_exclusion_flow(df_raw, focus_pop, focus):
    """
    P0.3 — Construye tabla de flujo muestral y tabla de comparación excluidos vs incluidos.
    Retorna (flow_df, excl_comp_df).

    IMPORTANTE: df_raw debe ser el DataFrame ya preparado (prepare_raw) porque
    se accede a la columna 'received_any'.
    """
    n_total = len(df_raw)
    n_received = int((df_raw["received_any"] == 1).sum())
    n_no_dx = int(focus_pop.shape[0])
    n_complete = int(focus.shape[0])
    n_treated = int(focus["T5_ge1"].sum())
    n_control = int((1 - focus["T5_ge1"]).sum())

    flow = pd.DataFrame([
        {"paso": 1, "descripcion": "ENDES total",
         "n": n_total, "n_excluido": 0, "n_retenido": n_total},
        {"paso": 2, "descripcion": "Recibió suplemento (received_any=1)",
         "n": n_received, "n_excluido": n_total - n_received, "n_retenido": n_received},
        {"paso": 3, "descripcion": "Sin diagnóstico previo de anemia (dx_anemia=0)",
         "n": n_no_dx, "n_excluido": n_received - n_no_dx, "n_retenido": n_no_dx},
        {"paso": 4, "descripcion": "Casos completos en covariables",
         "n": n_complete, "n_excluido": n_no_dx - n_complete, "n_retenido": n_complete},
    ])
    flow_extra = pd.DataFrame([
        {"paso": "—", "descripcion": "  Tratados (T5>=1)", "n": n_treated,
         "n_excluido": np.nan, "n_retenido": np.nan},
        {"paso": "—", "descripcion": "  Control (T5=0)", "n": n_control,
         "n_excluido": np.nan, "n_retenido": np.nan},
    ])
    flow = pd.concat([flow, flow_extra], ignore_index=True)
    flow.to_csv(TAB / "tabla_0_flujo_muestral.csv", index=False)

    excl_idx = focus_pop.index.difference(focus.index)
    if len(excl_idx) > 0:
        excl = focus_pop.loc[excl_idx]
        comp_rows = []
        key_covs = ["edad_niño", "niña", "bajo_peso", "edad_madre", "educa_madre",
                     "madre_anemia", "quintil", "area"]
        for v in key_covs:
            if v not in focus_pop.columns:
                continue
            inc_vals = pd.to_numeric(focus[v], errors="coerce")
            exc_vals = pd.to_numeric(excl[v], errors="coerce")
            inc_m = inc_vals.mean() if inc_vals.notna().any() else np.nan
            exc_m = exc_vals.mean() if exc_vals.notna().any() else np.nan
            comp_rows.append({"variable": v, "media_incluidos": round(inc_m, 4) if not pd.isna(inc_m) else np.nan,
                              "media_excluidos": round(exc_m, 4) if not pd.isna(exc_m) else np.nan,
                              "n_excluidos": int(excl[v].notna().sum())})
        comp_df = pd.DataFrame(comp_rows)
        comp_df.to_csv(TAB / "tabla_0b_excluidos_vs_incluidos.csv", index=False)
    else:
        comp_df = pd.DataFrame()

    print(f"\nFlujo muestral: {n_total} → {n_received} → {n_no_dx} → {n_complete}")
    print(f"  Tratados: {n_treated}  |  Control: {n_control}")
    return flow, comp_df


def dose_response_ipw(df, covs, outcome="anemia_modsev"):
    """
    P2.2 — Dosis-respuesta con dummies T5_1..T5_5 vs T5_0.
    Retorna DataFrame con estimaciones y test de tendencia lineal.
    """
    d = df.copy()
    t5 = pd.to_numeric(d["T5"], errors="coerce")
    levels = [1, 2, 3, 4, 5]
    results = []
    for lev in levels:
        d_lev = d[t5.isin([0, lev])].copy()
        if len(d_lev) < 100 or d_lev["T5_ge1"].sum() < 30:
            results.append({"T5_level": lev, "n": len(d_lev), "ipw_ate": np.nan,
                            "ipw_p": np.nan, "ci_low": np.nan, "ci_high": np.nan})
            continue
        d_lev["T5_dose"] = (pd.to_numeric(d_lev["T5"], errors="coerce") == lev).astype(float)
        A_d, ps_d, _ = fit_ps(d_lev, covs, "T5_dose")
        w_d = weights(A_d, ps_d, estimand="ATE")
        est = ipw_wls(d_lev[outcome].astype(float).values, A_d, w_d)
        results.append({"T5_level": lev, "n": len(d_lev),
                        "ipw_ate": est["estimate"], "ipw_p": est["p_value"],
                        "ci_low": est["ci_low"], "ci_high": est["ci_high"]})
    dr_df = pd.DataFrame(results)
    dr_df.to_csv(TAB / "tabla_S_dosis_respuesta.csv", index=False)

    valid = dr_df.dropna(subset=["ipw_ate"])
    if len(valid) >= 2:
        r, p_trend = stats.pearsonr(valid["T5_level"].values, valid["ipw_ate"].values)
        print(f"  Test tendencia lineal dosis-respuesta: r={r:.4f}, p={p_trend:.4f}")
        trend_info = pd.DataFrame([{"test": "Pearson r (ATE ~ nivel T5)", "r": r, "p_value": p_trend,
                                    "n_levels": len(valid)}])
        trend_info.to_csv(TAB / "tabla_S_dosis_respuesta_trend.csv", index=False)
    else:
        print("  Insuficientes niveles para test de tendencia.")
    return dr_df


def misclassification_sim(df, covs, outcome="anemia_modsev", n_sim=1000):
    """
    P2.3 — Simulación de sesgo por mala clasificación de la exposición.
    En cada iteración, se perturba aleatoriamente T5_ge1 (flip ~3%)
    y se reestima IPW ATE.
    """
    results = []
    A_true = df["T5_ge1"].astype(int).values
    Y = df[outcome].astype(float).values
    for _ in range(n_sim):
        flip_mask = RNG.random(len(A_true)) < 0.03
        A_mis = A_true.copy()
        A_mis[flip_mask] = 1 - A_mis[flip_mask]
        if A_mis.sum() == 0 or A_mis.sum() == len(A_mis):
            continue
        d_sim = df.copy()
        d_sim["_A_mis"] = A_mis
        try:
            _, psm, _ = fit_ps(d_sim, covs, "_A_mis")
            wm = weights(A_mis, psm, estimand="ATE")
            est = ipw_wls(Y, A_mis, wm)
            results.append(est["estimate"])
        except Exception:
            continue
    if results:
        arr = np.array(results)
        sim_df = pd.DataFrame([{
            "outcome": outcome, "n_sim": len(results),
            "mean_ate": float(np.mean(arr)), "sd_ate": float(np.std(arr, ddof=1)),
            "bias_pct": float(100 * (np.mean(arr) - ipw_wls(Y, A_true,
                weights(A_true, fit_ps(df, covs)[1], estimand="ATE"))["estimate"])),
        }])
        sim_df.to_csv(TAB / "tabla_S_misclass.csv", index=False)
        print(f"  Misclassification sim ({len(results)} válidos): ATE medio = {np.mean(arr):.5f}")
        return sim_df
    return pd.DataFrame()


# ================================================================== MAIN
def main():
    print("=" * 60)
    print("PIPELINE INFERENCIA CAUSAL — ENDES 2024")
    print("=" * 60)

    # ---------------------------------------------------------------- 0. CARGA
    print(f"\nCargando {DATA}")
    raw = pd.read_stata(DATA, convert_categoricals=False)
    assert raw.shape[0] == 14428, f"Esperados 14428, obtenidos {raw.shape[0]}"
    df = prepare_raw(raw)

    # ---------------------------------------------------------------- P0.5 — CODEBOOK
    print("\n>>> P0.5 — Codebook de exposición")
    document_treatment_construction(df)

    # ---------------------------------------------------------------- 1. MISSINGNESS
    miss_vars = ["eda_aun", "lact_exclu", "madre_anemia", "educa_madre"] + BASE_COVARIATES
    miss_vars = list(dict.fromkeys([c for c in miss_vars if c in df.columns]))
    pd.DataFrame({
        "variable": miss_vars,
        "n_missing": [int(df[c].isna().sum()) for c in miss_vars],
        "pct_missing": [round(100 * float(df[c].isna().mean()), 2) for c in miss_vars],
    }).to_csv(TAB / "tabla_S1_missingness.csv", index=False)

    # ---------------------------------------------------------------- 2. MUESTRA CONFIRMATORIA (elegibilidad exportable)
    print("\n>>> Elegibilidad exportable: build_eligibility + make_analytic_sample")
    focus_pop, focus, covs = make_analytic_sample(
        df, covariates=BASE_COVARIATES_CORE, include_design=True, include_dpto=True
    )
    # documentar reglas de elegibilidad
    pd.DataFrame([
        {"regla": "received_any==1", "descripcion": "Receptor del programa (T1|n_recibidos|total_rec)"},
        {"regla": "dx_anemia==0", "descripcion": "Sin diagnóstico previo de anemia del niño (autorreporte)"},
        {"regla": "complete_case", "descripcion": "Sin missing en covs pretratamiento, outcomes y diseño"},
        {"regla": "tratamiento", "descripcion": "T5_ge1 = (T5>=1) consumo reportado ≥1 vehículo"},
        {"regla": "funcion", "descripcion": "build_eligibility() + make_analytic_sample() en pipeline"},
    ]).to_csv(TAB / "tabla_S_elegibilidad_reglas.csv", index=False)
    print(f"\nMuestra confirmatoria: {focus.shape} | tratados: {int(focus['T5_ge1'].sum())}")

    # ---------------------------------------------------------------- P0.3 — FLUJO MUESTRAL
    print("\n>>> P0.3 — Flujo muestral y comparación excluidos")
    # FIX: usar `df` (preparado con prepare_raw) porque make_exclusion_flow
    # accede a la columna `received_any` que sólo existe en `df`.
    flow_df, excl_comp = make_exclusion_flow(df, focus_pop, focus)

    # ---------------------------------------------------------------- 3. TABLA 1
    t = focus["T5_ge1"].astype(int)
    desc = [
        ("edad_niño", "cont", "Edad del niño (meses)"),
        ("niña", "bin", "Sexo femenino"),
        ("bajo_peso", "bin", "Bajo peso al nacer"),
        ("edad_madre", "cont", "Edad materna (años)"),
        ("educa_madre", "cont", "Educación materna (nivel)"),
        ("madre_anemia", "bin", "Anemia materna"),
        ("control_pren", "bin", "Control prenatal"),
        ("quintil", "cont", "Quintil de riqueza"),
        ("agua_potable", "bin", "Agua potable"),
        ("saneamiento", "bin", "Saneamiento"),
        ("area", "bin", "Área urbana"),
        ("eda_14d_ant", "bin", "Diarrea 14 días (post-tratamiento)"),
        ("anemia", "bin", "Anemia"),
        ("anemia_modsev", "bin", "Anemia moderada/severa"),
        ("hb_minsa", "cont", "Hb MINSA (g/L)"),
        ("hb_oms", "cont", "Hb OMS (g/L)"),
    ]
    r1 = []
    for v, kind, lab in desc:
        a1, a0, tot = focus.loc[t == 1, v], focus.loc[t == 0, v], focus[v]
        if kind == "bin":
            r1.append({"variable": lab, "consumo_efectivo": f"{100*a1.mean():.1f}%",
                       "control": f"{100*a0.mean():.1f}%", "total": f"{100*tot.mean():.1f}%"})
        else:
            r1.append({"variable": lab, "consumo_efectivo": f"{a1.mean():.1f} ({a1.std(ddof=1):.1f})",
                       "control": f"{a0.mean():.1f} ({a0.std(ddof=1):.1f})",
                       "total": f"{tot.mean():.1f} ({tot.std(ddof=1):.1f})"})
    pd.DataFrame(r1).to_csv(TAB / "tabla_1_caracteristicas.csv", index=False)

    # ---------------------------------------------------------------- 4. PS PRINCIPAL (SIN diarrea) + BALANCE
    print("\n>>> PS principal (core covariates, sin eda_14d_ant)")
    A, ps_core, _ = fit_ps(focus, covs, model="logit")
    w_core = weights(A, ps_core, estimand="ATE")
    bal = smd_table(focus, A, w_core, covs)
    bal.to_csv(TAB / "tabla_S2_balance_smd.csv", index=False)
    max_smd = bal["smd_post"].abs().max()
    print(f"  Max |SMD| post-IPW: {max_smd:.4f}")

    # ---------------------------------------------------------------- P0.6 — SENSIBILIDAD PS CON/SIN DIARREA
    print("\n>>> P0.6 — Sensibilidad PS con diarrea (eda_14d_ant)")
    covs_diarrhea = BASE_COVARIATES_WITH_DIARRHEA + ["edad_niño_sq", "edad_niño_cu"]
    Ad, ps_diarrhea, _ = fit_ps(focus, covs_diarrhea, model="logit")
    w_diarrhea = weights(Ad, ps_diarrhea, estimand="ATE")

    sens_rows = []
    for y, ytype in OUTCOMES:
        Y = focus[y].astype(float).values
        est_core = ipw_wls(Y, A, w_core)
        est_dia = ipw_wls(Y, Ad, w_diarrhea)
        rd_core = est_core["estimate"]
        rd_dia = est_dia["estimate"]
        delta_rd = rd_core - rd_dia
        sens_rows.append({
            "outcome": y, "etiqueta": OUT_LABELS[y],
            "ipw_sin_diarrea": rd_core, "ipw_p_sin": est_core["p_value"],
            "ipw_con_diarrea": rd_dia, "ipw_p_con": est_dia["p_value"],
            "delta_rd": delta_rd,
        })
    sens_diarrhea_df = pd.DataFrame(sens_rows)
    sens_diarrhea_df.to_csv(TAB / "tabla_S_sensibilidad_diarrea.csv", index=False)
    print(sens_diarrhea_df[["outcome", "ipw_sin_diarrea", "ipw_con_diarrea", "delta_rd"]].to_string(index=False))

    # ---------------------------------------------------------------- P1.1 — PRIMARIO: IPW × DISEÑO + BOOTSTRAP
    print(f"\n>>> P1.1 — Bootstrap estratificado (500 iteraciones, clusters dentro de estratos)")
    boot_store = bootstrap_ipw_design(focus, covs, B=500)
    w_design = focus["hv005_norm"].values
    w_design = w_design / np.nanmean(w_design)

    w_prim_point = w_core * w_design

    A_ref, ps_ref, _ = fit_ps(focus, covs)
    w_ref = weights(A_ref, ps_ref, estimand="ATE")

    match_rows = {}
    for y, _ in OUTCOMES:
        match_rows[y] = matching_att(focus, covs, y)

    aipw_rows = {}
    for y, ytype in OUTCOMES:
        aipw_rows[y] = estimate_aipw(focus, "T5_ge1", y, covs, ytype)

    primary_rows = []
    boot_p_values = {}
    for i, (y, ytype) in enumerate(OUTCOMES):
        Y = focus[y].astype(float).values
        ipw_design = ipw_wls(Y, A, w_prim_point)
        ipw_no_design = ipw_wls(Y, A, w_ref)
        arr = np.array(boot_store.get(y, []))
        if len(arr) > 0:
            boot_ci_low = float(np.percentile(arr, 2.5))
            boot_ci_high = float(np.percentile(arr, 97.5))
            # p bootstrap bilateral H0: tau=0 (proporción de réplicas al otro lado del 0)
            p_boot = float(2.0 * min(np.mean(arr <= 0), np.mean(arr >= 0)))
            p_boot = min(p_boot, 1.0)
        else:
            boot_ci_low, boot_ci_high, p_boot = np.nan, np.nan, np.nan
        boot_p_values[y] = p_boot
        aipw = aipw_rows[y]
        mat = match_rows[y]
        primary_rows.append({
            "outcome": y, "etiqueta": OUT_LABELS[y],
            "ipw_design_ate": ipw_design["estimate"],
            "ipw_design_p": ipw_design["p_value"],  # HC3 con pesos IPW×diseño
            "boot_ci_low": boot_ci_low, "boot_ci_high": boot_ci_high,
            "p_boot": p_boot,
            "ipw_no_design": ipw_no_design["estimate"],
            "ipw_no_design_p": ipw_no_design["p_value"],
            "aipw": aipw["estimate"], "aipw_p": aipw["p_value"],
            "matching_att": mat["estimate"], "matching_p": mat["p_value"],
            "matching_n_pairs": mat.get("n_pairs", np.nan),
        })

    # ---------------------------------------------------------------- P1.2 — HOLM-BONFERRONI
    # Ajuste sobre p HC3 del estimador primario (IPW×diseño); el primario no se corrige.
    print("\n>>> P1.2 — Holm-Bonferroni (primario = anemia_modsev, 4 secundarios)")
    p_vals_for_holm = [row["ipw_design_p"] for row in primary_rows]
    holm_adj = holm_bonferroni(p_vals_for_holm, primary_idx=1)

    for i, row in enumerate(primary_rows):
        row["holm_p"] = holm_adj[i]

    primary_df = pd.DataFrame(primary_rows)
    primary_df.to_csv(TAB / "tabla_2_efectos_primarios.csv", index=False)
    # Compatibilidad: también exportar tabla_2 / tabla_4 en formatos legibles por el paper
    primary_df.to_csv(TAB / "tabla_2_efectos_ipw_aipw.csv", index=False)
    tabla4 = primary_df[["outcome", "ipw_no_design", "ipw_no_design_p",
                         "ipw_design_ate", "ipw_design_p", "boot_ci_low", "boot_ci_high"]].copy()
    tabla4.columns = ["outcome", "ipw_sin_diseno", "p_sin", "ipw_con_diseno", "p_con",
                      "boot_ci_low", "boot_ci_high"]
    tabla4.to_csv(TAB / "tabla_4_pesos_diseno.csv", index=False)
    print(primary_df[["outcome", "ipw_design_ate", "ipw_design_p", "boot_ci_low", "boot_ci_high",
                       "p_boot", "holm_p"]].to_string(index=False))

    # ---------------------------------------------------------------- P2.1 — NNT
    print("\n>>> P2.1 — NNT")
    rd_prim = primary_df.loc[primary_df.outcome == "anemia_modsev", "ipw_design_ate"].values[0]
    nnt_val = nnt(rd_prim) if not pd.isna(rd_prim) else np.nan
    print(f"  RD diseño anemia mod/sev = {rd_prim:.5f}  →  NNT = {nnt_val}")

    # ---------------------------------------------------------------- PLACEBO
    fake = RNG.binomial(1, A.mean(), size=len(A))
    plac = []
    for y, _ in OUTCOMES:
        d2 = focus.copy(); d2["_f"] = fake
        Af, psf, _ = fit_ps(d2, covs, "_f")
        wf = weights(Af, psf, estimand="ATE")
        est = ipw_wls(focus[y].astype(float).values, Af, wf)
        plac.append({"outcome": y, "estimate": est["estimate"], "p_value": est["p_value"]})
    plac_df = pd.DataFrame(plac)

    # ---------------------------------------------------------------- SUBSAMPLING
    print("Subsampling 1000×80% ...")
    n_sub = int(0.8 * len(focus))
    store_sub = {y: [] for y, _ in OUTCOMES}
    for _ in range(1000):
        idx = RNG.choice(len(focus), size=n_sub, replace=False)
        d = focus.iloc[idx]
        As, pss, _ = fit_ps(d, covs)
        ws = weights(As, pss, estimand="ATE")
        for y, _ in OUTCOMES:
            store_sub[y].append(ipw_wls(d[y].astype(float).values, As, ws)["estimate"])
    sub_df = pd.DataFrame([{"outcome": y, "mean": np.mean(store_sub[y]),
                            "ci_low": np.percentile(store_sub[y], 2.5),
                            "ci_high": np.percentile(store_sub[y], 97.5)}
                           for y, _ in OUTCOMES])

    # ---------------------------------------------------------------- E-VALUES
    main_df_for_eval = pd.DataFrame([
        {"outcome": y, "ipw_ate": ipw_wls(focus[y].astype(float).values, A, w_ref)["estimate"],
         "mean_do1": ipw_wls(focus[y].astype(float).values, A, w_ref)["mean_do1"],
         "mean_do0": ipw_wls(focus[y].astype(float).values, A, w_ref)["mean_do0"]}
        for y, _ in OUTCOMES
    ])
    ev = []
    for i, (y, ytype) in enumerate(OUTCOMES):
        row = main_df_for_eval.iloc[i]
        if ytype == "binary":
            rr = row["mean_do1"] / row["mean_do0"] if row["mean_do0"] and row["mean_do0"] > 0 else np.nan
            ev.append({"outcome": y, "RR": rr, "E_value": evalue_rr(rr)})
        else:
            sd = float(focus[y].std(ddof=1))
            rr = np.exp(0.91 * abs(row["ipw_ate"]) / sd) if sd > 0 else np.nan
            ev.append({"outcome": y, "RR": rr, "E_value": evalue_rr(rr)})
    ev_df = pd.DataFrame(ev)

    # ---------------------------------------------------------------- TABLA 3: ROBUSTEZ CONSOLIDADA (sin Rosenbaum)
    rob = []
    for y, _ in OUTCOMES:
        p = plac_df[plac_df.outcome == y].iloc[0]
        s = sub_df[sub_df.outcome == y].iloc[0]
        e = ev_df[ev_df.outcome == y].iloc[0]
        rob.append({"outcome": y, "etiqueta": OUT_LABELS[y],
                    "placebo_p": p["p_value"],
                    "sub_ci_low": s["ci_low"], "sub_ci_high": s["ci_high"],
                    "e_value": e["E_value"]})
    pd.DataFrame(rob).to_csv(TAB / "tabla_3_robustez.csv", index=False)

    # ---------------------------------------------------------------- POSITIVIDAD (P1.0)
    print("\n>>> P1.0 — Diagnóstico de positividad")
    ps_raw = ps_core
    n_low = int(np.sum(ps_raw < 0.05))
    n_mid = int(np.sum((ps_raw >= 0.05) & (ps_raw <= 0.95)))
    n_high = int(np.sum(ps_raw > 0.95))
    n_total = len(ps_raw)
    pos_rows = [
        {"region": "ps < 0.05", "n": n_low, "pct": round(100 * n_low / n_total, 2)},
        {"region": "0.05 <= ps <= 0.95", "n": n_mid, "pct": round(100 * n_mid / n_total, 2)},
        {"region": "ps > 0.95", "n": n_high, "pct": round(100 * n_high / n_total, 2)},
    ]
    pos_df = pd.DataFrame(pos_rows)
    pos_df.to_csv(TAB / "tabla_S_positivity.csv", index=False)
    n_trimmed_ps = n_low + n_high
    print(f"  PS < 0.05: {n_low} | PS > 0.95: {n_high} | Total trimmed: {n_trimmed_ps}")

    # Figura S2 — Densidad PS por brazo
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.hist(ps_raw[A == 1], bins=40, alpha=0.6, density=True, color="#4c72b0", label="Tratados (T5≥1)")
    ax.hist(ps_raw[A == 0], bins=40, alpha=0.6, density=True, color="#c44e52", label="Control (T5=0)")
    ax.set_xlabel("Propensity score")
    ax.set_ylabel("Densidad")
    ax.set_title("Distribución del propensity score por brazo de tratamiento")
    ax.legend(frameon=False)
    fig.savefig(FIG / "figura_S2_ps_density.png"); plt.close()

    # ---------------------------------------------------------------- MATCHING ATT (suplementario)
    mrows = [{"outcome": y, **matching_att(focus, covs, y)} for y, _ in OUTCOMES]
    match_df = pd.DataFrame(mrows)
    match_df.to_csv(TAB / "tabla_S3_matching_att.csv", index=False)

    # ---------------------------------------------------------------- TRIMMING
    tr_specs = [("clip_05_95", (0.05, 0.95), None), ("clip_01_99", (0.01, 0.99), None),
                ("clip_10_90", (0.10, 0.90), None), ("clip_05_95_cap_p99", (0.05, 0.95), "p99")]
    tr_rows = []
    for name, trim, cap in tr_specs:
        wt = weights(A, ps_core, trim=trim, estimand="ATE")
        if cap == "p99":
            wt = np.minimum(wt, np.percentile(wt, 99))
        for y, _ in OUTCOMES:
            est = ipw_wls(focus[y].astype(float).values, A, wt)
            tr_rows.append({"spec": name, "outcome": y, "estimate": est["estimate"],
                            "p_value": est["p_value"], "w_max": float(wt.max())})
    trim_df = pd.DataFrame(tr_rows)
    trim_df.to_csv(TAB / "tabla_S4_trimming.csv", index=False)

    # ---------------------------------------------------------------- PS LOGIT VS GBM
    ps_rows = []
    for model in ("logit", "gbm"):
        Am, psm, _ = fit_ps(focus, covs, model=model)
        wm = weights(Am, psm, estimand="ATE")
        ms = smd_table(focus, Am, wm, covs)["smd_post"].abs().max()
        for y, ytype in OUTCOMES:
            ipw = ipw_wls(focus[y].astype(float).values, Am, wm)
            aipw = estimate_aipw(focus, "T5_ge1", y, covs, ytype, ps_model=model)
            ps_rows.append({"ps_model": model, "outcome": y, "ipw_ate": ipw["estimate"],
                            "ipw_p": ipw["p_value"], "aipw_ate": aipw["estimate"],
                            "aipw_p": aipw["p_value"], "max_abs_smd": ms})
    psmodel_df = pd.DataFrame(ps_rows)
    psmodel_df.to_csv(TAB / "tabla_S5_ps_logit_gbm.csv", index=False)

    # ---------------------------------------------------------------- LEAVE-ONE-COVARIATE-OUT
    loo_rows = []
    for y, _ in OUTCOMES:
        loo_rows.append({"dropped": "NONE", "outcome": y,
                         "estimate": ipw_wls(focus[y].astype(float).values, A, w_core)["estimate"]})
    for drop in BASE_COVARIATES_CORE:
        covs_d = ([c for c in BASE_COVARIATES_CORE if c != drop]
                  + ([] if drop == "edad_niño" else ["edad_niño_sq", "edad_niño_cu"]))
        Ad_loo, psd_loo, _ = fit_ps(focus, covs_d)
        wdd_loo = weights(Ad_loo, psd_loo, estimand="ATE")
        for y, _ in OUTCOMES:
            loo_rows.append({"dropped": drop, "outcome": y,
                             "estimate": ipw_wls(focus[y].astype(float).values, Ad_loo, wdd_loo)["estimate"]})
    loo_df = pd.DataFrame(loo_rows)
    loo_df.to_csv(TAB / "tabla_S6_leave_one_out.csv", index=False)

    # ---------------------------------------------------------------- ESTRATIFICACIÓN
    focus["edad_grp"] = pd.cut(focus["edad_niño"], [5, 11, 23, 35, 60],
                               labels=["6-11", "12-23", "24-35", "36+"])
    focus["quintil_alto"] = (focus["quintil"] >= 4).astype(int)
    strata = [("urbano", focus.area == 1), ("rural", focus.area == 0),
              ("quintil_4_5", focus.quintil_alto == 1), ("quintil_1_3", focus.quintil_alto == 0),
              ("edad_6_11", focus.edad_grp == "6-11"), ("edad_12_23", focus.edad_grp == "12-23"),
              ("edad_24_35", focus.edad_grp == "24-35")]
    st_rows = []
    for lab, mask in strata:
        d_st = add_age_polys(focus.loc[mask].copy())
        if d_st["T5_ge1"].sum() < 80 or (1 - d_st["T5_ge1"]).sum() < 80:
            continue
        Ast_st, psst_st, _ = fit_ps(d_st, covs)
        wst_st = weights(Ast_st, psst_st, estimand="ATE")
        for y, _ in OUTCOMES:
            est = ipw_wls(d_st[y].astype(float).values, Ast_st, wst_st)
            st_rows.append({"estrato": lab, "outcome": y, "n": len(d_st),
                            "estimate": est["estimate"], "p_value": est["p_value"]})
    pd.DataFrame(st_rows).to_csv(TAB / "tabla_S7_estratificacion.csv", index=False)

    # ---------------------------------------------------------------- MICE
    print("MICE m=5 ...")
    other = [c for c in BASE_COVARIATES_CORE if c != "madre_anemia"] + ["T5_ge1"] + [y for y, _ in OUTCOMES]
    fm = focus_pop[list(dict.fromkeys(BASE_COVARIATES_CORE + ["T5_ge1"] + [y for y, _ in OUTCOMES]))].apply(pd.to_numeric, errors="coerce")
    dm = fm.loc[fm[other].notna().all(axis=1)].copy()
    imp_cols = BASE_COVARIATES_CORE + ["T5_ge1"] + [y for y, _ in OUTCOMES]
    mice_store = {y: [] for y, _ in OUTCOMES}
    for m in range(5):
        imputer = IterativeImputer(random_state=SEED + m, max_iter=10, sample_posterior=True)
        arr = imputer.fit_transform(dm[imp_cols])
        di = pd.DataFrame(arr, columns=imp_cols, index=dm.index)
        for y, _ in OUTCOMES:
            di[y] = dm[y].values
        di["T5_ge1"] = dm["T5_ge1"].values
        di = add_age_polys(di)
        Am_m, psm_m, _ = fit_ps(di, covs)
        wm_m = weights(Am_m, psm_m, estimand="ATE")
        for y, _ in OUTCOMES:
            mice_store[y].append(ipw_wls(di[y].astype(float).values, Am_m, wm_m)["estimate"])
    ref_mice = {y: ipw_wls(focus[y].astype(float).values, A, w_ref)["estimate"] for y, _ in OUTCOMES}
    mice_df = pd.DataFrame([{"outcome": y, "ate_mice_mean": np.mean(mice_store[y]),
                             "ate_complete_case": ref_mice[y]} for y, _ in OUTCOMES])
    mice_df.to_csv(TAB / "tabla_S8_mice.csv", index=False)

    # ---------------------------------------------------------------- T3 NULO
    dfa = add_age_polys(df[["T3", "anemia"] + BASE_COVARIATES_CORE].apply(pd.to_numeric, errors="coerce").dropna())
    At3, pst3, _ = fit_ps(dfa, covs, "T3")
    wt3 = weights(At3, pst3, estimand="ATE")
    t3 = ipw_wls(dfa["anemia"].astype(float).values, At3, wt3)
    pd.DataFrame([{"treatment": "T3", "outcome": "anemia", "n": len(dfa),
                   "ate": t3["estimate"], "p_value": t3["p_value"]}]).to_csv(
        TAB / "tabla_S9_t3_nulo.csv", index=False)

    # ---------------------------------------------------------------- P2.2 — DOSIS-RESPUESTA
    print("\n>>> P2.2 — Dosis-respuesta (T5 ordinal)")
    dose_response_ipw(focus, covs, outcome="anemia_modsev")

    # ---------------------------------------------------------------- P2.3 — MISCLASSIFICATION SIM
    print("\n>>> P2.3 — Simulación de mala clasificación (1000 iteraciones)")
    misclassification_sim(focus, covs, outcome="anemia_modsev", n_sim=1000)

    # ---------------------------------------------------------------- P2.4 — OVERLAP (ATO)
    print("\n>>> P2.4 — Pesos de overlap (ATO) para anemia mod/sev")
    ps_for_ato = np.clip(ps_core, 1e-6, 1 - 1e-6)
    w_ato = overlap_weights_ato(A, ps_for_ato)
    est_ato = ipw_wls(focus["anemia_modsev"].astype(float).values, A, w_ato)
    est_ipw_ref = ipw_wls(focus["anemia_modsev"].astype(float).values, A, w_ref)
    overlap_df = pd.DataFrame([{
        "outcome": "anemia_modsev",
        "ipw_ate": est_ipw_ref["estimate"], "ipw_p": est_ipw_ref["p_value"],
        "ato_ate": est_ato["estimate"], "ato_p": est_ato["p_value"],
    }])
    overlap_df.to_csv(TAB / "tabla_S_overlap.csv", index=False)
    print(f"  IPW ATE = {est_ipw_ref['estimate']:.5f}  |  ATO ATE = {est_ato['estimate']:.5f}")

    # ---------------------------------------------------------------- P2-Q1 — IPW INCLUSIÓN, E-VALUE BENCHMARK, MDE, IMPACTO
    print("\n>>> P2-Q1 — IPW de inclusión (selección a casos completos)")
    incl_df = inclusion_ipw_analysis(focus_pop, focus, BASE_COVARIATES_CORE, "anemia_modsev")

    print("\n>>> P2-Q1 — Benchmark E-value con confusores observados")
    ebench = evalue_benchmark(focus, "anemia_modsev")

    print("\n>>> P2-Q1 — MDE / poder post-hoc")
    mde_df = power_mde_table(focus, "anemia_modsev")

    print("\n>>> P2-Q1 — Impacto poblacional escalado")
    p0row = primary_df[primary_df.outcome == "anemia_modsev"].iloc[0]
    impact_df = population_impact(
        df, focus,
        rd_design=p0row["ipw_design_ate"],
        boot_ci_low=p0row["boot_ci_low"],
        boot_ci_high=p0row["boot_ci_high"],
    )

    # ---------------------------------------------------------------- Pauta residual: dpto, interacciones, NNT, PATE, PS survey, escenarios
    print("\n>>> Pauta — Heterogeneidad dpto/macro + interacciones")
    heterogeneity_dpto_macro(df, focus, covs, outcome="anemia_modsev")

    print("\n>>> Pauta — NNT por subgrupo")
    nnt_by_subgroup(focus, covs, outcome="anemia_modsev")

    print("\n>>> Pauta — PATE-like exploratorio")
    pate_like_exploratory(df, BASE_COVARIATES_CORE, outcome="anemia_modsev")

    print("\n>>> Pauta — PS survey-weighted (sensibilidad)")
    design_weighted_ps_sensitivity(focus, covs, outcome="anemia_modsev")

    print("\n>>> Pauta — Peores escenarios / recomendaciones condicionales")
    ev_mod = float(ev_df.loc[ev_df.outcome == "anemia_modsev", "E_value"].values[0])
    worst_case_scenarios(
        rd_design=float(p0row["ipw_design_ate"]),
        boot_lo=float(p0row["boot_ci_low"]),
        boot_hi=float(p0row["boot_ci_high"]),
        e_value=ev_mod,
        nnt_val=nnt_val,
    )

    # ---------------------------------------------------------------- MEJORAS REPO-ONLY (post-95)
    print("\n>>> Mejoras repo — Lee bounds de selección")
    lee_bounds_selection(focus_pop, focus, outcome="anemia_modsev")

    print("\n>>> Mejoras repo — Mediación exploratoria diarrea")
    mediation_diarrhea_analysis(focus, covs, outcome="anemia_modsev")

    print("\n>>> Mejoras repo — Pesos de transporte (IOSW-like)")
    transport_weights_analysis(df, focus, BASE_COVARIATES_CORE, outcome="anemia_modsev")

    print("\n>>> Mejoras repo — SE sandwich cluster (sensibilidad)")
    sandwich_survey_se(focus, covs, outcome="anemia_modsev")

    print("\n>>> Mejoras repo — Tabla comparativa de literatura")
    literature_comparison_table()

    # ================================================================ FIGURAS
    print("\nGenerando figuras ...")

    # Figura 1 — Love plot
    bp = bal.copy()
    bp["abs_pre"] = bp["smd_pre"].abs(); bp["abs_post"] = bp["smd_post"].abs()
    bp = bp.sort_values("abs_post")
    fig, ax = plt.subplots(figsize=(7, 6))
    yy = np.arange(len(bp))
    ax.scatter(bp["abs_pre"], yy, marker="o", label="Sin ponderar", color="#c44e52")
    ax.scatter(bp["abs_post"], yy, marker="s", label="Post-IPW", color="#4c72b0")
    ax.axvline(0.10, color="gray", ls="--", lw=1)
    ax.set_yticks(yy); ax.set_yticklabels(bp["covariable"], fontsize=8)
    ax.set_xlabel("Diferencia media estandarizada absoluta |SMD|")
    ax.legend(frameon=False)
    fig.savefig(FIG / "figura_1_love_plot.png"); plt.close()

    # Figura 2 — Forest IPW × diseño (primario)
    fig, ax = plt.subplots(figsize=(8, 5))
    yy = np.arange(len(primary_df))
    ax.errorbar(primary_df["ipw_design_ate"], yy,
                xerr=[primary_df["ipw_design_ate"] - primary_df["boot_ci_low"],
                      primary_df["boot_ci_high"] - primary_df["ipw_design_ate"]],
                fmt="o", color="#4c72b0", capsize=3, label="IPW × diseño (IC 95% boot)")
    ax.axvline(0, color="gray", ls="--", lw=1)
    ax.set_yticks(yy); ax.set_yticklabels([OUT_LABELS[o] for o in primary_df["outcome"]])
    ax.set_xlabel("Efecto causal estimado — IPW × diseño ENDES (IC 95%)")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(FIG / "figura_2_forest_plot.png"); plt.close()

    # Figura 3 — DAG de publicación (módulo editorial; no sobrescribir con cajas crudas)
    try:
        import importlib.util

        _fp = Path(__file__).resolve().parent / "figuras_publicacion.py"
        _spec = importlib.util.spec_from_file_location("figuras_publicacion", _fp)
        _mod = importlib.util.module_from_spec(_spec)
        assert _spec.loader is not None
        _spec.loader.exec_module(_mod)
        _mod.figura_3_dag()
    except Exception as _e_fig3:
        print(f"  [aviso] figuras_publicacion.figura_3_dag falló ({_e_fig3}); se omite overwrite.")

    # Figura 4 — Specification curve anemia mod/sev
    p0 = primary_df[primary_df.outcome == "anemia_modsev"].iloc[0]
    synth = []
    synth.append(("IPW × diseño (boot CI)", p0["ipw_design_ate"], p0["boot_ci_low"], p0["boot_ci_high"]))
    synth.append(("IPW ATE (logit)", p0["ipw_no_design"], np.nan, np.nan))
    synth.append(("AIPW ATE (logit)", p0["aipw"], np.nan, np.nan))
    m0 = match_df[match_df.outcome == "anemia_modsev"].iloc[0]
    if np.isfinite(m0.get("ci_low", np.nan)):
        synth.append(("Matching ATT", m0["estimate"], m0["ci_low"], m0["ci_high"]))
    g0 = psmodel_df[(psmodel_df.outcome == "anemia_modsev") & (psmodel_df.ps_model == "gbm")].iloc[0]
    synth.append(("AIPW (PS-GBM)", g0["aipw_ate"], np.nan, np.nan))
    s0 = sub_df[sub_df.outcome == "anemia_modsev"].iloc[0]
    synth.append(("Subsampling 80%", np.mean(store_sub["anemia_modsev"]), s0["ci_low"], s0["ci_high"]))
    fig, ax = plt.subplots(figsize=(8, 4.5))
    yy = np.arange(len(synth))
    for i, (lab, est, lo, hi) in enumerate(synth):
        if np.isfinite(lo) and np.isfinite(hi):
            ax.errorbar(est, i, xerr=[[est - lo], [hi - est]], fmt="o", color="#4c72b0", capsize=3)
        else:
            ax.plot(est, i, "D", color="#55a868")
    ax.axvline(0, color="gray", ls="--", lw=1)
    ax.set_yticks(yy); ax.set_yticklabels([s[0] for s in synth], fontsize=9)
    ax.set_xlabel("Efecto sobre anemia moderada/severa (RD)")
    fig.savefig(FIG / "figura_4_curva_especificacion.png"); plt.close()

    # Figura 5 — Subsampling distributions
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4))
    for ax_i, y in zip(axes, ["anemia", "anemia_modsev", "hb_minsa"]):
        ax_i.hist(store_sub[y], bins=30, color="#4c72b0", alpha=0.8)
        ax_i.axvline(0, color="red", ls="--", lw=1)
        ax_i.set_title(OUT_LABELS[y], fontsize=9)
        ax_i.set_xlabel("ATE")
    fig.tight_layout()
    fig.savefig(FIG / "figura_5_subsampling.png"); plt.close()

    # Figura S1 — LOO
    lm = loo_df[loo_df.outcome == "anemia_modsev"].sort_values("estimate")
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.barh(lm["dropped"], lm["estimate"], color="#dd8452")
    ax.axvline(lm.loc[lm.dropped == "NONE", "estimate"].iloc[0], color="#4c72b0", ls="--", label="baseline")
    ax.axvline(0, color="gray", ls=":")
    ax.set_xlabel("IPW ATE anemia mod/sev"); ax.legend(frameon=False)
    fig.savefig(FIG / "figura_S1_leave_one_out.png"); plt.close()

    # Figura S3 — Dosis-respuesta (opcional)
    try:
        dr_plot = pd.read_csv(TAB / "tabla_S_dosis_respuesta.csv")
        valid_dr = dr_plot.dropna(subset=["ipw_ate"])
        if len(valid_dr) >= 2:
            fig, ax = plt.subplots(figsize=(6, 4))
            ax.errorbar(valid_dr["T5_level"], valid_dr["ipw_ate"],
                        yerr=[valid_dr["ipw_ate"] - valid_dr["ci_low"],
                              valid_dr["ci_high"] - valid_dr["ipw_ate"]],
                        fmt="o-", color="#4c72b0", capsize=4, lw=1.5)
            ax.axhline(0, color="gray", ls="--", lw=1)
            ax.set_xlabel("Nivel T5 (intensidad de consumo)")
            ax.set_ylabel("IPW ATE — anemia mod/sev (RD)")
            ax.set_title("Dosis-respuesta: efecto marginal por nivel T5 vs T5=0")
            fig.savefig(FIG / "figura_S3_dosis_respuesta.png"); plt.close()
    except Exception:
        pass

    # ---------------------------------------------------------------- RESUMEN FINAL JSON
    summary = {
        "seed": SEED,
        "ENDES_label": ENDES_LABEL,
        "N_endes": 14428,
        "n_confirmatorio": int(len(focus)),
        "n_treated": int(focus["T5_ge1"].sum()),
        "n_control": int((1 - focus["T5_ge1"]).sum()),
        "max_abs_smd": float(max_smd),
        "w_p99": float(np.percentile(w_core, 99)),
        "w_max": float(np.max(w_core)),
        "n_trimmed_ps": int(n_trimmed_ps),
        "nnt": float(nnt_val) if not pd.isna(nnt_val) else None,
        "prevalencia_anemia_cruda": float(focus["anemia"].mean()),
        "hb_scale": "g/L",
        "upm": "hv001",
        "strata": "hv022 (240 estratos)",
        "primary_outcome_stats": {
            "outcome": "anemia_modsev",
            "ipw_design_ate": float(primary_df.loc[primary_df.outcome == "anemia_modsev", "ipw_design_ate"].values[0]),
            "boot_ci_low": float(primary_df.loc[primary_df.outcome == "anemia_modsev", "boot_ci_low"].values[0]),
            "boot_ci_high": float(primary_df.loc[primary_df.outcome == "anemia_modsev", "boot_ci_high"].values[0]),
            "p_boot": float(primary_df.loc[primary_df.outcome == "anemia_modsev", "p_boot"].values[0]),
        },
        "holm_p_values": {row["outcome"]: row["holm_p"] for _, row in primary_df.iterrows()},
        "main_effects": primary_df.to_dict("records"),
        "e_values": ev_df.to_dict("records"),
        "bootstrap_iterations": 500,
        "bootstrap_method": "stratified cluster (hv001 within hv022)",
        "inclusion_ipw": incl_df.to_dict("records") if len(incl_df) else [],
        "evalue_benchmark": ebench.to_dict("records") if len(ebench) else [],
        "mde_poder": mde_df.to_dict("records") if len(mde_df) else [],
        "impacto_poblacional": impact_df.to_dict("records") if len(impact_df) else [],
        "eligibility_functions": ["build_eligibility", "make_analytic_sample"],
        "pauta_extra_tables": [
            "tabla_S_heterogeneidad_dpto.csv",
            "tabla_S_interacciones.csv",
            "tabla_S_nnt_subgrupos.csv",
            "tabla_S_pate_exploratorio.csv",
            "tabla_S_ps_survey_weighted.csv",
            "tabla_S_peores_escenarios.csv",
            "tabla_S_elegibilidad_reglas.csv",
            "tabla_S_lee_bounds.csv",
            "tabla_S_mediacion_diarrea.csv",
            "tabla_S_transporte.csv",
            "tabla_S_sandwich_survey.csv",
            "tabla_S_literatura_comparativa.csv",
        ],
        "mejoras_repo_only": {
            "lee_bounds": True,
            "mediacion_diarrea": True,
            "transporte": True,
            "sandwich_cluster": True,
            "literatura_comparativa": True,
        },
    }
    (TAB / "resumen_final.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n" + "=" * 60)
    print("OK. Tablas en", TAB, "| Figuras en", FIG)
    print("=" * 60)


if __name__ == "__main__":
    main()
