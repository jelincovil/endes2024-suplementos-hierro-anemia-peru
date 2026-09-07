#!/usr/bin/env bash
# =============================================================================
# Reproduce TODOS los resultados del manuscrito paper/paper_final_APA7.tex
# a partir de la fuente única de datos data/anemia_valor.dta (ENDES 2024).
#
# Uso (desde la raíz del repositorio):
#   bash run_all.sh          # análisis completo (bootstrap; puede tardar)
#   bash run_all.sh --pdf    # además compila el manuscrito (requiere TeX)
#   bash run_all.sh --fast   # solo anclas del cuerpo + verificación
#
# Determinismo: SEED fijo 20260710 + entornox congelado en requirements-lock.txt.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

PDF="${1:-}"

echo "==> [0/6] Entorno"
python - <<'PY'
mods = ["pandas", "numpy", "scipy", "statsmodels", "sklearn", "matplotlib"]
missing = []
for m in mods:
    try:
        __import__(m)
    except Exception:
        missing.append(m)
if missing:
    raise SystemExit("Faltan dependencias: " + ", ".join(missing) +
                     ". Instale con: pip install -r requirements.txt")
print("    dependencias OK")
PY

echo "==> [1/6] Sensibilidades del cuerpo (IPW×diseño, bootstrap 2000)"
python analysis/sensibilidades_cuerpo.py

if [[ "${PDF}" == "--fast" ]]; then
  echo "==> (modo --fast: se omite el pipeline completo y las figuras)"
else
  echo "==> [2/6] Pipeline completo (IPW/AIPW/matching/robustez/…; puede tardar)"
  python analysis/pipeline_informe_final.py

  echo "==> [3/6] Tablas de mejoras (Lee bounds, mediación, transporte, …)"
  python analysis/pipeline_mejoras_repo.py

  echo "==> [4/6] Figuras del cuerpo (flujo, love plot, bosque)"
  python paper/fig_publish/generar_todas.py
  cp -f paper/fig_publish/figura_flujo_muestral.png \
        paper/fig_publish/figura_1_love_plot.png \
        paper/fig_publish/figura_bosque_esencial.png \
        paper/figuras/
  echo "    PNG del cuerpo sincronizados en paper/figuras/"
fi

echo "==> [5/6] Verificación TEX ↔ CSV (autocheck)"
python analysis/autocheck_tex_csv.py

echo "==> [6/6] Estado"
if git rev-parse --git-dir >/dev/null 2>&1; then
  git --no-pager diff --stat -- paper/tablas paper/figuras || true
  echo "    Compare con 'git diff' los artefactos regenerados."
fi
echo "Listo."

if [[ "${PDF}" == "--pdf" ]]; then
  echo "==> Compilando manuscrito (pdflatex → biber → pdflatex ×2)"
  (cd paper && bash compile.sh)
fi
