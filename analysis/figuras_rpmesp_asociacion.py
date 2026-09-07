#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figuras del cuerpo RPMESP (asociación / implementación).

No reestima modelos. Usa paper/tablas/*.csv.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "paper" / "tablas"
FIG = ROOT / "paper" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 10,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

C = {
    "blue": "#1f4e79",
    "blue_fill": "#d6e6f5",
    "teal": "#0d6e6e",
    "teal_fill": "#d4efef",
    "coral": "#a33b3b",
    "coral_fill": "#f5d9d9",
    "gray": "#5a5a5a",
    "gray_fill": "#f0f0f0",
    "line": "#333333",
    "post": "#2b6cb0",
}


def _save(fig: plt.Figure, name: str) -> None:
    path = FIG / name
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  → {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def figura_flujo() -> None:
    fig, ax = plt.subplots(figsize=(8.4, 9.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    def box(x, y, w, h, title, body, fc, ec):
        p = FancyBboxPatch(
            (x - w / 2, y - h / 2),
            w,
            h,
            boxstyle="round,pad=0.02,rounding_size=0.08",
            facecolor=fc,
            edgecolor=ec,
            linewidth=1.4,
            zorder=3,
        )
        ax.add_patch(p)
        ax.text(x, y + 0.18, title, ha="center", va="center", fontsize=10, fontweight="bold", color=ec, zorder=4)
        ax.text(x, y - 0.22, body, ha="center", va="center", fontsize=8.4, color=C["line"], zorder=4, linespacing=1.25)

    def arrow(y0, y1):
        ax.add_patch(
            FancyArrowPatch(
                (5, y0),
                (5, y1),
                arrowstyle="-|>",
                mutation_scale=12,
                linewidth=1.3,
                color=C["line"],
                zorder=2,
            )
        )

    box(5, 11.1, 7.6, 1.15, "ENDES 2024", "Niños de 6 a 59 meses con hemoglobina capilar\nN = 14 428", C["blue_fill"], C["blue"])
    arrow(10.52, 9.78)
    box(5, 9.15, 7.6, 1.15, "Receptores de suplementos", "Recibieron al menos una presentación de suplemento (12 meses)\nn = 9 079   ·   excluidos: 5 349 no receptores", C["teal_fill"], C["teal"])
    arrow(8.57, 7.83)
    box(5, 7.20, 7.6, 1.15, "Sin diagnóstico previo reportado", "Población de análisis principal\nn = 6 908   ·   excluidos: 2 171 con diagnóstico previo", C["teal_fill"], C["teal"])
    arrow(6.62, 5.88)
    box(5, 5.25, 7.6, 1.15, "Casos completos en covariables", "Muestra analítica\nn = 6 703   ·   excluidos: 205 (sobre todo anemia materna)", C["blue_fill"], C["blue"])
    arrow(4.67, 3.95)

    box(2.55, 2.85, 4.2, 1.35, "Consumo reportado", "Al menos una toma en 7 días\nn = 2 194", "#e8f5e9", "#1b7a4e")
    box(7.45, 2.85, 4.2, 1.35, "Recepción sin consumo reportado", "Sin toma en 7 días\nn = 4 509", C["gray_fill"], C["gray"])

    ax.text(
        5,
        1.35,
        "La restricción por diagnóstico previo define el subgrupo principal\ny puede introducir selección. El análisis sin esa restricción se informa en el texto.",
        ha="center",
        va="center",
        fontsize=8,
        color=C["gray"],
    )
    fig.tight_layout()
    _save(fig, "figura_flujo_muestral.png")


def figura_bosque() -> None:
    import pandas as pd

    sens = pd.read_csv(TAB / "tabla_sensibilidades_cuerpo.csv")
    labels = {
        "principal": "Anemia moderada o severa\nIPW × diseño (referencia)",
        "departamental": "Con ajuste departamental",
        "sin_restriccion": "Todos los receptores,\nsin filtro de diagnóstico",
        "consumo_12m": "Consumo reportado en 12 meses",
    }
    rows = []
    for spec_id, lab in labels.items():
        r = sens.loc[sens["spec_id"] == spec_id].iloc[0]
        lo = float(r["boot_ci_low"]) if pd.notna(r["boot_ci_low"]) else None
        hi = float(r["boot_ci_high"]) if pd.notna(r["boot_ci_high"]) else None
        rows.append((lab, float(r["estimate"]), lo, hi, spec_id == "principal", "dp"))
    rows.append(("Hemoglobina MINSA (g/L)", 0.654, -0.039, 1.240, False, "hb"))

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 5.0), gridspec_kw={"width_ratios": [1.45, 1.0]})

    def draw(ax, subset, xlabel, title, xlim):
        data = [(i, r) for i, r in enumerate(subset)]
        yy = np.arange(len(data))[::-1]
        for i, r in enumerate(subset):
            lab, est, lo, hi, primary, _ = r
            y = yy[i]
            color = C["coral"] if primary else C["post"]
            if lo is not None and hi is not None:
                ax.errorbar(
                    est,
                    y,
                    xerr=[[est - lo], [hi - est]],
                    fmt="o",
                    color=color,
                    ecolor=color,
                    elinewidth=1.8 if primary else 1.3,
                    capsize=3.5,
                    markersize=8 if primary else 6.5,
                )
            else:
                ax.plot(est, y, "D", color=color, markersize=7)
            ax.text(xlim[1] - 0.02 * (xlim[1] - xlim[0]), y, f"{est:+.3f}", va="center", ha="right", fontsize=8, color=color)
        ax.axvline(0, color="#888888", ls="--", lw=1.0)
        ax.set_yticks(yy)
        ax.set_yticklabels([r[0] for r in subset], fontsize=8.6)
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_title(title, fontweight="bold", loc="left", fontsize=10.5)
        ax.set_xlim(*xlim)

    dp = [r for r in rows if r[5] == "dp"]
    hb = [r for r in rows if r[5] == "hb"]
    draw(axes[0], dp, "Diferencia de prevalencias", "A. Anemia moderada o severa", (-0.055, 0.055))
    draw(axes[1], hb, "Diferencia media, g/L", "B. Hemoglobina", (-0.4, 1.6))
    fig.suptitle(
        "Asociación del consumo reportado (IPW × diseño ENDES)",
        fontweight="bold",
        fontsize=12,
        y=1.02,
    )
    fig.tight_layout()
    _save(fig, "figura_bosque_esencial.png")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    figura_flujo()
    figura_bosque()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
