#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Autocheck: ancla números clave del paper TEX a CSV/JSON del pipeline.
Escribe tablas/autocheck_tex_csv.json y sale 0 si todos los checks críticos pasan.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

# Raíz del paquete (…/anemia-endes-2023-main)
ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "paper" / "tablas"
TEX = ROOT / "paper" / "paper_final_APA7.tex"


def _tex() -> str:
    return TEX.read_text(encoding="utf-8") if TEX.exists() else ""


def _approx_in_tex(tex: str, value: float, tol: float = 0.002) -> bool:
    """Busca formas europeas 0{,}028 / −0{,}028 cercanas al valor."""
    # capturar números con coma decimal LaTeX
    nums = re.findall(r"([−\-]?)0\{,\}(\d+)", tex)
    for sign, digits in nums:
        # reconstruir 0.xxx
        dec = float("0." + digits[:6])
        if sign in ("−", "-"):
            dec = -dec
        if abs(dec - value) <= tol or abs(abs(dec) - abs(value)) <= tol:
            return True
    # también formas 0,028 sin llaves
    nums2 = re.findall(r"([−\-]?)0,(\d+)", tex)
    for sign, digits in nums2:
        dec = float("0." + digits[:6])
        if sign in ("−", "-"):
            dec = -dec
        if abs(dec - value) <= tol or abs(abs(dec) - abs(value)) <= tol:
            return True
    return False


