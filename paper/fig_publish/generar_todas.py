#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenera las tres figuras del cuerpo del paper en esta carpeta.

Uso (desde paper/fig_publish/):
    python generar_todas.py

No reestima modelos: lee paper/tablas/*.csv.
"""
from __future__ import annotations

import sys

import figura_1_love_plot
import figura_bosque_esencial
import figura_flujo_muestral


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print("Figuras del cuerpo (paper/fig_publish)")
    figura_flujo_muestral.generar()
    figura_1_love_plot.generar()
    figura_bosque_esencial.generar()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
