# endes2024-suplementos-hierro-anemia-peru

Repositorio autónomo de **análisis y replicación** del manuscrito:

> *Asociación entre consumo reportado de suplementos con hierro y anemia
> moderada o severa en niños receptores del programa: ENDES 2024, Perú*
> (manuscrito en `paper/paper_final_APA7.tex`, formato RPMESP/Vancouver).

Con una única fuente de datos (`data/anemia_valor.dta`, ENDES 2024) y una
semilla fija (`20260710`), este repositorio reproduce **todas** las tablas,
figuras, estimaciones e intervalos reportados en el manuscrito: tablas del
cuerpo, sensibilidades, estimadores alternativos (emparejamiento 1:1 y AIPW),
figuras de publicación y verificación TEX↔CSV.

> **Nota de interpretación.** El estudio es observacional y transversal. Reporta
> una **asociación** entre consumo reportado y anemia; **no** demuestra eficacia
> farmacológica del hierro ni relación causal (ver discusión del manuscrito).

---

## Resultado principal (replicable)

| Especificación | Diferencia (puntos porcentuales) | IC 95 % bootstrap |
|---|---|---|
| IPW × peso de diseño (referencia) | −2,8 | [−4,5; −1,2] |
| + ajuste departamental | −2,4 | [−4,1; −0,7] |
| Sin filtro de diagnóstico (casos completos, n = 8 800) | −0,9 | [−2,6; 0,9] |
| Consumo reportado en 12 meses | +2,4 | [−0,2; 4,7] |

Hemoglobina: +0,65 g/L (IC [−0,04; 1,24]) y +0,67 g/L (IC [0,00; 1,25]) según
criterio MINSA y OMS. E-value del punto ≈ 1,93; del límite del IC ≈ 1,46.
Muestra analítica: 6 703 niños (2 194 con consumo reportado en 7 días / 4 509
sin consumo), prevalencias ajustadas 9,3 % frente a 12,1 %.

## Estructura

```
endes2024-suplementos-hierro-anemia-peru/
├── data/
│   └── anemia_valor.dta        ← única fuente de datos (ENDES 2024, 14 428 × 127)
├── analysis/
│   ├── pipeline_informe_final.py    ← pipeline completo (todos los estimadores)
│   ├── sensibilidades_cuerpo.py     ← anclas del cuerpo (IPW×diseño, bootstrap 2000)
│   ├── pipeline_mejoras_repo.py     ← tablas de robustez adicionales
│   ├── autocheck_tex_csv.py         ← QA TEX ↔ CSV (esperado 23/23)
│   ├── figuras_publicacion.py       ← figuras suplementarias/DAG
│   ├── figuras_rpmesp_asociacion.py ← figuras del cuerpo (legado)
│   └── codebook_analisis.md         ← diccionario de variables y roles
├── paper/
│   ├── paper_final_APA7.tex         ← manuscrito (RPMESP)
│   ├── referencias.bib              ← bibliografía Vancouver (17 entradas)
│   ├── compile.sh                   ← compilación LaTeX (pdflatex + biber)
│   ├── STROBE_checklist_ENDES_2024.md
│   ├── figuras/                     ← PNG que lee el manuscrito
│   ├── fig_publish/                 ← generadores de las figuras del cuerpo
│   └── tablas/                      ← resultados CSV/JSON (anclas del manuscrito)
├── requirements.txt                 ← dependencias mínimas
├── requirements-lock.txt            ← entorno congelado (Python 3.11, conda)
├── run_all.sh                       ← orquesta la replicación completa
└── LICENSE                          ← CC BY 4.0
```

## Requisitos

- **Python ≥ 3.11** con las dependencias de `requirements.txt` (pandas, numpy,
  scipy, statsmodels, scikit-learn, matplotlib, pyreadstat).
  Reproducción byte-idéntica recomendada con el entorno congelado:
  `conda create -n causal_env python=3.11` + `pip install -r requirements-lock.txt`.
- **LaTeX** (TeX Live/MiKTeX) con `apa7`, `biblatex` y `biber` — solo necesario
  para compilar el manuscrito.

## Reproducir todos los resultados

```bash
bash run_all.sh            # análisis completo (el pipeline puede tardar)
bash run_all.sh --pdf      # análisis + compilación del manuscrito
bash run_all.sh --fast     # solo anclas del cuerpo + verificación
```

El script regenera los CSV/JSON de `paper/tablas/` y los PNG de
`paper/fig_publish/` (y sincroniza las tres figuras del cuerpo en
`paper/figuras/`). Para comprobar que los artefactos regenerados coinciden con
los versionados, ejecute `git diff -- paper/tablas paper/figuras` (debería estar
vacío si el entorno y la semilla coinciden).

Verificación final esperada:

```text
Autocheck: 23/23 pass | critical_fail=0
```

### Reproducir un solo bloque

```bash
python analysis/sensibilidades_cuerpo.py   # anclas del cuerpo
python analysis/pipeline_informe_final.py  # pipeline completo (lento)
python analysis/autocheck_tex_csv.py       # QA TEX ↔ CSV
python paper/fig_publish/generar_todas.py  # figuras del cuerpo
(cd paper && bash compile.sh)              # PDF del manuscrito
```

## Datos

`data/anemia_valor.dta` es el microdato **ENDES 2024** (INEI), procesado y
enriquecido con variables derivadas (T1–T5, hemoglobina ajustada, pesos
normalizados), sin identificadores personales. Los microdatos originales son
públicos y se obtienen del portal del INEI:
<https://proyectos.inei.gob.pe/endes/>. La metodología corresponde al programa
DHS/ICF (<https://www.dhsprogram.com/methodology/>). El diseño muestral usa
conglomerados `hv001`, estratos `hv022` y pesos `hv005/10⁶`.

## Reproducibilidad y determinismo

- Semilla global: `20260710`.
- Bootstrap estratificado por conglomerados (`hv001` dentro de `hv022`),
  2 000 réplicas para las anclas del cuerpo.
- Versiones congeladas en `requirements-lock.txt`.
- Corrección de multiplicidad: Holm–Bonferroni sobre la familia de desenlaces
  secundarios.

## Citar

Manuscrito: `paper/paper_final_APA7.tex` (autores según la portada). Si usa este
repositorio o sus resultados, cite el manuscrito y, cuando exista, el DOI del
repositorio.

## Licencia

Contenido del repositorio bajo [CC BY 4.0](LICENSE). Los microdatos ENDES son
del INEI y se distribuyen bajo sus propios términos de acceso público; ver
<https://proyectos.inei.gob.pe/endes/>.
