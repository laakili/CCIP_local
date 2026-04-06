#!/bin/bash
# ─── Plateforme Gestion de Crise Inondation — Démarrage ───────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "Démarrage de la plateforme sur http://localhost:8501"
python3 -m streamlit run "$SCRIPT_DIR/app.py" \
  --server.enableStaticServing true \
  --server.port 8501 \
  --server.headless true \
  --server.maxUploadSize 4096 \
  --browser.gatherUsageStats false \
  --theme.base dark \
  --theme.primaryColor "#2196f3" \
  --theme.backgroundColor "#0b1422" \
  --theme.secondaryBackgroundColor "#0f1e30" \
  --theme.textColor "#d0dce8"
