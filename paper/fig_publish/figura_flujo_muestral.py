#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figura 1 del cuerpo — flujo de selección de la muestra analítica (MEJORADO).

Cambios respecto a la versión original:
1. Rama lateral con análisis sin restricción por diagnóstico previo (n=8.800).
2. Cajas finales renombradas para distinguir elegibilidad (recepción) de exposición (consumo).
3. Nota al pie integrada con reponderación por inclusión y análisis alternativo.
4. Layout desplazado a la izquierda para acomodar la rama lateral sin apretar.

Fuente: analysis/figuras_rpmesp_asociacion.py → figura_flujo()
PNG:    figura_flujo_muestral.png
Anclas: paper/tablas/tabla_0_flujo_muestral.csv
"""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import pandas as pd

from _estilo import C, TAB, apply_style, save


def generar() -> None:
    apply_style()
    flujo = pd.read_csv(TAB / "tabla_0_flujo_muestral.csv")

    def n_paso(paso: str) -> int:
        return int(flujo.loc[flujo["paso"].astype(str) == paso, "n"].iloc[0])

    def n_excl(paso: str) -> int:
        return int(flujo.loc[flujo["paso"].astype(str) == paso, "n_excluido"].iloc[0])

    # --- Anclas numéricas ---
    n_endes = n_paso("1")
    n_receptores = n_paso("2")
    n_sin_dx = n_paso("3")
    n_cc = n_paso("4")
    n_consumo = int(
        flujo.loc[flujo["descripcion"].str.contains("Tratados", na=False), "n"].iloc[0]
    )
    n_control = int(
        flujo.loc[flujo["descripcion"].str.contains("Control", na=False), "n"].iloc[0]
    )

    # Análisis sin restricción por diagnóstico previo (sensibilidad esencial).
    # Si el CSV tiene una fila con paso="alt", la usa; si no, usa el valor del paper.
    try:
        n_alt = int(flujo.loc[flujo["paso"].astype(str) == "alt", "n"].iloc[0])
    except IndexError:
        n_alt = 8800  # reportado en Resultados: todos los receptores, sin filtro dx

    # --- Canvas ---
    fig, ax = plt.subplots(figsize=(9.0, 9.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    # Centro del flujo principal (ligeramente a la izquierda para dejar espacio a la rama)
    x_main = 3.7
    w_main = 5.2

    # Color ámbar para la rama alternativa
    col_alt_edge = "#B8860B"
    col_alt_fill = "#FFF8DC"

    def box(x, y, w, h, title, body, fc, ec, title_fontsize=9.8, body_fontsize=8.0):
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
        ax.text(
            x,
            y + 0.16,
            title,
            ha="center",
            va="center",
            fontsize=title_fontsize,
            fontweight="bold",
            color=ec,
            zorder=4,
        )
        ax.text(
            x,
            y - 0.20,
            body,
            ha="center",
            va="center",
            fontsize=body_fontsize,
            color=C["line"],
            zorder=4,
            linespacing=1.25,
        )

    def arrow(x0, y0, x1, y1, style="-|>", lw=1.3, color=None, dashed=False):
        color = color or C["line"]
        linestyle = "dashed" if dashed else "solid"
        ax.add_patch(
            FancyArrowPatch(
                (x0, y0),
                (x1, y1),
                arrowstyle=style,
                mutation_scale=12,
                linewidth=lw,
                color=color,
                linestyle=linestyle,
                zorder=2,
            )
        )

    # --- Flujo principal ---

    box(
        x_main,
        11.0,
        w_main,
        1.05,
        "ENDES 2024",
        f"Niños de 6 a 59 meses con hemoglobina capilar\nN = {n_endes:,}".replace(",", " "),
        C["blue_fill"],
        C["blue"],
    )
    arrow(x_main, 10.47, x_main, 9.75)

    box(
        x_main,
        9.2,
        w_main,
        1.05,
        "Receptores de suplementos",
        f"Elegibilidad: ≥1 presentación recibida en 12 meses\n"
        f"n = {n_receptores:,}   ·   excluidos: {n_excl('2'):,} no receptores".replace(",", " "),
        C["teal_fill"],
        C["teal"],
    )
    arrow(x_main, 8.67, x_main, 7.95)

    box(
        x_main,
        7.4,
        w_main,
        1.05,
        "Sin diagnóstico previo reportado",
        f"Población de análisis principal\n"
        f"n = {n_sin_dx:,}   ·   excluidos: {n_excl('3'):,} con diagnóstico previo".replace(",", " "),
        C["teal_fill"],
        C["teal"],
    )
    arrow(x_main, 6.87, x_main, 6.15)

    box(
        x_main,
        5.6,
        w_main,
        1.05,
        "Casos completos en covariables",
        f"Muestra analítica\n"
        f"n = {n_cc:,}   ·   excluidos: {n_excl('4'):,} (sobre todo anemia materna)".replace(",", " "),
        C["blue_fill"],
        C["blue"],
    )
    # --- Rama lateral: análisis sin restricción ---
    x_alt = 8.35
    w_alt = 2.9
    box(
        x_alt,
        7.4,
        w_alt,
        1.55,
        "Análisis sin restricción",
        "Todos los receptores,\nsin filtro de diagnóstico previo\n"
        f"n = {n_alt:,}   ·   sensibilidad esencial".replace(",", " "),
        col_alt_fill,
        col_alt_edge,
        title_fontsize=9.3,
        body_fontsize=7.6,
    )
    # Flecha punteada desde borde derecho de "Sin dx" a borde izquierdo de "Alt"
    arrow(
        x_main + w_main / 2,
        7.4,
        x_alt - w_alt / 2,
        7.4,
        dashed=True,
        color=col_alt_edge,
    )

    # --- Bifurcación final ---
    x_left = 1.9
    x_right = 5.7
    w_final = 3.5
    y_split = 3.8
    y_top_final = 3.475  # borde superior de cajas finales (2.85 + 1.25/2)

    # Una sola flecha vertical desde "Casos completos" hasta el punto de split
    arrow(x_main, 5.07, x_main, y_split)

    box(
        x_left,
        2.85,
        w_final,
        1.25,
        "Consumo reportado",
        f"≥1 toma en 7 días previos\nn = {n_consumo:,}".replace(",", " "),
        C["green_fill"],
        C["green"],
    )
    arrow(x_main, y_split, x_left, y_top_final)

    box(
        x_right,
        2.85,
        w_final,
        1.25,
        "Sin consumo reportado en 7 días",
        f"Recepción sí, pero sin toma reportada\nn = {n_control:,}".replace(",", " "),
        C["gray_fill"],
        C["gray"],
    )
    arrow(x_main, y_split, x_right, y_top_final)

    ax.set_ylim(1.9, 12.0)
    fig.tight_layout()
    save(fig, "figura_flujo_muestral.png")


if __name__ == "__main__":
    generar()
