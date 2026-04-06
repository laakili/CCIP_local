"""Configuration globale de la plateforme

Les chemins des outils sont lus depuis des variables d'environnement,
avec des valeurs de repli pour macOS (développement local).
Sur Linux/Docker les variables ENV définies dans le Dockerfile sont utilisées.
"""

import os
import platform

# ── Outils externes ──────────────────────────────────────────────────────────
SNAP_GPT    = os.environ.get("SNAP_GPT_PATH",    "/Applications/esa-snap/bin/gpt")
PYTHON_QGIS = os.environ.get("PYTHON_EXEC",      "/Applications/QGIS.app/Contents/MacOS/python3.12")
GDAL_BIN    = os.environ.get("GDAL_BIN",         "/Applications/QGIS.app/Contents/MacOS")
GDAL_POLYGONIZE = os.environ.get("GDAL_POLYGONIZE",
                                  "/Applications/QGIS.app/Contents/MacOS/gdal_polygonize.py")
PROJ_DATA   = os.environ.get("PROJ_LIB",
                              "/Applications/QGIS.app/Contents/Resources/qgis/proj")

# ── Variables d'environnement injectées lors de l'exécution des sous-processus
# Sur Linux/Docker aucune variable QGIS spécifique n'est nécessaire.
if platform.system() == "Linux":
    QGIS_ENV = {}
else:
    QGIS_ENV = {
        "PYTHONHOME":          "/Applications/QGIS.app/Contents/Frameworks",
        "PYTHONPATH":          (
            "/Applications/QGIS.app/Contents/Resources/python3.11/site-packages"
            ":/Applications/QGIS.app/Contents/Frameworks/lib/python3.12"
        ),
        "DYLD_FRAMEWORK_PATH": "/Applications/QGIS.app/Contents/Frameworks",
        "PROJ_DATA":           PROJ_DATA,
        "PROJ_LIB":            PROJ_DATA,
    }

# ── Données GADM (communes Maroc) ────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GADM_DEFAULT = os.environ.get(
    "GADM_PATH",
    os.path.join(_BASE_DIR, "data", "gadm", "gadm41_MAR_4.shp"),
)

# ── Répertoires de la plateforme ─────────────────────────────────────────────
PLATFORM_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR   = os.environ.get("RESULTS_DIR", os.path.join(PLATFORM_DIR, "results"))
TEMPLATES_DIR = os.path.join(PLATFORM_DIR, "templates")
STATIC_DIR    = os.path.join(PLATFORM_DIR, "static")
GRAPHS_DIR    = os.path.join(PLATFORM_DIR, "core", "graphs")

os.makedirs(RESULTS_DIR, exist_ok=True)
os.makedirs(GRAPHS_DIR,  exist_ok=True)

# ── Paramètres de traitement par défaut ──────────────────────────────────────
DEFAULT_PARAMS = {
    "polarisation":   "VH",
    "pixel_spacing":  10.0,
    "dem":            "SRTM 1Sec HGT",
    "speckle_filter": "Refined Lee",
    "seuil_db":       -26.0,
    "area_min_ha":    0.5,
    "epsg":           32629,       # UTM 29N (Maroc Nord)
    "aoi": {                       # Zone El Gharb par défaut
        "lon_min": -6.8, "lat_min": 33.5,
        "lon_max": -4.8, "lat_max": 35.8
    }
}
