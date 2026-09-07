#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figura 3 del cuerpo — forest plot de asociación (IPW × diseño). MEJORADO.

Cambios respecto a la versión original:
1. Panel A poblado con 5 filas: las 4 especificaciones principales + anemia de cualquier grado.
2. Panel B poblado con 2 filas: Hb MINSA y Hb OMS (desenlaces secundarios).
3. Indicador visual de cruce del nulo: punto RELLENO cuando IC95 no incluye cero,
   punto VACÍO cuando IC95 incluye cero.
4. Banda sombreada alrededor del cero para facilitar lectura visual.
5. Labels más concisos y leyenda integrada.

Fuente: analysis/figuras_rpmesp_asociacion.py → figura_bosque()
PNG:    figura_bosque_esencial.png
Anclas:
  - paper/tablas/tabla_sensibilidades_cuerpo.csv
  - paper/tablas/tabla_2_efectos_primarios.csv
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _estilo import C, TAB, apply_style, es_axis_formatter, fmt_es, save


def generar() -> None:
    apply_style()
    sens = pd.read_csv(TAB / "tabla_sensibilidades_cuerpo.csv")
    prim = pd.read_csv(TAB / "tabla_2_efectos_primarios.csv")

    # --- Panel A: Anemia (diferencias de prevalencias) ---
    specs = {
        "principal": ("Referencia (IPW × diseño)", True),
        "departamental": ("+ Ajuste departamental", False),
        "sin_restriccion": ("Todos los receptores (sin filtro dx)", False),
        "consumo_12m": ("Consumo en 12 meses (def. alternativa)", False),
    }
    rows_a = []
    for spec_id, (lab, is_primary) in specs.items():
        r = sens.loc[sens["spec_id"] == spec_id].iloc[0]
        lo = float(r["boot_ci_low"]) if pd.notna(r["boot_ci_low"]) else None
        hi = float(r["boot_ci_high"]) if pd.notna(r["boot_ci_high"]) else None
        rows_a.append((lab, float(r["estimate"]), lo, hi, is_primary))

    # Anemia de cualquier grado (misma escala, del CSV primario o sensitividades)
    try:
        r_any = prim.loc[prim["outcome"] == "anemia_any"].iloc[0]
        rows_a.append((
            "Anemia (cualquier grado)",
            float(r_any["ipw_design_ate"]),
            float(r_any["boot_ci_low"]),
            float(r_any["boot_ci_high"]),
            False,
        ))
    except IndexError:
        pass  # si no existe en el CSV, se omite silenciosamente

    # --- Panel B: Hemoglobina (diferencias de medias, g/L) ---
    rows_b = []
    for out_key, out_label in [("hb_minsa", "Hemoglobina MINSA (g/L)"),
                                ("hb_oms", "Hemoglobina OMS (g/L)")]:
        try:
            r = prim.loc[prim["outcome"] == out_key].iloc[0]
            rows_b.append((
                out_label,
                float(r["ipw_design_ate"]),
                float(r["boot_ci_low"]) if pd.notna(r["boot_ci_low"]) else None,
                float(r["boot_ci_high"]) if pd.notna(r["boot_ci_high"]) else None,
                False,
            ))
        except IndexError:
            pass

    # Fallback si no hay datos de Hb OMS
    if not rows_b:
        hb = prim.loc[prim["outcome"] == "hb_minsa"].iloc[0]
        rows_b.append((
            "Hemoglobina MINSA (g/L)",
            float(hb["ipw_design_ate"]),
            float(hb["boot_ci_low"]),
            float(hb["boot_ci_high"]),
            False,
        ))

    # --- Figura ---
    fig, axes = plt.subplots(1, 2, figsize=(11.4, 5.4), gridspec_kw={"width_ratios": [1.55, 1.0]})

    def draw(ax, subset, xlabel, title, xlim, decimales_x=2):
        yy = np.arange(len(subset))[::-1]

        # Banda sombreada estrecha alrededor del cero
        ax.axvspan(-0.0008, 0.0008, color="#E8E8E8", zorder=0, alpha=0.9)
        ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)

        for i, r in enumerate(subset):
            lab, est, lo, hi, is_primary = r
            y = yy[i]

            # ¿Cruza el nulo?
            crosses = (lo is not None and hi is not None and lo <= 0 <= hi)

            # Color y estilo
            if is_primary:
                color = C["coral"]
                mfc = color
                ms = 9
                lw = 2.0
            elif not crosses:
                color = C["post"]  # azul oscuro
                mfc = color
                ms = 7
                lw = 1.4
            else:
                color = "#8CB4C4"  # azul apagado
                mfc = "white"      # vacío cuando cruza
                ms = 7
                lw = 1.4

            # Errorbar
            if lo is not None and hi is not None:
                ax.errorbar(
                    est, y,
                    xerr=[[est - lo], [hi - est]],
                    fmt="o",
                    color=color,
                    ecolor=color,
                    elinewidth=lw,
                    capsize=3.5,
                    markersize=ms,
                    markerfacecolor=mfc,
                    markeredgewidth=1.3 if crosses and not is_primary else 0,
                    zorder=3,
                )
            else:
                ax.plot(est, y, "o", color=color, markersize=ms,
                        markerfacecolor=mfc, markeredgewidth=1.3 if crosses else 0, zorder=3)

            # Valor numérico a la derecha
            ax.text(
                xlim[1] - 0.008,
                y,
                fmt_es(est, 3, signo=True),
                va="center",
                ha="right",
                fontsize=8.5,
                color=color,
                fontweight="bold" if is_primary else "normal",
                zorder=4,
            )

        ax.set_yticks(yy)
        ax.set_yticklabels([r[0] for r in subset], fontsize=8.8)
        ax.set_xlabel(xlabel, fontsize=9.2)
        ax.set_title(title, fontweight="bold", loc="left", fontsize=10.5)
        ax.set_xlim(*xlim)
        ax.xaxis.set_major_formatter(es_axis_formatter(decimales_x))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(axis="both", which="both", length=0)

    draw(axes[0], rows_a, "Diferencia de prevalencias", "A. Anemia", (-0.055, 0.055), decimales_x=2)
    draw(axes[1], rows_b, "Diferencia media (g/L)", "B. Hemoglobina", (-0.4, 1.6), decimales_x=1)

    # Leyenda integrada
    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C["coral"],
                markersize=9, label="Referencia"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=C["post"],
                markersize=7, label="IC del 95% no incluye nulo"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="white",
                markeredgecolor="#8CB4C4", markeredgewidth=1.3, markersize=7,
                label="IC del 95% incluye nulo"),
    ]
    fig.legend(
        handles=legend_elements,
        loc="lower center",
        ncol=3,
        fontsize=8,
        frameon=False,
        bbox_to_anchor=(0.5, -0.03),
    )

    fig.suptitle(
        "Asociación del consumo reportado con anemia y hemoglobina (IPW × diseño ENDES)",
        fontweight="bold",
        fontsize=11.5,
        y=1.02,
    )
    fig.tight_layout()
    save(fig, "figura_bosque_esencial.png")


if __name__ == "__main__":
    generar()
