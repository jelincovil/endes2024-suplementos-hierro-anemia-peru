# endes2024-suplementos-hierro-anemia-peru

Análisis y material de reproducción del estudio *Asociación entre consumo reportado
de suplementos con hierro y anemia moderada o severa en niños que recibieron
suplementos: ENDES 2024, Perú*.

El manuscrito (en `paper/`) evalúa, con datos de la ENDES 2024, si el consumo
reportado de suplementos con hierro durante los siete días previos se asocia con
menor prevalencia de anemia moderada o severa en niños de 6 a 59 meses que habían
recibido suplementos y no tenían un diagnóstico previo de anemia reportado por la
madre. Se trata de un estudio observacional y transversal: los resultados describen
una asociación y no deben interpretarse como eficacia del hierro ni como relación
causal.

Con una única fuente de datos (`data/anemia_valor.dta`) y una semilla fija, este
repositorio reproduce todas las tablas, figuras y estimaciones del manuscrito.

## Contenido

| Carpeta | Qué hay |
| --- | --- |
| `data/` | Microdatos ENDES 2024 (INEI) procesados, sin identificadores. |
| `analysis/` | Scripts de análisis: estimación principal, sensibilidades, figuras y verificación TEX↔CSV. |
| `paper/` | Manuscrito (`paper_final_APA7.tex`, `referencias.bib`), figuras, tablas de resultados y checklist STROBE. |

El entorno de trabajo es Python 3.11 con las dependencias de `requirements.txt`; las
versiones exactas usadas están congeladas en `requirements-lock.txt`.

## Resultado principal

| Especificación | Diferencia (puntos porcentuales) | IC 95 % (bootstrap) |
| --- | ---: | --- |
| IPW × peso de diseño | −2,8 | [−4,5; −1,2] |
| Con ajuste por departamento | −2,4 | [−4,1; −0,7] |
| Sin filtro de diagnóstico (n = 8 800) | −0,9 | [−2,6; 0,9] |
| Consumo reportado en 12 meses | +2,4 | [−0,2; 4,7] |

Muestra analítica: 6 703 niños (2 194 con consumo reportado en 7 días y 4 509 sin
consumo). Prevalencias ajustadas de anemia moderada o severa: 9,3 % frente a 12,1 %.

## Reproducir los resultados

Desde la raíz del repositorio, con el entorno de Python instalado:

```bash
bash run_all.sh            # análisis completo
bash run_all.sh --pdf      # análisis y compilación del manuscrito
bash run_all.sh --fast     # solo estimaciones principales y verificación
```

Para compilar únicamente el manuscrito:

```bash
cd paper && bash compile.sh
```

El flujo usa latexmk con biber (pdflatex → biber → pdflatex → pdflatex). Los editores
basados en latexmk (Overleaf, VS Code LaTeX Workshop, TeXstudio, TeXShop) leen el
`.latexmkrc` incluido y compilan con referencias de forma directa.

Tras una ejecución completa, `python analysis/autocheck_tex_csv.py` debe reportar
23/23 verificaciones correctas, lo que confirma que las cifras del manuscrito
coinciden con las tablas generadas.

## Manuscrito

`paper/paper_final_APA7.tex` está redactado según el formato RPMESP (Vancouver) e
incluye resumen en español e inglés, material suplementario y checklist STROBE
(`paper/STROBE_checklist_ENDES_2024.md`).

## Datos

Los microdatos ENDES 2024 son públicos y se descargan del portal del INEI
(https://proyectos.inei.gob.pe/endes/). La encuesta sigue la metodología del
programa DHS (https://www.dhsprogram.com/methodology/). El archivo incluido en
`data/` contiene las variables derivadas usadas en el análisis.

## Licencia y cita

El contenido se distribuye bajo CC BY 4.0 (ver `LICENSE`). Si utiliza este
repositorio o sus resultados, cite el manuscrito de `paper/`. El DOI del
repositorio se indicará cuando esté disponible.
