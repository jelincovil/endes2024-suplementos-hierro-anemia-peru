#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autocheck: verifica la consistencia interna de los artefactos del pipeline
(CSV/JSON) y sus anclas clave, SIN depender del manuscrito (que se somete a la
revista aparte y no forma parte del repositorio).

Comprueba:
  - presencia de tablas críticas y de mejoras;
  - artículo principal: RD e IC bootstrap (B=2000) de IPW×diseño;
  - especificaciones del cuerpo (departamental, sin restricción, 12 meses);
  - semilla y muestra confirmatoria en resumen_final.json.

Escribe paper/tablas/autocheck_pipeline.json; sale 0 si todo pasa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "paper" / "tablas"

TABLAS_OBLIGATORIAS = [
    "tabla_0_flujo_muestral.csv",
    "tabla_1_caracteristicas.csv",
    "tabla_2_efectos_primarios.csv",
    "tabla_sensibilidades_cuerpo.csv",
    "tabla_3_robustez.csv",
    "tabla_S1_missingness.csv",
    "tabla_S2_balance_smd.csv",
    "tabla_S8_mice.csv",
    # mejoras repo-only
    "tabla_S_lee_bounds.csv",
    "tabla_S_mediacion_diarrea.csv",
    "tabla_S_transporte.csv",
    "tabla_S_sandwich_survey.csv",
    "tabla_S_literatura_comparativa.csv",
]

FIGURAS_CUERPO = [
    "figura_flujo_muestral.png",
    "figura_1_love_plot.png",
    "figura_bosque_esencial.png",
]


def main() -> int:
    checks = []
    sens_path = TAB / "tabla_sensibilidades_cuerpo.csv"
    res_path = TAB / "resumen_final.json"
    sens_json_path = TAB / "resumen_sensibilidades_cuerpo.json"

    ok_files = sens_path.exists() and res_path.exists()
    checks.append({"id": "files", "pass": ok_files,
                   "detail": "tabla_sensibilidades_cuerpo + resumen_final"})

    if sens_path.exists():
        sens = pd.read_csv(sens_path)
        row = sens[sens["spec_id"] == "principal"].iloc[0]
        rd = float(row["estimate"])
        lo = float(row["boot_ci_low"])
        hi = float(row["boot_ci_high"])
        boot_n = int(row["boot_n"]) if pd.notna(row.get("boot_n")) else 0
        checks.append({
            "id": "rd_modsev_ipw_design",
            "pass": abs(rd - (-0.027924)) < 0.0005 and lo < 0 and hi < 0,
            "detail": f"RD mod/sev = {rd:.5f}, IC [{lo:.5f}; {hi:.5f}]",
            "value": rd,
        })
        checks.append({
            "id": "bootstrap_2000",
            "pass": boot_n >= 2000,
            "detail": f"bootstrap_n={boot_n}",
            "value": boot_n,
        })
        n_t = int(row["n_consumo"]) if pd.notna(row.get("n_consumo")) else -1
        checks.append({
            "id": "n_expuestos",
            "pass": n_t == 2194,
            "detail": f"n_expuestos={n_t}",
            "value": n_t,
        })
        dep = sens[sens["spec_id"] == "departamental"].iloc[0]
        unr = sens[sens["spec_id"] == "sin_restriccion"].iloc[0]
        alt = sens[sens["spec_id"] == "consumo_12m"].iloc[0]
        checks.append({
            "id": "sens_ci_present",
            "pass": pd.notna(dep["boot_ci_low"]) and pd.notna(unr["boot_ci_low"]) and pd.notna(alt["boot_ci_low"]),
            "detail": "IC bootstrap en departamental, sin restricción y 12 meses",
        })
        checks.append({
            "id": "sin_restriccion_especificada",
            "pass": int(unr["n"]) == 8800,
            "detail": f"sin_restriccion n={int(unr['n'])} (8800 esperado)",
        })

    if res_path.exists():
        res = json.loads(res_path.read_text(encoding="utf-8"))
        checks.append({
            "id": "seed",
            "pass": res.get("seed") == 20260710,
            "detail": f"seed={res.get('seed')}",
        })
        checks.append({
            "id": "n_confirmatorio",
            "pass": res.get("n_confirmatorio") == 6703 and res.get("n_treated") == 2194,
            "detail": f"n={res.get('n_confirmatorio')}, tratados={res.get('n_treated')}",
        })
        stats = res.get("primary_outcome_stats", {})
        checks.append({
            "id": "ancla_resumen_final",
            "pass": abs(stats.get("ipw_design_ate", 0) - (-0.0279244004)) < 1e-6
                    and abs(stats.get("boot_ci_low", 0) - (-0.0434124123)) < 1e-6,
            "detail": "RD e IC del cuerpo consistentes con resumen_final.json",
        })

    if sens_json_path.exists():
        sens_meta = json.loads(sens_json_path.read_text(encoding="utf-8"))
        checks.append({
            "id": "ancla_cuerpo_json",
            "pass": int(sens_meta.get("bootstrap_iterations", 0)) >= 2000,
            "detail": "resumen_sensibilidades_cuerpo.json es ancla del cuerpo",
        })

    for name in TABLAS_OBLIGATORIAS:
        checks.append({"id": f"exists_{name}", "pass": (TAB / name).exists(), "detail": name})

    fig_root = ROOT / "paper" / "figuras"
    for name in FIGURAS_CUERPO:
        checks.append({"id": f"exists_{name}", "pass": (fig_root / name).exists(), "detail": name})

    n_pass = sum(1 for c in checks if c["pass"])
    n_fail = len(checks) - n_pass
    result = {
        "n_checks": len(checks),
        "n_pass": n_pass,
        "n_fail": n_fail,
        "n_critical_fail": n_fail,
        "all_critical_pass": n_fail == 0,
        "checks": checks,
    }
    TAB.mkdir(parents=True, exist_ok=True)
    out = TAB / "autocheck_pipeline.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Autocheck: {n_pass}/{len(checks)} pass | critical_fail={n_fail}")
    print(f"→ {out}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
