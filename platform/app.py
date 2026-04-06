"""
CRTS Crisis Intelligence Platform (CCIP)
Page d'accueil — Navbar fixe + Sélection du type de crise
"""

import random, base64, os
import streamlit as st
import streamlit.components.v1 as components

# ── Logo CRTS encodé en base64 ────────────────────────────────
_logo_path = os.path.join(os.path.dirname(__file__), "static", "crts_logo.png")
with open(_logo_path, "rb") as _f:
    CRTS_LOGO_B64 = f"data:image/png;base64,{base64.b64encode(_f.read()).decode()}"

st.set_page_config(
    page_title="CCIP — CRTS Crisis Intelligence Platform",
    page_icon=_logo_path if os.path.exists(_logo_path) else "🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Navigation vers inondation ────────────────────────────────
if st.session_state.get("goto_flood"):
    st.session_state.pop("goto_flood")
    st.switch_page("pages/1_Inondation.py")

# ═══════════════════════════════════════════════════════════════
# CSS global (pas de -- dans les valeurs)
# ═══════════════════════════════════════════════════════════════
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Inter:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
.stApp { background: #020b18 !important; overflow-x: hidden; }
[data-testid="stSidebar"]       { display: none !important; }
[data-testid="collapsedControl"]{ display: none !important; }
header[data-testid="stHeader"]  { display: none !important; }
footer                          { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stMarkdownContainer"],
[data-testid="stVerticalBlock"] { position: relative; z-index: 1; overflow: visible !important; }

/* Bouton Streamlit override */
[data-testid="baseButton-primary"] {
  font-family: 'Orbitron', monospace !important;
  letter-spacing: 2px !important;
  background: linear-gradient(135deg, #1565c0, #0d47a1) !important;
  border: none !important;
}
[data-testid="baseButton-primary"]:hover {
  background: linear-gradient(135deg, #1976d2, #1565c0) !important;
  box-shadow: 0 6px 28px rgba(21,101,192,0.55) !important;
}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════
# GÉNÉRATION DES ÉTOILES
# ═══════════════════════════════════════════════════════════════
rng = random.Random(42)
stars_html = "".join(
    f'<div class="star" style="left:{rng.uniform(0,100):.1f}%;top:{rng.uniform(0,100):.1f}%;'
    f'width:{rng.uniform(1,3):.1f}px;height:{rng.uniform(1,3):.1f}px;'
    f'animation-duration:{rng.uniform(2,6):.1f}s;opacity:{rng.uniform(0.2,0.8):.1f}"></div>'
    for _ in range(130)
)
data_pts = [
    (8,  22, "SAR-VH: -24.3 dB"), (87, 14, "ORBIT: 705 km"),
    (7,  68, "NDWI: 0.72"),        (89, 62, "S0: -18.6 dB"),
    (12, 88, "UTM 29N"),            (82, 83, "RES: 10m"),
    (50,  5, "S1C ACTIVE"),         (46, 94, "CRTS/DEP"),
    (30, 10, "IW GRD MODE"),        (70,  8, "EPSG:32629"),
]
data_html = "".join(
    f'<div class="data-point" style="left:{x}%;top:{y}%;animation-duration:{2.2+i*0.25:.2f}s">{t}</div>'
    for i, (x, y, t) in enumerate(data_pts)
)

# ═══════════════════════════════════════════════════════════════
# PAGE COMPLÈTE via st.components.v1.html (évite le parseur markdown)
# ═══════════════════════════════════════════════════════════════
PAGE_HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700;900&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ background: #020b18; overflow-x: hidden; font-family: 'Inter', sans-serif; }}

/* ── ANIMATIONS ── */
@keyframes spin      {{ from{{transform:rotate(0deg)}}   to{{transform:rotate(360deg)}} }}
@keyframes spin-rev  {{ from{{transform:rotate(0deg)}}   to{{transform:rotate(-360deg)}} }}
@keyframes blink     {{ 0%,100%{{opacity:1}} 50%{{opacity:.2}} }}
@keyframes twinkle   {{ from{{opacity:.1}} to{{opacity:.9}} }}
@keyframes gridMove  {{ from{{background-position:0 0}} to{{background-position:60px 60px}} }}
@keyframes pglow     {{ 0%,100%{{transform:translate(-50%,-50%) scale(1);opacity:.5}} 50%{{transform:translate(-50%,-50%) scale(1.3);opacity:1}} }}
@keyframes scan      {{ from{{transform:rotate(0deg)}} to{{transform:rotate(360deg)}} }}
@keyframes ffloat    {{ from{{opacity:.15;transform:translateY(0)}} to{{opacity:.6;transform:translateY(-7px)}} }}
@keyframes cspin     {{ from{{transform:translateX(-50%) rotate(0deg)}} to{{transform:translateX(-50%) rotate(-360deg)}} }}
@keyframes cspin2    {{ from{{transform:rotate(0deg)}} to{{transform:rotate(360deg)}} }}

/* ── NAVBAR ── */
.ccip-nav {{
  position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
  height: 60px;
  background: rgba(2,11,24,0.92);
  backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(33,150,243,0.2);
  display: flex; align-items: center;
  padding: 0 28px; gap: 0;
}}
.nav-logo {{
  display: flex; align-items: center; gap: 10px;
  text-decoration: none; flex-shrink: 0;
}}
.nav-logo-img {{
  width: 38px; height: 38px; object-fit: contain;
  background: radial-gradient(circle, rgba(255,255,255,0.18) 0%, rgba(255,255,255,0.06) 55%, transparent 75%);
  border-radius: 50%;
  padding: 3px;
  filter: drop-shadow(0 0 8px rgba(255,255,255,0.35)) brightness(1.15);
}}
.nav-brand {{
  font-family: 'Orbitron', monospace;
  font-size: .88em; font-weight: 700;
  color: #90caf9; letter-spacing: 2px;
}}
.nav-brand span {{ color: rgba(144,202,249,0.4); font-size:.75em; margin-left:4px; }}
.nav-sep {{
  width: 1px; height: 28px;
  background: rgba(33,150,243,0.2);
  margin: 0 22px; flex-shrink: 0;
}}
.nav-crises-label {{
  font-family: 'Orbitron', monospace;
  font-size: .62em; color: rgba(33,150,243,0.5);
  letter-spacing: 3px; margin-right: 14px; flex-shrink: 0;
  text-transform: uppercase;
}}
.nav-crisis-items {{ display: flex; align-items: center; gap: 6px; flex: 1; }}
.nav-crisis-item {{
  display: flex; align-items: center; gap: 7px;
  padding: 5px 13px; border-radius: 20px;
  font-family: 'Inter', sans-serif; font-size: .78em; font-weight: 500;
  text-decoration: none; cursor: pointer;
  transition: all .2s; white-space: nowrap;
  border: 1px solid transparent;
  color: rgba(144,202,249,0.45); background: transparent;
}}
.nav-crisis-item:hover {{ color:#90caf9; background:rgba(33,150,243,0.08); border-color:rgba(33,150,243,0.2); }}
.nav-crisis-item.active {{
  color: #e3f2fd; background: rgba(33,150,243,0.15); border-color: rgba(33,150,243,0.4);
}}
.nav-crisis-item.disabled {{ opacity:.35; cursor:default; pointer-events:none; }}
.dot-active {{
  width: 5px; height: 5px; border-radius: 50%;
  background: #4fc3f7; box-shadow: 0 0 5px #4fc3f7;
  animation: blink 1.5s ease-in-out infinite;
}}
.nav-right {{ display:flex; align-items:center; gap:14px; margin-left:auto; flex-shrink:0; }}
.nav-status {{
  display:flex; align-items:center; gap:6px;
  font-family:'Orbitron',monospace; font-size:.62em; color:rgba(144,202,249,0.5);
}}
.nav-status-dot {{
  width:6px; height:6px; border-radius:50%;
  background:#66bb6a; box-shadow:0 0 5px #66bb6a;
  animation:blink 1.5s ease-in-out infinite;
}}
.nav-version {{
  font-family:'Orbitron',monospace; font-size:.6em;
  color:rgba(33,150,243,0.3); border:1px solid rgba(33,150,243,0.15);
  padding:2px 8px; border-radius:10px;
}}

/* ── FOND SPATIAL ── */
.space-bg {{
  position: fixed; inset: 0; z-index: 0;
  background: radial-gradient(ellipse at 20% 50%, #0a1628 0%, #020b18 60%),
              radial-gradient(ellipse at 80% 20%, #061024 0%, transparent 50%);
  overflow: hidden;
}}
.stars {{ position: absolute; inset: 0; }}
.star {{
  position: absolute; background: white; border-radius: 50%;
  animation: twinkle 3s ease-in-out infinite alternate;
}}
.grid-bg {{
  position: absolute; inset: 0;
  background-image:
    linear-gradient(rgba(33,150,243,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(33,150,243,0.04) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: gridMove 20s linear infinite;
}}
.orbit-wrap {{
  position: absolute; top: 50%; right: 4%;
  transform: translateY(-50%);
  width: 520px; height: 520px;
  pointer-events: none;
}}
.orbit-ring {{
  position: absolute; border-radius: 50%;
  border: 1px solid rgba(33,150,243,0.13);
}}
.orbit-ring-1 {{ inset: 0; animation: spin 18s linear infinite; }}
.orbit-ring-2 {{ inset: 55px; border-color:rgba(100,181,246,0.09); animation: spin-rev 25s linear infinite; }}
.orbit-ring-3 {{ inset: 110px; border-color:rgba(33,150,243,0.06); animation: spin 35s linear infinite; }}
.satellite {{
  position: absolute; top: -11px; left: 50%;
  transform: translateX(-50%);
  font-size: 20px;
  filter: drop-shadow(0 0 8px rgba(33,150,243,0.9));
  animation: cspin 18s linear infinite;
}}
.satellite-2 {{
  position: absolute; bottom: -10px; right: -10px; font-size: 15px;
  filter: drop-shadow(0 0 5px rgba(100,181,246,0.8));
  animation: cspin2 25s linear infinite;
}}
.earth {{
  position: absolute; top:50%; left:50%;
  transform: translate(-50%,-50%);
  width: 72px; height: 72px;
  background: radial-gradient(circle at 35% 35%, #1565c0 0%, #0d47a1 40%, #062a61 100%);
  border-radius: 50%;
  box-shadow: 0 0 36px rgba(33,150,243,0.3), inset -8px -8px 18px rgba(0,0,0,0.4);
  overflow: hidden;
}}
.earth::before {{
  content:''; position:absolute; top:15%; left:20%;
  width:45%; height:35%; background:rgba(255,255,255,0.11);
  border-radius:50%; transform:rotate(-30deg);
}}
.earth-glow {{
  position: absolute; top:50%; left:50%;
  transform: translate(-50%,-50%);
  width:94px; height:94px; border-radius:50%;
  background: radial-gradient(circle, rgba(33,150,243,0.13) 0%, transparent 70%);
  animation: pglow 3s ease-in-out infinite;
}}
.scan-beam {{
  position: absolute; top:50%; left:50%;
  width: 250px; height: 1.5px;
  background: linear-gradient(90deg, rgba(33,150,243,0.5), transparent);
  transform-origin: 0 50%;
  animation: scan 6s linear infinite;
}}
.data-point {{
  position: absolute; font-family:'Orbitron',monospace;
  font-size:9px; color:rgba(100,181,246,0.55);
  animation: ffloat 4s ease-in-out infinite alternate;
}}

/* ── CONTENU PRINCIPAL ── */
.page-wrap {{
  position: relative; z-index: 10;
  min-height: 100vh;
  padding-top: 76px;
  width: 100%;
}}

/* Bandeau gauche : logo + tag */
.left-brand {{
  padding: 28px 0 0 5%;
  margin-bottom: 10px;
}}

.main-content {{
  padding: 20px 5% 20px;
  max-width: 1100px;
  margin: 0 auto;
  width: 100%;
  display: flex; flex-direction: column; align-items: center;
  text-align: center;
}}

/* CRTS identité */
.crts-identity {{
  display: flex; align-items: center; gap: 14px;
}}
.crts-logo-img {{
  width: 60px; height: 60px; object-fit: contain; flex-shrink: 0;
  background: radial-gradient(circle, rgba(255,255,255,0.22) 0%, rgba(255,255,255,0.08) 55%, transparent 75%);
  border-radius: 50%;
  padding: 4px;
  filter: drop-shadow(0 0 12px rgba(255,255,255,0.4)) brightness(1.15);
}}
.crts-abbr {{ font-family:'Orbitron',monospace; font-size:1.05em; font-weight:700; color:#90caf9; letter-spacing:3px; }}
.crts-full {{ font-size:.7em; color:rgba(144,202,249,0.45); letter-spacing:.5px; margin-top:2px; }}

/* Tag — centré au-dessus du titre */
.ccip-tag {{
  font-family:'Orbitron',monospace; font-size:.72em; color:#2196f3; letter-spacing:5px;
  margin-bottom: 22px; display: block; text-align: center;
}}
.ccip-h1 {{
  font-family:'Orbitron',monospace;
  font-size: clamp(2em, 4.5vw, 3.6em);
  font-weight: 900; line-height: 1.15; margin-bottom: 16px;
  background: linear-gradient(135deg, #ffffff 0%, #90caf9 45%, #2196f3 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}}
.ccip-sub {{
  font-size:.95em; color:rgba(144,202,249,0.55); line-height:1.7; margin-bottom:32px;
  max-width: 420px; text-align: center; letter-spacing: 1px;
}}
.light-line {{
  width: 100px; height: 2px; margin-bottom: 32px;
  background: linear-gradient(90deg, transparent, #2196f3, transparent);
}}

/* Status pills */
.status-pills {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:44px; justify-content: center; }}
.spill {{
  display:flex; align-items:center; gap:6px;
  padding:5px 12px; border-radius:20px;
  background:rgba(33,150,243,0.08); border:1px solid rgba(33,150,243,0.18);
  font-family:'Orbitron',monospace; font-size:.62em; color:rgba(144,202,249,0.7);
}}
.spill-dot {{ width:5px; height:5px; border-radius:50%; }}
.spill-green {{ background:#66bb6a; box-shadow:0 0 4px #66bb6a; }}
.spill-blue  {{ background:#2196f3; box-shadow:0 0 4px #2196f3; }}

/* Section titre */
.section-crises {{
  font-family:'Orbitron',monospace; font-size:.65em;
  color:rgba(33,150,243,0.5); letter-spacing:4px;
  margin-bottom:18px; text-transform:uppercase;
}}

/* ── GRILLE DES CRISES ── */
.crisis-grid {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px; width: 100%; max-width: 1100px;
  margin-bottom: 36px;
}}
.crisis-card {{
  position: relative;
  background: linear-gradient(145deg, rgba(13,33,57,0.88), rgba(6,18,36,0.94));
  border: 1px solid rgba(33,150,243,0.18);
  border-radius: 16px; padding: 36px 22px 28px;
  text-align: center; overflow: hidden;
  transition: all .3s ease;
  text-decoration: none;
  color: #e3f2fd;
  display: block;
}}
.crisis-card::after {{
  content:''; position:absolute; top:0; left:0; right:0; height:2px;
  opacity:0; transition:opacity .3s;
}}
.crisis-card.card-flood {{ border-color: rgba(33,150,243,0.35); }}
.crisis-card.card-flood::after {{ background: #2196f3; opacity: 1; }}
.crisis-card.card-fire::after   {{ background: #ef5350; }}
.crisis-card.card-quake::after  {{ background: #ffa726; }}
.crisis-card.card-storm::after  {{ background: #ab47bc; }}
.crisis-card.card-drought::after{{ background: #26a69a; }}

.crisis-card.active {{
  cursor: pointer;
  box-shadow: 0 0 20px rgba(33,150,243,0.08);
}}
.crisis-card.active:hover {{
  transform: translateY(-5px);
  border-color: rgba(33,150,243,0.7);
  box-shadow: 0 18px 50px rgba(0,0,0,0.35), 0 0 30px rgba(33,150,243,0.18);
}}
.crisis-card.active:hover::after {{ opacity: 1; }}
.crisis-card.soon {{ cursor: default; opacity: .45; pointer-events: none; }}

.card-icon  {{ font-size:3em; margin-bottom:14px; display:block; }}
.card-title {{
  font-family:'Orbitron',monospace; font-size:.82em; font-weight:700;
  color:#e3f2fd; letter-spacing:1px; margin-bottom:8px;
}}
.card-desc  {{ font-size:.78em; color:rgba(144,202,249,0.5); line-height:1.5; }}
.card-badge {{
  display:inline-block; margin-top:10px;
  padding:2px 10px; border-radius:20px;
  font-size:.62em; font-weight:600; letter-spacing:1px;
  font-family:'Orbitron',monospace;
}}
.badge-active {{ background:rgba(33,150,243,0.2); color:#64b5f6; border:1px solid rgba(33,150,243,0.4); }}
.badge-soon   {{ background:rgba(60,60,60,0.25);  color:#455a64;  border:1px solid rgba(60,60,60,0.3); }}

/* Footer */
.ccip-footer {{
  text-align:center; padding: 40px 24px;
  font-size:.72em; color:rgba(55,71,79,0.7); letter-spacing:.5px;
  border-top:1px solid rgba(33,150,243,0.06);
}}

@media (max-width:900px) {{
  .crisis-grid {{ grid-template-columns: repeat(2,1fr); }}
  .orbit-wrap  {{ width:300px; height:300px; right:-5%; }}
  .main-content {{ padding: 30px 5% 20px; }}
}}
@media (max-width:600px) {{
  .crisis-grid {{ grid-template-columns: repeat(2,1fr); }}
  .ccip-h1 {{ font-size:1.7em; }}
}}
</style>
</head>
<body>

<!-- ═══ NAVBAR ═══ -->
<nav class="ccip-nav">
  <a class="nav-logo" href="/" target="_top">
    <img class="nav-logo-img" src="{CRTS_LOGO_B64}" alt="CRTS">
    <div class="nav-brand">CCIP <span>· CRTS</span></div>
  </a>
  <div class="nav-sep"></div>
  <div class="nav-crises-label">Crises</div>
  <div class="nav-crisis-items">
    <a class="nav-crisis-item active" href="/Inondation" target="_top">
      <div class="dot-active"></div>
      🌊 Inondation
    </a>
    <span class="nav-crisis-item disabled">🔥 Incendie</span>
    <span class="nav-crisis-item disabled">🏔️ Séisme</span>
    <span class="nav-crisis-item disabled">🌪️ Tempête</span>
    <span class="nav-crisis-item disabled">🏜️ Sécheresse</span>
  </div>
  <div class="nav-right">
    <div class="nav-status">
      <div class="nav-status-dot"></div>
      S1 OPÉRATIONNEL
    </div>
    <div class="nav-version">v1.0</div>
  </div>
</nav>

<!-- ═══ FOND SPATIAL ═══ -->
<div class="space-bg">
  <div class="stars">{stars_html}</div>
  <div class="grid-bg"></div>
  <div class="orbit-wrap">
    <div class="orbit-ring orbit-ring-1"><div class="satellite">🛰️</div></div>
    <div class="orbit-ring orbit-ring-2"><div class="satellite-2">🛰️</div></div>
    <div class="orbit-ring orbit-ring-3"></div>
    <div class="earth-glow"></div>
    <div class="earth"></div>
    <div class="scan-beam"></div>
  </div>
  {data_html}
</div>

<!-- ═══ CONTENU ═══ -->
<div class="page-wrap">

  <!-- Identité CRTS — top-left -->
  <div class="left-brand">
    <div class="crts-identity">
      <img src="{CRTS_LOGO_B64}" alt="CRTS" class="crts-logo-img">
      <div>
        <div class="crts-abbr">CRTS</div>
        <div class="crts-full">Centre Royal de Télédétection Spatiale</div>
      </div>
    </div>
  </div>

  <div class="main-content">

    <!-- Tag centré -->
    <div class="ccip-tag">[ SYSTÈME DE SURVEILLANCE PAR SATELLITE ]</div>

    <!-- Titre sur deux lignes -->
    <div class="ccip-h1">Crisis Intelligence<br>Platform</div>
    <div class="ccip-sub">CCIP · CRTS/DEP · Maroc</div>
    <div class="light-line"></div>

    <!-- Status pills -->
    <div class="status-pills">
      <div class="spill"><div class="spill-dot spill-green"></div>SENTINEL-1 OPÉRATIONNEL</div>
      <div class="spill"><div class="spill-dot spill-blue"></div>ESA SNAP V13 ACTIF</div>
      <div class="spill"><div class="spill-dot spill-blue"></div>QGIS 3.44 CONNECTÉ</div>
      <div class="spill"><div class="spill-dot spill-green"></div>GADM MAR V4.1 CHARGÉ</div>
    </div>

    <!-- Sélection crise -->
    <div class="section-crises">— SÉLECTIONNEZ LE TYPE DE CRISE —</div>

    <!-- Grille des crises — 4 colonnes -->
    <div class="crisis-grid">

      <a class="crisis-card active card-flood" href="/Inondation" target="_top">
        <span class="card-icon">🌊</span>
        <div class="card-title">INONDATION</div>
        <div class="card-desc">Cartographie SAR des zones inondées via Sentinel-1 GRD/SLC</div>
        <span class="card-badge badge-active">● ACTIF</span>
      </a>

      <div class="crisis-card soon card-fire">
        <span class="card-icon">🔥</span>
        <div class="card-title">INCENDIE</div>
        <div class="card-desc">Détection des feux de forêt par imagerie Sentinel-2/MODIS</div>
        <span class="card-badge badge-soon">BIENTÔT</span>
      </div>

      <div class="crisis-card soon card-quake">
        <span class="card-icon">🏔️</span>
        <div class="card-title">SÉISME</div>
        <div class="card-desc">Évaluation des dommages par InSAR et analyse SAR</div>
        <span class="card-badge badge-soon">BIENTÔT</span>
      </div>

      <div class="crisis-card soon card-storm">
        <span class="card-icon">🌪️</span>
        <div class="card-title">TEMPÊTE</div>
        <div class="card-desc">Suivi des systèmes météo et cartographie des impacts</div>
        <span class="card-badge badge-soon">BIENTÔT</span>
      </div>

      <div class="crisis-card soon card-drought">
        <span class="card-icon">🏜️</span>
        <div class="card-title">SÉCHERESSE</div>
        <div class="card-desc">Suivi NDVI/NDWI et stress hydrique agricole</div>
        <span class="card-badge badge-soon">BIENTÔT</span>
      </div>

    </div>

  </div>

  <!-- Footer -->
  <div class="ccip-footer">
    CRTS Crisis Intelligence Platform (CCIP) · v1.0 &nbsp;|&nbsp;
    Centre Royal de Télédétection Spatiale — Division Études &amp; Projets &nbsp;|&nbsp;
    ESA SNAP · QGIS/GDAL · Sentinel-1
  </div>
</div>

</body>
</html>
"""

components.html(PAGE_HTML, height=950, scrolling=True)
