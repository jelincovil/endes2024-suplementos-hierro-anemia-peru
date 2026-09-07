#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner rápido: solo genera las tablas de mejoras repo-only (post meta 95).
No re-ejecuta bootstrap 500 ni subsampling 1000.

Uso:
    python pipeline_mejoras_repo.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pandas as pd

warnings.filterwarnings("ignore")

# Reutilizar pipeline principal (mismo directorio analysis/)
from pipeline_informe_final import (  # noqa: E402
    BASE_COVARIATES_CORE,
    DATA,
    SEED,
    TAB,
    lee_bounds_selection,
    literature_comparison_table,
    make_analytic_sample,
    mediation_diarrhea_analysis,
    prepare_raw,
    sandwich_survey_se,
    transport_weights_analysis,
)


def main() -> int:
    print("=" * 60)
    print("PIPELINE MEJORAS REPO-ONLY — seed", SEED)
    print("=" * 60)
    if not Path(DATA).exists():
        print(f"ERROR: no se encuentra {DATA}", file=sys.stderr)
        return 2

    raw = pd.read_stata(DATA, convert_categoricals=False)
    df = prepare_raw(raw)
    focus_pop, focus, covs = make_analytic_sample(
        df, covariates=BASE_COVARIATES_CORE, include_design=True, include_dpto=True
    )
    print(f"Confirmatorio: n={len(focus)} tratados={int(focus['T5_ge1'].sum())}")

    print("\n[1/5] Lee bounds")
    lee_bounds_selection(focus_pop, focus, outcome="anemia_modsev")

    print("\n[2/5] Mediación diarrea")
    mediation_diarrhea_analysis(focus, covs, outcome="anemia_modsev")

    print("\n[3/5] Transporte IOSW-like")
    transport_weights_analysis(df, focus, BASE_COVARIATES_CORE, outcome="anemia_modsev")

    print("\n[4/5] Sandwich cluster SE")
    sandwich_survey_se(focus, covs, outcome="anemia_modsev")

    print("\n[5/5] Literatura comparativa")
    literature_comparison_table()

    print("\nOK. Tablas nuevas en", TAB)
    for name in [
        "tabla_S_lee_bounds.csv",
        "tabla_S_mediacion_diarrea.csv",
        "tabla_S_transporte.csv",
        "tabla_S_sandwich_survey.csv",
        "tabla_S_literatura_comparativa.csv",
    ]:
        p = TAB / name
        print(f"  {'✓' if p.exists() else '✗'} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
