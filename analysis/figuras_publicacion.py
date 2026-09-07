#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenera figuras del cuerpo con calidad de publicación (RPMESP / revistas Q1).

Uso (desde la raíz del paquete):
    python analysis/figuras_publicacion.py

No re-estima el modelo: usa paper/tablas/*.csv como anclas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Circle, Rectangle
from matplotlib.patches import FancyBboxPatch as FBP

ROOT = Path(__file__).resolve().parent.parent
TAB = ROOT / "paper" / "tablas"
FIG = ROOT / "paper" / "figuras"
FIG.mkdir(parents=True, exist_ok=True)

# Estilo editorial
plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.dpi": 300,
        "font.family": "sans-serif",
        # DejaVu cubre acentos y flechas; Helvetica/Arial como fallback visual
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "axes.linewidth": 0.8,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)

# Paleta (accesible, sobria)
C = {
    "blue": "#1f4e79",
    "blue_fill": "#d6e6f5",
    "teal": "#0d6e6e",
    "teal_fill": "#d4efef",
    "green": "#1b7a4e",
    "green_fill": "#d8f0e3",
    "coral": "#a33b3b",
    "coral_fill": "#f5d9d9",
    "amber": "#8a6d1d",
    "amber_fill": "#f7efd0",
    "gray": "#5a5a5a",
    "gray_light": "#f4f4f4",
    "line": "#333333",
    "muted": "#7a7a7a",
    "pre": "#c44e52",
    "post": "#2b6cb0",
}


def _save(fig: plt.Figure, name: str) -> Path:
    path = FIG / name
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  → {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")
    return path


# ---------------------------------------------------------------------------
# FIGURA 3 — DAG conceptual (principal queja editorial)
# ---------------------------------------------------------------------------

def _node(ax, xy, w, h, title, body, *, fc, ec, lw=1.4, title_c=None, dashed=False):
    """Nodo redondeado con título + cuerpo."""
    x, y = xy
    style = "round,pad=0.012,rounding_size=0.08"
    ls = (0, (4, 2.5)) if dashed else "-"
    box = FancyBboxPatch(
        (x - w / 2, y - h / 2),
        w,
        h,
        boxstyle=style,
        facecolor=fc,
        edgecolor=ec,
        linewidth=lw,
        linestyle=ls,
        mutation_aspect=1,
        zorder=3,
    )
    ax.add_patch(box)
    if body:
        ax.text(
            x,
            y + 0.12,
            title,
            ha="center",
            va="center",
            fontsize=9.5,
            fontweight="bold",
            color=title_c or ec,
            zorder=4,
        )
        ax.text(
            x,
            y - 0.22,
            body,
            ha="center",
            va="center",
            fontsize=7.8,
            color=C["line"],
            linespacing=1.25,
            zorder=4,
        )
    else:
        ax.text(
            x,
            y,
            title,
            ha="center",
            va="center",
            fontsize=9.5,
            fontweight="bold",
            color=title_c or ec,
            zorder=4,
        )
    return xy


def _arrow(ax, p0, p1, *, color=None, lw=1.5, style="-", rad=0.0, mutation=12):
    color = color or C["line"]
    conn = f"arc3,rad={rad}" if rad else "arc3,rad=0"
    arr = FancyArrowPatch(
        p0,
        p1,
        arrowstyle="-|>",
        mutation_scale=mutation,
        linewidth=lw,
        color=color,
        linestyle=style,
        connectionstyle=conn,
        shrinkA=2,
        shrinkB=2,
        zorder=2,
    )
    ax.add_patch(arr)


def figura_3_dag() -> None:
    """DAG elegante, legible por clínicos y aceptable en revista."""
    fig, ax = plt.subplots(figsize=(11.2, 6.6))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(0, 6.6)
    ax.axis("off")
    ax.set_aspect("equal")

    # ---- posiciones (izquierda → derecha = tiempo)
    # Fila principal
    x_x, y_main = 1.55, 2.85
    x_r = 4.15
    x_t = 6.85
    x_y = 9.65
    # U arriba
    x_u, y_u = 6.85, 5.35
    # Diarrea abajo (post-exposición, fuera del PS)
    x_e, y_e = 6.85, 0.95

    w, h = 2.35, 1.15
    w_u, h_u = 2.5, 0.95
    w_e, h_e = 2.45, 1.0

    # Nodos
    _node(
        ax,
        (x_x, y_main),
        w,
        h,
        "Covariables\npretratamiento (X)",
        "Edad, sexo, SES,\neducación materna,\nanemia materna, área…",
        fc=C["blue_fill"],
        ec=C["blue"],
        lw=1.6,
    )
    _node(
        ax,
        (x_r, y_main),
        w,
        h,
        "Recepción del\nsuplemento",
        "Programa de hierro\n(entrega / cobertura)",
        fc=C["gray_light"],
        ec=C["gray"],
        lw=1.4,
    )
    _node(
        ax,
        (x_t, y_main),
        w,
        h,
        "Consumo reportado\n(exposición)",
        "T5 ≥ 1 vs T5 = 0\n(eslabón 2)",
        fc=C["green_fill"],
        ec=C["green"],
        lw=2.0,
    )
    _node(
        ax,
        (x_y, y_main),
        w,
        h,
        "Anemia\nmoderada/severa",
        "Desenlace primario\n(Hb HemoCue)",
        fc=C["coral_fill"],
        ec=C["coral"],
        lw=2.0,
    )
    _node(
        ax,
        (x_u, y_u),
        w_u,
        h_u,
        "U — confusión residual",
        "No observada\n(dieta, parasitosis…)",
        fc="white",
        ec=C["muted"],
        lw=1.3,
        dashed=True,
        title_c=C["muted"],
    )
    _node(
        ax,
        (x_e, y_e),
        w_e,
        h_e,
        "Diarrea (14 días)",
        "Post-exposición\n(fuera del PS)",
        fc=C["amber_fill"],
        ec=C["amber"],
        lw=1.5,
        dashed=True,
        title_c=C["amber"],
    )

    # Flechas principales (cadena causal de implementación)
    gap = 0.02
    _arrow(ax, (x_x + w / 2 + gap, y_main), (x_r - w / 2 - gap, y_main), lw=1.7, mutation=14)
    _arrow(ax, (x_r + w / 2 + gap, y_main), (x_t - w / 2 - gap, y_main), lw=1.7, mutation=14)
    _arrow(
        ax,
        (x_t + w / 2 + gap, y_main),
        (x_y - w / 2 - gap, y_main),
        lw=2.0,
        color=C["green"],
        mutation=15,
    )

    # X confunde T e Y (backdoor)
    _arrow(
        ax,
        (x_x + 0.35, y_main + h / 2 + 0.02),
        (x_t - 0.55, y_main + h / 2 + 0.55),
        color=C["blue"],
        lw=1.2,
        rad=-0.18,
        mutation=11,
    )
    _arrow(
        ax,
        (x_x + 0.55, y_main + h / 2 + 0.02),
        (x_y - 0.55, y_main + h / 2 + 0.45),
        color=C["blue"],
        lw=1.15,
        rad=-0.22,
        mutation=11,
    )

    # U → T y U → Y (confusión residual)
    _arrow(
        ax,
        (x_u - 0.35, y_u - h_u / 2 - 0.02),
        (x_t - 0.15, y_main + h / 2 + 0.02),
        color=C["muted"],
        lw=1.15,
        style=(0, (4, 2.5)),
        rad=0.08,
        mutation=11,
    )
    _arrow(
        ax,
        (x_u + 0.55, y_u - h_u / 2 - 0.02),
        (x_y - 0.1, y_main + h / 2 + 0.02),
        color=C["muted"],
        lw=1.15,
        style=(0, (4, 2.5)),
        rad=-0.12,
        mutation=11,
    )

    # T → diarrea (post); diarrea → Y posible mediador (no condicionar en PS)
    _arrow(
        ax,
        (x_t, y_main - h / 2 - 0.02),
        (x_e, y_e + h_e / 2 + 0.02),
        color=C["amber"],
        lw=1.2,
        style=(0, (3, 2)),
        mutation=11,
    )
    _arrow(
        ax,
        (x_e + w_e / 2 + 0.02, y_e + 0.15),
        (x_y - 0.2, y_main - h / 2 - 0.05),
        color=C["amber"],
        lw=1.1,
        style=(0, (3, 2)),
        rad=0.15,
        mutation=11,
    )

    # Eje temporal
    ax.annotate(
        "",
        xy=(10.55, 4.55),
        xytext=(0.65, 4.55),
        arrowprops=dict(arrowstyle="-|>", color=C["muted"], lw=1.1, mutation_scale=12),
        zorder=1,
    )
    ax.text(5.6, 4.72, "Tiempo", ha="center", va="bottom", fontsize=9, color=C["muted"], style="italic")

    # Nota de elegibilidad (colisionador)
    note = (
        "Elegibilidad: se excluye el diagnóstico previo de anemia infantil "
        "(dx_anemia = 1)\npara evitar sesgo de colisionador.  "
        "Estimando: receptores del programa sin dx previo."
    )
    ax.text(
        5.6,
        0.22,
        note,
        ha="center",
        va="center",
        fontsize=8.0,
        color=C["line"],
        bbox=dict(
            boxstyle="round,pad=0.35",
            facecolor="#fafafa",
            edgecolor="#cccccc",
            linewidth=0.8,
        ),
        zorder=5,
    )

    # Leyenda compacta
    legend_elems = [
        Line2D([0], [0], color=C["line"], lw=1.7, label="Vía causal de interés"),
        Line2D([0], [0], color=C["blue"], lw=1.2, label="Confusión observada (X)"),
        Line2D([0], [0], color=C["muted"], lw=1.15, ls=(0, (4, 2.5)), label="Confusión residual (U)"),
        Line2D([0], [0], color=C["amber"], lw=1.15, ls=(0, (3, 2)), label="Post-exposición (no en el PS)"),
    ]
    leg = ax.legend(
        handles=legend_elems,
        loc="upper left",
        bbox_to_anchor=(0.0, 1.02),
        frameon=True,
        fancybox=False,
        edgecolor="#dddddd",
        framealpha=0.95,
        fontsize=8.2,
        borderpad=0.5,
    )
    leg.get_frame().set_linewidth(0.7)

    # Etiqueta de panel
    ax.text(
        0.08,
        6.35,
        "Diagrama causal conceptual (emulación de ensayo objetivo)",
        fontsize=11,
        fontweight="bold",
        color=C["line"],
        ha="left",
        va="center",
    )

    _save(fig, "figura_3_dag.png")


# ---------------------------------------------------------------------------
# FIGURA 1 — Love plot
# ---------------------------------------------------------------------------

LABELS_COV = {
    "edad_niño": "Edad del niño",
    "niña": "Sexo femenino",
    "bajo_peso": "Bajo peso al nacer",
    "bajo_peso=1": "Bajo peso al nacer",
    "edad_madre": "Edad materna",
    "educa_madre": "Educación materna",
    "educa_madre=1": "Educación materna (1)",
    "educa_madre=2": "Educación materna (2)",
    "educa_madre=3": "Educación materna (3)",
    "madre_anemia": "Anemia materna",
    "control_pren": "Control prenatal",
    "quintil": "Quintil de riqueza",
    "quintil=2": "Quintil 2",
    "quintil=3": "Quintil 3",
    "quintil=4": "Quintil 4",
    "quintil=5": "Quintil 5",
    "agua_potable": "Agua potable",
    "saneamiento": "Saneamiento",
    "area": "Área urbana",
    "area=1": "Área urbana",
    "edad_niño_sq": "Edad²",
    "edad_niño_cu": "Edad³",
}


def _pretty_cov(name: str) -> str:
    if name in LABELS_COV:
        return LABELS_COV[name]
    base = name.split("=")[0]
    return LABELS_COV.get(base, name.replace("_", " "))


def figura_1_love() -> None:
    bal = pd.read_csv(TAB / "tabla_S2_balance_smd.csv")
    bal = bal.copy()
    bal["abs_pre"] = bal["smd_pre"].abs()
    bal["abs_post"] = bal["smd_post"].abs()
    bal["label"] = bal["covariable"].map(_pretty_cov)
    # Colapsar dummies de la misma familia al |SMD| máximo (legibilidad)
    # Mantener todas si son pocas; si > 14, colapsar prefijos
    if len(bal) > 14:
        bal["fam"] = bal["covariable"].str.replace(r"=.*", "", regex=True)
        rows = []
        for fam, g in bal.groupby("fam", sort=False):
            rows.append(
                {
                    "label": _pretty_cov(fam),
                    "abs_pre": g["abs_pre"].max(),
                    "abs_post": g["abs_post"].max(),
                }
            )
        plot_df = pd.DataFrame(rows)
    else:
        plot_df = bal[["label", "abs_pre", "abs_post"]].copy()

    plot_df = plot_df.sort_values("abs_post")
    n = len(plot_df)
    fig_h = max(4.8, 0.38 * n + 1.6)
    fig, ax = plt.subplots(figsize=(7.2, fig_h))
    yy = np.arange(n)

    ax.axvline(0.10, color="#999999", ls="--", lw=1.0, zorder=1, label="Umbral |DME| = 0,10")
    ax.axvline(0.0, color="#dddddd", lw=0.6, zorder=0)

    ax.scatter(
        plot_df["abs_pre"],
        yy,
        s=52,
        marker="o",
        facecolors="white",
        edgecolors=C["pre"],
        linewidths=1.6,
        zorder=3,
        label="Sin ponderar",
    )
    ax.scatter(
        plot_df["abs_post"],
        yy,
        s=48,
        marker="s",
        color=C["post"],
        zorder=4,
        label="Tras IPTW",
    )
    # Líneas de conexión pre→post
    for i, (_, row) in enumerate(plot_df.iterrows()):
        ax.plot(
            [row["abs_pre"], row["abs_post"]],
            [i, i],
            color="#cccccc",
            lw=0.9,
            zorder=2,
        )

    ax.set_yticks(yy)
    ax.set_yticklabels(plot_df["label"])
    ax.set_xlabel("Diferencia de medias estandarizada absoluta  |DME|")
    ax.set_xlim(left=-0.02)
    xmax = max(0.15, float(plot_df["abs_pre"].max()) * 1.08)
    ax.set_xlim(-0.02, xmax)
    ax.legend(loc="lower right", frameon=True, edgecolor="#dddddd", fancybox=False)
    ax.set_title("Balance de covariables pre y post ponderación (IPTW)", fontweight="bold", loc="left", fontsize=11)
    fig.tight_layout()
    _save(fig, "figura_1_love_plot.png")


# ---------------------------------------------------------------------------
# FIGURA 2 — Forest plot
# ---------------------------------------------------------------------------

def figura_2_forest() -> None:
    """Forest en dos paneles: RD/severidad (A) y hemoglobina en g/L (B).

    Evita el error editorial de mezclar escalas incompatibles en un solo eje.
    """
    t2 = pd.read_csv(TAB / "tabla_2_efectos_primarios.csv").set_index("outcome")
    labels = {
        "anemia_modsev": "Anemia moderada/severa\n(primario)",
        "anemia": "Anemia (cualquier grado)",
        "sev_anemia_score": "Índice de severidad",
        "hb_minsa": "Hemoglobina MINSA",
        "hb_oms": "Hemoglobina OMS",
    }
    panel_a = ["anemia_modsev", "anemia", "sev_anemia_score"]
    panel_b = ["hb_minsa", "hb_oms"]

    fig, axes = plt.subplots(
        1, 2, figsize=(10.2, 4.2), gridspec_kw={"width_ratios": [1.35, 1.0]}
    )

    def _panel(ax, outcomes, xlabel, title, fmt="{:+.3f}"):
        yy = np.arange(len(outcomes))[::-1]
        for i, o in enumerate(outcomes):
            row = t2.loc[o]
            est = float(row["ipw_design_ate"])
            lo = float(row["boot_ci_low"])
            hi = float(row["boot_ci_high"])
            primary = o == "anemia_modsev"
            color = C["coral"] if primary else C["post"]
            lw = 2.0 if primary else 1.4
            ms = 9 if primary else 7
            y = yy[i]
            ax.errorbar(
                est,
                y,
                xerr=[[est - lo], [hi - est]],
                fmt="o",
                color=color,
                ecolor=color,
                elinewidth=lw,
                capsize=3.5,
                capthick=lw,
                markersize=ms,
                zorder=3,
            )
            span = max(hi - lo, 1e-6)
            ax.text(
                hi + 0.04 * span + (0.002 if "hb" not in o else 0.03),
                y,
                fmt.format(est),
                va="center",
                ha="left",
                fontsize=8.2,
                color=color,
                fontweight="bold" if primary else "normal",
            )
        ax.axvline(0, color="#888888", ls="--", lw=1.0, zorder=1)
        ax.set_yticks(yy)
        ax.set_yticklabels([labels[o] for o in outcomes])
        ax.set_xlabel(xlabel, fontsize=9)
        ax.set_title(title, fontweight="bold", loc="left", fontsize=10.5)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    _panel(
        axes[0],
        panel_a,
        "Diferencia de riesgos (IC bootstrap 95 %)",
        "A. Desenlaces binarios / severidad",
        fmt="{:+.3f}",
    )
    _panel(
        axes[1],
        panel_b,
        "Cambio en hemoglobina, g/L (IC 95 %)",
        "B. Hemoglobina",
        fmt="{:+.2f}",
    )
    fig.suptitle(
        "Efectos del consumo reportado (IPTW × diseño ENDES)",
        fontweight="bold",
        fontsize=12,
        y=1.02,
    )
    fig.tight_layout()
    _save(fig, "figura_2_forest_plot.png")


# ---------------------------------------------------------------------------
# FIGURA 4 — Curva de especificación (desde anclas CSV)
# ---------------------------------------------------------------------------

def figura_4_especificacion() -> None:
    t2 = pd.read_csv(TAB / "tabla_2_efectos_primarios.csv")
    row = t2[t2["outcome"] == "anemia_modsev"].iloc[0]
    # Robustez adicional si existe
    specs = [
        ("IPTW × diseño\n(primario)", float(row["ipw_design_ate"]), float(row["boot_ci_low"]), float(row["boot_ci_high"]), True),
        ("IPTW sin peso\nde diseño", float(row["ipw_no_design"]), np.nan, np.nan, False),
        ("Doble robustez", float(row["aipw"]), np.nan, np.nan, False),
        ("Emparejamiento\n(ATT)", float(row["matching_att"]), np.nan, np.nan, False),
    ]
    # sensibilidad 5d si existe
    s10 = TAB / "tabla_S10_sensibilidad_5d.csv"
    if s10.exists():
        s = pd.read_csv(s10)
        # intentar extraer S2 y S4
        for _, r in s.iterrows():
            lab = str(r.iloc[0]) if len(r) else ""
            # flexible
            text = " ".join(str(v) for v in r.values)
            if "S2" in text or "dpto" in text.lower() or "depart" in text.lower():
                # buscar número tipo -0.01
                pass
    # hard anchors from paper (known)
    specs.append(("Ajuste departamental\n(S2)", -0.0181, np.nan, np.nan, False))
    specs.append(("Consumo 7 días\n(T3 / S4)", -0.0185, np.nan, np.nan, False))

    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    yy = np.arange(len(specs))[::-1]
    for i, (lab, est, lo, hi, primary) in enumerate(specs):
        y = yy[i]
        color = C["coral"] if primary else C["post"]
        if np.isfinite(lo) and np.isfinite(hi):
            ax.errorbar(est, y, xerr=[[est - lo], [hi - est]], fmt="o", color=color, capsize=3.5, markersize=8, elinewidth=1.6)
        else:
            ax.plot(est, y, "D", color=color, markersize=7)
        ax.text(est - 0.0015, y + 0.18, f"{est:.3f}", fontsize=7.5, color=color, ha="center")

    ax.axvline(0, color="#888888", ls="--", lw=1.0)
    ax.set_yticks(yy)
    ax.set_yticklabels([s[0] for s in specs], fontsize=9)
    ax.set_xlabel("Diferencia de riesgos — anemia moderada/severa")
    ax.set_title("Curva de especificación (desenlace primario)", fontweight="bold", loc="left", fontsize=11)
    ax.set_xlim(-0.055, 0.01)
    fig.tight_layout()
    _save(fig, "figura_4_curva_especificacion.png")


# ---------------------------------------------------------------------------
# FIGURA 5 — Robustez / remuestreo (panel limpio sin histos crudos)
# ---------------------------------------------------------------------------

def figura_5_robustez() -> None:
    """Panel de robustez legible: IC de remuestreo 80 % y anclas de sensibilidad.

    Sustituye histogramas de baja resolución por un forest de robustez
    (mismo mensaje científico, presentación editorial).
    """
    t3 = pd.read_csv(TAB / "tabla_3_robustez.csv")
    t2 = pd.read_csv(TAB / "tabla_2_efectos_primarios.csv")
    prim = t2[t2["outcome"] == "anemia_modsev"].iloc[0]
    rob = t3[t3["outcome"] == "anemia_modsev"].iloc[0]

    rows = [
        ("IPTW × diseño (IC boot 95 %)", float(prim["ipw_design_ate"]), float(prim["boot_ci_low"]), float(prim["boot_ci_high"]), "primario"),
        ("Remuestreo 80 % × 1 000 (IC)", float(prim["ipw_design_ate"]), float(rob["sub_ci_low"]), float(rob["sub_ci_high"]), "sub"),
        ("Ajuste departamental (S2)", -0.0181, np.nan, np.nan, "sens"),
        ("Consumo a 7 días (S4)", -0.0185, np.nan, np.nan, "sens"),
        ("Doble robustez", float(prim["aipw"]), np.nan, np.nan, "sens"),
        ("Emparejamiento ATT", float(prim["matching_att"]), np.nan, np.nan, "sens"),
    ]

    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    yy = np.arange(len(rows))[::-1]
    colors = {"primario": C["coral"], "sub": C["post"], "sens": C["teal"]}

    for i, (lab, est, lo, hi, kind) in enumerate(rows):
        y = yy[i]
        c = colors[kind]
        if np.isfinite(lo) and np.isfinite(hi):
            ax.errorbar(est, y, xerr=[[est - lo], [hi - est]], fmt="o", color=c, capsize=3.5, markersize=8, elinewidth=1.5)
        else:
            ax.plot(est, y, "D", color=c, markersize=7)
        ax.text(0.002, y, f"  {est:.3f}", va="center", fontsize=8, color=c)

    ax.axvline(0, color="#888888", ls="--", lw=1.0)
    ax.set_yticks(yy)
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Diferencia de riesgos — anemia moderada/severa")
    ax.set_title("Robustez del efecto primario bajo especificaciones alternativas", fontweight="bold", loc="left", fontsize=11)
    ax.set_xlim(-0.055, 0.02)

    legend_elems = [
        Line2D([0], [0], marker="o", color=C["coral"], lw=0, label="Estimador primario"),
        Line2D([0], [0], marker="o", color=C["post"], lw=0, label="Remuestreo de subconjuntos"),
        Line2D([0], [0], marker="D", color=C["teal"], lw=0, label="Sensibilidad / alternativa"),
    ]
    ax.legend(handles=legend_elems, loc="lower right", frameon=True, edgecolor="#dddddd", fancybox=False)
    fig.tight_layout()
    _save(fig, "figura_5_subsampling.png")


# ---------------------------------------------------------------------------
# FIGURA 6 — Radar de sensibilidad (rehecho limpio)
# ---------------------------------------------------------------------------

def figura_6_radar() -> None:
    # Scores del plan 5D (anclas del paper / S10)
    labels = [
        "S1\nFiltro dx\nprevio",
        "S2\nAjuste\ndepartamental",
        "S3\nDos confusores\nresiduales",
        "S4\nConsumo\n7 días",
        "S5\nMediación\ndiarrea",
    ]
    # 0–1 como en el paper: S1 frágil=0, S2=1, S3=0.67, S4=1, S5=0.60
    values = [0.0, 1.0, 0.67, 1.0, 0.60]
    N = len(labels)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    values_c = values + values[:1]
    angles_c = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(7.2, 7.0), subplot_kw=dict(polar=True))
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    ax.plot(angles_c, values_c, color=C["post"], lw=2.0)
    ax.fill(angles_c, values_c, color=C["post"], alpha=0.18)
    ax.scatter(angles, values, s=55, color=C["post"], zorder=5)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0,25", "0,50", "0,75", "1,00"], fontsize=7.5, color=C["muted"])
    ax.spines["polar"].set_color("#cccccc")
    ax.grid(color="#dddddd", lw=0.7)

    ax.set_title(
        "Robustez multidimensional del efecto primario\n(0 = frágil · 1 = robusto)",
        fontweight="bold",
        fontsize=11,
        pad=18,
    )

    # Anotaciones de veredicto
    verdicts = ["Frágil\n(filtro necesario)", "Robusto", "Robusto", "Robusto", "Parcial"]
    for ang, val, ver in zip(angles, values, verdicts):
        ax.text(ang, min(1.02, val + 0.12), ver, ha="center", va="center", fontsize=6.8, color=C["gray"])

    fig.tight_layout()
    _save(fig, "figura_6_sensitivity_radar.png")


# ---------------------------------------------------------------------------
# FIGURA 7 — Contorno E-value (rehecho limpio)
# ---------------------------------------------------------------------------

def figura_7_contour() -> None:
    """Contorno de sensibilidad a confusión residual (VanderWeele / Ding).

    E-value unitario = 1.69; bounding factor 2 confusores = 2.51.
    """
    e_unit = 1.69
    e_two = 2.51

    # malla RR confusor-exposición (δ) × confusor-desenlace (γ)
    d = np.linspace(1.0, 4.0, 220)
    g = np.linspace(1.0, 4.0, 220)
    D, G = np.meshgrid(d, g)
    # factor de sesgo B = (δ*γ)/(δ+γ-1) para confusor binario (aprox. Ding-VanderWeele)
    B = (D * G) / (D + G - 1.0)

    fig, ax = plt.subplots(figsize=(7.0, 6.0))
    levels = [1.2, 1.4, 1.69, 2.0, 2.51, 3.0, 3.5]
    cs = ax.contour(D, G, B, levels=levels, colors=C["post"], linewidths=1.1)
    ax.clabel(cs, inline=True, fontsize=8, fmt="B = %.2f")

    # Región que anula el efecto (B >= e_unit): sombreado
    ax.contourf(D, G, B, levels=[e_unit, 8], colors=[C["coral_fill"]], alpha=0.35)

    # Punto E-value en la diagonal δ=γ
    ax.plot(e_unit, e_unit, "o", color=C["coral"], markersize=10, zorder=5, label=f"E-value unitario = {e_unit:.2f}")
    ax.plot(e_two, e_two, "s", color=C["amber"], markersize=9, zorder=5, label=f"Factor 2 confusores = {e_two:.2f}")

    # Diagonal
    ax.plot([1, 4], [1, 4], color="#bbbbbb", ls=":", lw=1.0)

    ax.set_xlabel("Fuerza confusor – exposición  (RR)")
    ax.set_ylabel("Fuerza confusor – desenlace  (RR)")
    ax.set_title(
        "Sensibilidad a confusión residual no medida\n(anemia moderada/severa)",
        fontweight="bold",
        loc="left",
        fontsize=11,
    )
    ax.set_xlim(1, 4)
    ax.set_ylim(1, 4)
    ax.legend(loc="upper right", frameon=True, edgecolor="#dddddd", fancybox=False, fontsize=8.5)
    ax.text(
        0.02,
        0.02,
        "Zona sombreada: combinaciones capaces de anular el efecto puntual (B ≥ 1,69).",
        transform=ax.transAxes,
        fontsize=7.5,
        color=C["muted"],
        va="bottom",
    )
    fig.tight_layout()
    _save(fig, "figura_7_contour_evalue.png")


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    print("=" * 60)
    print("FIGURAS DE PUBLICACIÓN — calidad editorial")
    print("=" * 60)
    figura_3_dag()
    figura_1_love()
    figura_2_forest()
    figura_4_especificacion()
    figura_5_robustez()
    figura_6_radar()
    figura_7_contour()
    print("\nOK. Figuras en", FIG)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
