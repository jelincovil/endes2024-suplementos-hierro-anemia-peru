#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Estilo compartido de las tres figuras publicadas en el cuerpo del paper."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

HERE = Path(__file__).resolve().parent
TAB = HERE.parent / "tablas"
OUT = HERE

C = {
    "blue": "#1f4e79",
    "blue_fill": "#d6e6f5",
    "teal": "#0d6e6e",
    "teal_fill": "#d4efef",
    "green": "#1b7a4e",
    "green_fill": "#e8f5e9",
    "coral": "#a33b3b",
    "coral_fill": "#f5d9d9",
    "gray": "#5a5a5a",
    "gray_fill": "#f0f0f0",
    "line": "#333333",
    "pre": "#c44e52",
    "post": "#2b6cb0",
}


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "font.family": "sans-serif",
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


def fmt_es(x: float, decimales: int = 2, signo: bool = False) -> str:
    """Formatea un número con coma decimal (convención RPMESP), p. ej. -0.028 -> '-0,028'."""
    texto = f"{x:+.{decimales}f}" if signo else f"{x:.{decimales}f}"
    return texto.replace(".", ",")


def es_axis_formatter(decimales: int = 2) -> FuncFormatter:
    """FuncFormatter para ejes: mismos ticks de matplotlib, pero con coma decimal."""
    return FuncFormatter(lambda x, _pos: fmt_es(x, decimales))


def save(fig: plt.Figure, name: str) -> Path:
    path = OUT / name
    fig.savefig(path, dpi=300, bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    print(f"  → {path.name} ({path.stat().st_size // 1024} KB)")
    return path