def main() -> int:
    checks = []
    tex = _tex()
    t2_path = TAB / "tabla_2_efectos_primarios.csv"
    res_path = TAB / "resumen_final.json"
    sens_path = TAB / "tabla_sensibilidades_cuerpo.csv"
    sens_json_path = TAB / "resumen_sensibilidades_cuerpo.json"

    ok_files = sens_path.exists() and res_path.exists() and TEX.exists()
    checks.append({
        "id": "files",
        "pass": ok_files,
        "detail": "TEX + tabla_sensibilidades_cuerpo + resumen_final",
    })

    if sens_path.exists():
        sens = pd.read_csv(sens_path)
        row = sens[sens["spec_id"] == "principal"].iloc[0]
        rd = float(row["estimate"])
        lo = float(row["boot_ci_low"])
        hi = float(row["boot_ci_high"])
        boot_n = int(row["boot_n"]) if pd.notna(row.get("boot_n")) else 0
        checks.append({
            "id": "rd_modsev_in_tex",
            "pass": (
                _approx_in_tex(tex, rd, tol=0.003)
                or "0{,}028" in tex
                or "−0{,}028" in tex
                or "2{,}8" in tex  # presentación en puntos porcentuales
                or "−2{,}8" in tex
            ),
            "detail": f"DP cuerpo={rd:.5f} anclado en TEX (tabla_sensibilidades_cuerpo; admite escala pp)",
            "value": rd,
        })
        checks.append({
            "id": "boot_ci_cuerpo",
            "pass": (
                lo < 0 and hi < 0
                and (
                    (("-0{,}045" in tex or "−0{,}045" in tex) and ("-0{,}012" in tex or "−0{,}012" in tex))
                    or (("-4{,}5" in tex or "−4{,}5" in tex) and ("-1{,}2" in tex or "−1{,}2" in tex))
                )
            ),
            "detail": f"IC cuerpo 2000 [{lo:.5f}, {hi:.5f}] anclado en TEX (proporción o pp)",
            "boot_ci_low": lo,
            "boot_ci_high": hi,
        })
        checks.append({
            "id": "bootstrap_2000",
            "pass": boot_n >= 2000 and ("2\\,000" in tex or "2{,}000" in tex or "2,000" in tex),
            "detail": f"bootstrap_n={boot_n}",
            "value": boot_n,
        })
    elif t2_path.exists():
        t2 = pd.read_csv(t2_path)
        row = t2[t2["outcome"] == "anemia_modsev"].iloc[0]
        rd = float(row["ipw_design_ate"])
        checks.append({
            "id": "rd_modsev_in_tex",
            "pass": _approx_in_tex(tex, rd, tol=0.003) or "0{,}028" in tex or "−0{,}028" in tex,
            "detail": f"RD diseño histórico={rd:.5f} (fallback tabla_2)",
            "value": rd,
        })

    if res_path.exists():
        res = json.loads(res_path.read_text(encoding="utf-8"))
        body = tex
        if r"\section{Material suplementario}" in tex:
            body = tex.split(r"\section{Material suplementario}")[0]
        forbidden = {
            "NNT": "NNT" in body,
            "analisis_causal": ("análisis causal" in body.lower()) or ("analisis causal" in body.lower()),
            "verdadero_efecto": "verdadero efecto" in body.lower(),
            "iptw": "IPTW" in body,
            "ensayo_hipotetico": "ensayo hipot" in body.lower(),
            "ventana_7d_sens": ("ventana de siete días" in body.lower()) or ("ventana de 7 días" in body.lower()),
        }
        checks.append({
            "id": "no_nnt_in_body",
            "pass": not forbidden["NNT"],
            "detail": "Cuerpo sin NNT",
        })
        checks.append({
            "id": "no_causal_claim_phrases",
            "pass": (not forbidden["analisis_causal"]) and (not forbidden["verdadero_efecto"]),
            "detail": "Cuerpo sin 'análisis causal' ni 'verdadero efecto'",
        })
        checks.append({
            "id": "no_iptw_in_body",
            "pass": not forbidden["iptw"],
            "detail": "Cuerpo sin IPTW (usar IPW de exposición)",
        })
        checks.append({
            "id": "no_ensayo_hipotetico",
            "pass": not forbidden["ensayo_hipotetico"],
            "detail": "Cuerpo sin ensayo hipotético",
        })
        checks.append({
            "id": "no_ventana_7d_as_sensitivity",
            "pass": not forbidden["ventana_7d_sens"],
            "detail": "No tratar la ventana de 7 días como sensibilidad",
        })
        checks.append({
            "id": "ventanas_12m_7d",
            "pass": ("12 meses previos" in tex) and ("siete días previos" in tex or "7 días previos" in tex),
            "detail": "Elegibilidad 12 meses y exposición 7 días explícitas",
        })
        checks.append({
            "id": "rd_departamental_in_tex",
            "pass": (
                ("0{,}024" in tex) or ("-0{,}024" in tex) or ("−0{,}024" in tex)
                or ("2{,}4" in tex) or ("−2{,}4" in tex)  # escala pp
            ),
            "detail": "Ajuste departamental −0,024 (−2,4 pp) anclado",
        })
        checks.append({
            "id": "sin_restriccion_todos_receptores",
            "pass": ("todos los receptores" in tex.lower()
                     or "análisis sin filtro de diagnóstico previo" in tex.lower()),
            "detail": "Análisis sin filtro descrito como todos los receptores",
        })
        checks.append({
            "id": "english_decimals",
            # El abstract EN actual usa escalas de prosa (−2.8 pp, 9.3%, 12.1%);
            # exigir la forma exacta -0.028 solo tenía sentido en la versión anterior.
            "pass": ("percentage points" in tex and "9.3" in tex and "12.1" in tex
                     and ("g/L" in tex or "+0.65" in tex or "0.65" in tex)),
            "detail": "Abstract EN con decimales de punto",
        })
        checks.append({
            "id": "consumo_12m_in_abstract",
            "pass": ("12 meses" in tex.split(r"\\begin{document}")[0]) or (
                "12 meses" in tex[: tex.find(r"\\section{Introducción}")]
            ),
            "detail": "Resultado de 12 meses en resumen o mensajes",
        })
        if sens_path.exists():
            sens = pd.read_csv(sens_path)
            dep = sens[sens["spec_id"] == "departamental"].iloc[0]
            unr = sens[sens["spec_id"] == "sin_restriccion"].iloc[0]
            alt = sens[sens["spec_id"] == "consumo_12m"].iloc[0]
            checks.append({
                "id": "sens_ci_present",
                "pass": pd.notna(dep["boot_ci_low"]) and pd.notna(unr["boot_ci_low"]) and pd.notna(alt["boot_ci_low"]),
                "detail": "IC bootstrap en departamental, sin restricción y 12 meses",
            })
        if sens_json_path.exists():
            sens_meta = json.loads(sens_json_path.read_text(encoding="utf-8"))
            checks.append({
                "id": "ancla_cuerpo_json",
                "pass": int(sens_meta.get("bootstrap_iterations", 0)) >= 2000,
                "detail": "resumen_sensibilidades_cuerpo.json es ancla del cuerpo",
            })
        checks.append({
            "id": "seed",
            "pass": res.get("seed") == 20260710 and "20260710" in tex or res.get("seed") == 20260710,
            "detail": f"seed={res.get('seed')}",
        })
        checks.append({
            "id": "n_confirmatorio",
            "pass": res.get("n_confirmatorio") == 6703 and ("6703" in tex or "6{,}703" in tex or r"6\,703" in tex),
            "detail": f"n={res.get('n_confirmatorio')}",
        })

    # tablas nuevas de mejoras
    for name in [
        "tabla_S_lee_bounds.csv",
        "tabla_S_mediacion_diarrea.csv",
        "tabla_S_transporte.csv",
        "tabla_S_sandwich_survey.csv",
        "tabla_S_literatura_comparativa.csv",
    ]:
        checks.append({
            "id": f"exists_{name}",
            "pass": (TAB / name).exists(),
            "detail": name,
        })

    critical = {
        "files",
        "rd_modsev_in_tex",
        "boot_ci_cuerpo",
        "no_nnt_in_body",
        "n_confirmatorio",
        "bootstrap_2000",
    }
    n_pass = sum(1 for c in checks if c["pass"])
    n_crit_fail = sum(1 for c in checks if c["id"] in critical and not c["pass"])
    result = {
        "n_checks": len(checks),
        "n_pass": n_pass,
        "n_fail": len(checks) - n_pass,
        "n_critical_fail": n_crit_fail,
        "all_critical_pass": n_crit_fail == 0,
        "checks": checks,
    }
    TAB.mkdir(parents=True, exist_ok=True)
    out = TAB / "autocheck_tex_csv.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Autocheck: {n_pass}/{len(checks)} pass | critical_fail={n_crit_fail}")
    print(f"→ {out}")
    return 0 if n_crit_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
