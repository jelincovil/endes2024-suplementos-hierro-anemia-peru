#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figura 2 del cuerpo — love plot de balance pre/post IPW. MEJORADO.

Cambios respecto a la versión original:
1. Banda verde semitransparente en 0–0.10: "zona de balance aceptable".
2. Anotación del máximo |DME| post-IPW (0.039) para que el lector vea de un vistazo
   que todas las covariables quedaron dentro del umbral.
3. Líneas conectoras con grosor proporcional al cambio: cuanto más se movió una
   covariable hacia la izquierda (mejoró), más gruesa la línea.
4. Anotación explicativa del umbral 0.10 integrada en el gráfico.
5. Eje X comienza en 0 (|DME| no puede ser negativo).
6. Título y nota al pie que narran el hallazgo: el desbalance inicial extremo
   (confusión por indicación) se resolvió tras la ponderación.

Fuente: analysis/figuras_publicacion.py → figura_1_love()
PNG:    figura_1_love_plot.png
Anclas: paper/tablas/tabla_S2_balance_smd.csv
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _estilo import C, TAB, apply_style, es_axis_formatter, fmt_es, save

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


def generar() -> None:
    apply_style()
    bal = pd.read_csv(TAB / "tabla_S2_balance_smd.csv").copy()
    bal["abs_pre"] = bal["smd_pre"].abs()
    bal["abs_post"] = bal["smd_post"].abs()
    bal["label"] = bal["covariable"].map(_pretty_cov)

    # Colapsar categorías dummy al máximo por familia
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
    plot_df["delta"] = plot_df["abs_pre"] - plot_df["abs_post"]  # cuánto mejoró
    n = len(plot_df)
    fig_h = max(4.8, 0.40 * n + 1.8)
    fig, ax = plt.subplots(figsize=(7.6, fig_h))

    yy = np.arange(n)

    # El eje se recorta a un rango legible: casi todas las covariables (pre y post)
    # caen bajo 0.12. Edad y edad³ tienen |DME| pre-IPW extremo (~0.62-0.72) y se
    # marcan con una flecha de truncamiento en vez de estirar todo el eje para
    # incluirlas (eso aplastaría el mensaje real: el balance post-IPW).
    xlim_max = 0.15
    off_scale = plot_df["abs_pre"] > xlim_max

    # --- Zonas de referencia ---
    # Banda verde: zona de balance aceptable (0 – 0.10)
    ax.axvspan(0.0, 0.10, color="#4A8F5A", alpha=0.06, zorder=0)
    # Línea del umbral
    ax.axvline(0.10, color="#999999", ls="--", lw=1.0, zorder=1)
    # Anotación del umbral (fila baja, lejos de la anotación del máximo post-IPW)
    ax.text(
        0.102,
        1.4,
        "Umbral de\nbalance\n|DME| = 0,10",
        va="center",
        ha="left",
        fontsize=7.8,
        color="#666666",
        linespacing=1.2,
    )

    # --- Puntos pre (solo los que caen dentro del rango visible) ---
    in_range = plot_df.loc[~off_scale]
    ax.scatter(
        in_range["abs_pre"],
        yy[~off_scale.values],
        s=55,
        marker="o",
        facecolors="white",
        edgecolors=C["pre"],
        linewidths=1.7,
        zorder=4,
        label="Sin ponderar",
    )
    ax.scatter(
        plot_df["abs_post"],
        yy,
        s=50,
        marker="s",
        color=C["post"],
        zorder=5,
        label="Tras IPW",
    )

    # --- Líneas conectoras con grosor proporcional a la mejora ---
    for i, (_, row) in enumerate(plot_df.iterrows()):
        improvement = row["delta"]
        # Grosor entre 0.8 y 2.2 según cuánto mejoró
        lw = 0.8 + min(improvement * 4.0, 1.4)
        # Color: azul si mejoró, gris neutro si empeoró (raro)
        color = C["post"] if improvement > 0 else "#bbbbbb"
        alpha = 0.5 if improvement > 0 else 0.3
        if off_scale.iloc[i]:
            # Fuera de rango: línea truncada + flecha + valor real anotado
            edge = xlim_max * 0.99
            ax.plot([row["abs_post"], edge], [i, i], color=color, lw=lw, alpha=alpha, zorder=2)
            ax.annotate(
                "",
                xy=(edge, i),
                xytext=(edge - 0.018, i),
                arrowprops=dict(arrowstyle="-|>", color=C["pre"], lw=1.3),
                zorder=3,
            )
            ax.text(
                edge - 0.004,
                i + 0.28,
                f"Sin ponderar = {fmt_es(row['abs_pre'], 2)}",
                va="bottom",
                ha="right",
                fontsize=7.3,
                color=C["pre"],
                fontstyle="italic",
            )
        else:
            ax.plot(
                [row["abs_pre"], row["abs_post"]],
                [i, i],
                color=color,
                lw=lw,
                alpha=alpha,
                zorder=2,
            )

    # --- Anotación del máximo post-IPW ---
    max_post = float(plot_df["abs_post"].max())
    max_idx = int(plot_df["abs_post"].idxmax())
    y_max = yy[plot_df.index.get_loc(max_idx)]
    ax.annotate(
        f"Máx. post-IPW = {fmt_es(max_post, 3)}",
        xy=(max_post, y_max),
        xytext=(max_post + 0.045, y_max - 1.1),
        fontsize=8.5,
        color=C["post"],
        fontweight="bold",
        arrowprops=dict(
            arrowstyle="->",
            color=C["post"],
            lw=1.1,
        ),
        zorder=6,
    )

    # --- Ejes y estética ---
    ax.set_yticks(yy)
    ax.set_yticklabels(plot_df["label"], fontsize=9)
    ax.set_xlabel(
        "Diferencia de medias estandarizada absoluta  |DME|",
        fontsize=9.5,
    )
    ax.set_xlim(0.0, xlim_max)
    ax.set_ylim(-0.6, n - 0.4)
    ax.xaxis.set_major_formatter(es_axis_formatter(2))

    # Grid vertical sutil
    ax.xaxis.grid(True, color="#eeeeee", linestyle="-", linewidth=0.5, zorder=0)

    # Leyenda
    ax.legend(
        loc="lower right",
        frameon=True,
        edgecolor="#dddddd",
        fancybox=False,
        fontsize=8.5,
    )

    fig.tight_layout()
    save(fig, "figura_1_love_plot.png")


if __name__ == "__main__":
    generar()
