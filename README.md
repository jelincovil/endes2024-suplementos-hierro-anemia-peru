# endes2024-suplementos-hierro-anemia-peru

Análisis y material de reproducción del estudio *Asociación entre consumo reportado
de suplementos con hierro y anemia moderada o severa en niños que recibieron
suplementos: ENDES 2024, Perú*.

**Enlace al manuscrito**: [`paper/paper_final_APA7.tex`](paper/paper_final_APA7.tex)
(PDF compilado en [`paper/paper_final_APA7.pdf`](paper/paper_final_APA7.pdf)).

## Descripción del proyecto

El manuscrito evalúa, con microdatos de la ENDES 2024 del INEI, si el consumo
reportado de suplementos con hierro durante los siete días previos a la
entrevista se asocia con menor prevalencia de **anemia moderada o severa** en
niños de 6 a 59 meses que habían recibido suplementos y no tenían un
diagnóstico previo de anemia reportado por la madre.

**Tipo de estudio**: observacional y transversal. Los resultados describen
una **asociación** y no deben interpretarse como eficacia del hierro ni como
relación causal. No obstante, el análisis incluye un extenso programa de
sensibilidad causal (IPW/AIPW, matching, Lee bounds, E-values, DoWhy,
misclassification, MICE, transporte, overlap weights, etc.).

### Resultado principal

| Especificación | RD (puntos porcentuales) | IC 95 % (bootstrap estratificado) |
| --- | ---: | --- |
| IPW × peso de diseño (principal) | −2,8 | [−4,5; −1,2] |
| Con ajuste por departamento | −2,4 | [−4,1; −0,7] |
| Sin filtro de diagnóstico (n = 8 800) | −0,9 | [−2,6; 0,9] |
| Consumo reportado en 12 meses | +2,4 | [−0,2; 4,7] |

Muestra analítica: **6 703 niños** (2 194 con consumo reportado en 7 días y
4 509 sin consumo). Prevalencias ajustadas de anemia moderada o severa:
9,3 % frente a 12,1 %. NNT = 36.

### Flujo muestral

```
14 428   (ENDES 2024, niños 6–59 meses)
  9 079   recibieron ≥1 suplemento en 12 meses (received_any = 1)
  6 908   sin diagnóstico previo de anemia (dx_anemia = 0)
  6 703   casos completos (muestra confirmatoria)
           ├── 2 194 expuestos (algún toma7d_* = 1)
           └── 4 509 no expuestos (todos toma7d_* = 0)
```

## Estructura del repositorio

| Carpeta / archivo | Qué hay |
| --- | --- |
| `data/anemia_valor.dta` | Microdatos ENDES 2024 (INEI) procesados, sin identificadores. Única fuente de datos de todo el pipeline. |
| `analysis/sensibilidades_cuerpo.py` | Especificaciones del cuerpo del artículo e inferencia bootstrap (B=2000). |
| `analysis/pipeline_informe_final.py` | Pipeline completo: IPW/AIPW, matching, positividad, MICE, dosis-respuesta, misclassification, E-values, MDE, impacto poblacional, heterogeneidad, figuras DAG, etc. |
| `analysis/pipeline_mejoras_repo.py` | Tablas de mejoras: Lee bounds, mediación (diarrea), pesos de transporte (IOSW), SE sandwich cluster, comparativa de literatura. |
| `analysis/autocheck_tex_csv.py` | Verificación automática TEX ↔ CSV (debe reportar 23/23). |
| `analysis/figuras_rpmesp_asociacion.py`, `analysis/figuras_publicacion.py` | Figuras del cuerpo y de publicación. |
| `analysis/codebook_analisis.md` | Codebook completo de variables (T / Y / X / selección / diseño) y convenciones. |
| `paper/paper_final_APA7.tex`, `paper/referencias.bib` | Manuscrito (formato RPMESP/Vancouver) y bibliografía. |
| `paper/tablas/` | Tablas de resultados en CSV/JSON (más de 40 tablas) y registros de verificación (`autocheck_tex_csv.json`). |
| `paper/figuras/`, `paper/fig_publish/` | Figuras generadas (Love plot, bosque, DAGs, dosis-respuesta, E-value, radar, etc.) y scripts de publicación de figuras. |
| `paper/STROBE_checklist_ENDES_2024.md` | Checklist STROBE. |
| `run_all.sh` | Orquestador del pipeline completo. |
| `requirements.txt`, `requirements-lock.txt` | Dependencias (libres y congeladas, respectivamente). |

## Requisitos para ejecutar el pipeline

- **Python 3.11** (entorno original: conda `causal_env`; el lock fue generado con
  `/opt/homebrew/Caskroom/miniforge/base/envs/causal_env/bin/python`).
- Dependencias (`requirements.txt`):
  - `pandas >= 1.5` · `numpy >= 1.24` · `scipy >= 1.10`
  - `statsmodels >= 0.14` · `scikit-learn >= 1.2` · `matplotlib >= 3.7`
  - `pyreadstat >= 1.2` (lectura del `.dta`)
- TeX (latexmk + biber + pdflatex) **solo** para compilar el manuscrito (`--pdf`).

### Instalación

```bash
python -m venv .venv && source .venv/bin/activate   # o conda create -n causal_env python=3.11
pip install -r requirements.txt                     # versión exacta: pip install -r requirements-lock.txt
```

### Ejecución

Desde la raíz del repositorio:

```bash
bash run_all.sh            # análisis completo (bootstrap B=2000; puede tardar)
bash run_all.sh --pdf      # análisis + compilación del manuscrito
bash run_all.sh --fast     # solo anclas del cuerpo + verificación TEX↔CSV
```

Para compilar únicamente el manuscrito:

```bash
cd paper && bash compile.sh
```

El flujo usa latexmk con biber (pdflatex → biber → pdflatex → pdflatex). Los
editores basados en latexmk (Overleaf, VS Code LaTeX Workshop, TeXstudio,
TeXShop) leen el `.latexmkrc` incluido y compilan con referencias de forma
directa.

### Verificación de reproducibilidad

- **Determinismo**: semilla fija `20260710` en todas las operaciones aleatorias,
  y versiones congeladas en `requirements-lock.txt`.
- Tras una ejecución completa, `python analysis/autocheck_tex_csv.py` debe
  reportar **23/23 verificaciones correctas**, lo que confirma que las cifras
  del manuscrito coinciden con las tablas generadas.
- La inferencia del cuerpo usa bootstrap estratificado con 2 000 réplicas
  (clusters `hv001` dentro de estratos `hv022`); la tabla fuente es
  `paper/tablas/tabla_sensibilidades_cuerpo.csv`.

## Datos y licencia

- **Fuente**: ENDES 2024 (Encuesta Demográfica y de Salud Familiar), INEI Perú.
  Los microdatos son **públicos** y se descargan de
  https://proyectos.inei.gob.pe/endes/. La encuesta sigue la metodología del
  programa DHS (https://www.dhsprogram.com/methodology/).
- El archivo incluido en `data/` contiene las variables derivadas usadas en el
  análisis (N = 14 428 filas, 127 columnas, sin identificadores personales).
- **Código, manuscrito y artefactos**: CC BY 4.0 (ver `LICENSE`). Si utiliza
  este repositorio o sus resultados, cite el manuscrito de `paper/`. El DOI del
  repositorio se indicará cuando esté disponible.
- Los microdatos ENDES son de uso libre para fines estadísticos y de
  investigación; cualquier reutilización debe respetar los términos de
  disponibilidad del INEI y las guías DHS (cita de la encuesta original).
