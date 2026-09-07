# =============================================================================
# latexmkrc — compilación nativa con biblatex + biber en editores independientes
# (Overleaf, VS Code LaTeX Workshop, TeXstudio, TeXShop y cualquier editor que
#  use latexmk como motor).
#
# Sin este archivo, un editor que ejecute sólo una pasada de pdflatex (o que
# lance "bibtex" por defecto) produce el PDF SIN referencias, porque biblatex
# con backend=biber necesita la cadena: pdflatex -> biber -> pdflatex -> pdflatex.
# Con este archivo, latexmk orquesta esa cadena automáticamente.
#
# Flujo documentado equivalente (terminal):
#   pdflatex -interaction=nonstopmode paper_final_APA7.tex
#   biber paper_final_APA7
#   pdflatex -interaction=nonstopmode paper_final_APA7.tex
#   pdflatex -interaction=nonstopmode paper_final_APA7.tex
# =============================================================================

# Motor PDF: pdflatex (1 = pdflatex, 0 = latex+dvipdf, 4 = lualatex, 5 = xelatex)
$pdf_mode = 1;

# Pasadas y opciones de pdflatex
$pdflatex = 'pdflatex -synctex=1 -interaction=nonstopmode -halt-on-error %O %S';

# biblatex usa biber; forzamos explícitamente el programa
$biber = 'biber %O %S';
# Si algún flujo genérico decidiera ejecutar 'bibtex', que ejecute biber
# (la cadena biblatex+biber es incompatible con bibtex clásico).
$bibtex = 'biber %O %S';

# Nº máximo de pasadas (pdflatex+biber+pdflatex+pdflatex = 4; margen seguro)
$max_repeat = 5;

# No detenerse preguntando por archivos no encontrados (Overleaf/CI friendly)
$force_long_parskip = 0;
