# Figuras publicadas en el cuerpo

Solo estas tres figuras aparecen en `paper_final_APA7.tex` (`\includegraphics`). El resto de `paper/figuras/` es material de análisis o suplemento no incluido en el manuscrito.

| Orden | Archivo PNG | `\label` | Generador Python | Anclas CSV |
|------:|-------------|---------|------------------|------------|
| 1 | `figura_flujo_muestral.png` | `fig:flujo` | `figura_flujo_muestral.py` | `tabla_0_flujo_muestral.csv` |
| 2 | `figura_1_love_plot.png` | `fig:love` | `figura_1_love_plot.py` | `tabla_S2_balance_smd.csv` |
| 3 | `figura_bosque_esencial.png` | `fig:bosque` | `figura_bosque_esencial.py` | `tabla_sensibilidades_cuerpo.csv`, `tabla_2_efectos_primarios.csv` |

Los `.tex` de esta carpeta son los entornos `figure` extraídos del paper. El manuscrito sigue leyendo los PNG desde `paper/figuras/` (`\graphicspath{{figuras/}{paper/figuras/}}`: `figuras/` al compilar desde `paper/`, `paper/figuras/` al compilar desde la raíz del repo).

## Regenerar

Desde esta carpeta, con el entorno Python del repositorio:

```bash
python generar_todas.py
```

O una figura suelta:

```bash
python figura_flujo_muestral.py
python figura_1_love_plot.py
python figura_bosque_esencial.py
```

No reestima modelos: lee `paper/tablas/*.csv`.

## Proveniencia del código

| Figura | Script original |
|--------|-----------------|
| Flujo y bosque | `analysis/figuras_rpmesp_asociacion.py` |
| Love plot | `analysis/figuras_publicacion.py` (`figura_1_love`) |

`pipeline_informe_final.py` también escribe un love plot más crudo sobre `paper/figuras/`; la versión de publicación es la de `figuras_publicacion.py`.
