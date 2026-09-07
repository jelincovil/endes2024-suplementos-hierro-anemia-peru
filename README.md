# endes2024-suplementos-hierro-anemia-peru

Repositorio de investigación reproducible que acompaña el manuscrito:

> *Asociación entre consumo reportado de suplementos con hierro y anemia
> moderada o severa en niños que recibieron suplementos: ENDES 2024, Perú*
> (sometido a evaluación por pares; el manuscrito no se incluye aquí).

Este repositorio contiene **todo el material de reproducción**: el código del
pipeline, la base de datos y las tablas y figuras publicables, de modo que
editores y lectores puedan regenerar y auditar los resultados del artículo sin
manipular el texto del manuscrito.

## Descripción del estudio

El manuscrito evalúa, con microdatos de la ENDES 2024 del INEI, si el consumo
reportado de suplementos con hierro durante los siete días previos a la
entrevista se asocia con menor prevalencia de **anemia moderada o severa** en
niños de 6 a 59 meses que habían recibido suplementos y no tenían un
diagnóstico previo de anemia reportado por la madre.

**Tipo de estudio**: observacional y transversal. Los resultados describen
una **asociación** y no deben interpretarse como eficacia del hierro ni como
relación causal. El análisis incluye un extenso programa de sensibilidad
(IPW/AIPW, matching, Lee bounds, E-values, mala clasificación, MICE,
pesos de transporte y de overlap, entre otros).

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

## Qué hay en cada carpeta

| Carpeta / archivo | Qué hay |
| --- | --- |
| `data/anemia_valor.dta` | Microdatos ENDES 2024 (INEI) procesados, sin identificadores. Única fuente de datos del pipeline (N = 14 428, 127 columnas). |
| `analysis/sensibilidades_cuerpo.py` | Especificaciones del cuerpo del artículo e inferencia bootstrap (B=2000). |
| `analysis/pipeline_informe_final.py` | Pipeline completo: IPW/AIPW, matching, positividad, MICE, dosis-respuesta, mala clasificación, E-values, MDE, impacto poblacional, heterogeneidad, DAGs, etc. |
| `analysis/pipeline_mejoras_repo.py` | Tablas de mejoras: Lee bounds, mediación (diarrea), pesos de transporte (IOSW), SE sandwich cluster, comparativa de literatura. |
| `analysis/autocheck_positivo.py` | Verificación automática de artefactos (tablas/figuras/anclas; espera 100 % pass). |
| `analysis/codebook_analisis.md` | Codebook completo de variables (T / Y / X / selección / diseño) y convenciones. |
| `analysis/figuras_rpmesp_asociacion.py`, `analysis/figuras_publicacion.py` | Figuras del cuerpo y de publicación. |
| `paper/tablas/` | Tablas de resultados en CSV/JSON (más de 40 tablas) y registro de verificación (`autocheck_pipeline.json`). |
| `paper/figuras/`, `paper/fig_publish/` | Figuras generadas (flujo muestral, Love plot, bosque, DAGs, dosis-respuesta, E-value, radar, etc.) y sus scripts de publicación. |
| `paper/STROBE_checklist_ENDES_2024.md` | Checklist STROBE del estudio. |
| `run_all.sh` | Orquestador del pipeline completo. |
| `requirements.txt`, `requirements-lock.txt` | Dependencias (libres y congeladas, respectivamente). |

## Requisitos para ejecutar el pipeline

- **Python 3.11** junto con las dependencias de `requirements.txt`:
  - `pandas >= 1.5` · `numpy >= 1.24` · `scipy >= 1.10`
  - `statsmodels >= 0.14` · `scikit-learn >= 1.2` · `matplotlib >= 3.7`
  - `pyreadstat >= 1.2` (lectura del `.dta`)
- Los números exactos con los que se estimó el artículo están congelados en
  `requirements-lock.txt`. Si quiere reproducibilidad bit a bit, instale con el
  lock; si solo quiere re-ejecutar con versiones más nuevas, use
  `requirements.txt` y compare contra las tablas de referencia.

### Instalación

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt     # versión exacta: pip install -r requirements-lock.txt
```

### Ejecución

Desde la raíz del repositorio:

```bash
bash run_all.sh            # análisis completo (bootstrap B=2000; puede tardar)
bash run_all.sh --fast     # solo anclas del cuerpo + verificación
```

### Verificación de reproducción

- **Determinismo**: semilla fija `20260710` en todas las operaciones aleatorias
  y versiones congeladas en `requirements-lock.txt`.
- Tras una ejecución (completa o `--fast`),
  `python analysis/autocheck_positivo.py` debe reportar **0 fallos**,
  confirmando que las tablas y figuras del repo y sus anclas
  (RD = −0,0279; IC 95 % [−0,0434; −0,0113]; n = 6 703; 2 194 expuestos) son
  consistentes entre sí.
- La inferencia del cuerpo usa bootstrap estratificado con 2 000 réplicas
  (clusters `hv001` dentro de estratos `hv022`); la tabla fuente es
  `paper/tablas/tabla_sensibilidades_cuerpo.csv`.

## Datos y licencia

- **Fuente**: ENDES 2024 (Encuesta Demográfica y de Salud Familiar), INEI Perú.
  Los microdatos son **públicos** y se descargan de
  https://proyectos.inei.gob.pe/endes/. La encuesta sigue la metodología del
  programa DHS (https://www.dhsprogram.com/methodology/).
- El archivo incluido en `data/` contiene las variables derivadas usadas en el
  análisis, **sin identificadores personales** (N = 14 428 filas, 127 columnas).
- **Código, tablas y figuras**: CC BY 4.0 (ver `LICENSE`). Si utiliza este
  repositorio o sus resultados, cite el manuscrito sometido.
- Los microdatos ENDES son de uso libre para fines estadísticos y de
  investigación; cualquier reutilización debe respetar los términos de
  disponibilidad del INEI y las guías DHS (cita de la encuesta original).
- El manuscrito completo se somete a la revista correspondiente; los números
  citados en el texto provienen exactamente de las tablas y figuras de este
  repositorio (verificables con el autocheck).
