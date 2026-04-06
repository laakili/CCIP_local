#!/usr/bin/env python3
"""
Plateforme Gestion de Crise Inondation — Serveur HTTP
Démarre sur http://localhost:8080
"""

import os, sys, json, uuid, threading, mimetypes, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Ajouter le dossier plateforme au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.pipeline import FloodPipeline, Job
from core.config   import RESULTS_DIR, STATIC_DIR, TEMPLATES_DIR

# Stockage des jobs en mémoire
JOBS: dict[str, Job] = {}

# ─── Charger les jobs précédents depuis disque ────────────────────────────────
def load_existing_jobs():
    if not os.path.exists(RESULTS_DIR):
        return
    for job_id in os.listdir(RESULTS_DIR):
        state_file = os.path.join(RESULTS_DIR, job_id, "state.json")
        if os.path.exists(state_file):
            try:
                with open(state_file) as f:
                    state = json.load(f)
                job = Job(job_id, state.get("params", {}))
                job.status   = state.get("status", "unknown")
                job.progress = state.get("progress", 0)
                job.logs     = state.get("logs", [])
                job.results  = state.get("results", {})
                job.created  = state.get("created", "")
                job.finished = state.get("finished", "")
                JOBS[job_id] = job
            except:
                pass

load_existing_jobs()

# ─── Handler HTTP ─────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # Silencieux sauf erreurs

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self._serve_file(os.path.join(TEMPLATES_DIR, "index.html"), "text/html")

        elif path.startswith("/static/"):
            rel  = path[len("/static/"):]
            fpath = os.path.join(STATIC_DIR, rel)
            mime  = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
            self._serve_file(fpath, mime)

        elif path == "/api/jobs":
            jobs_list = []
            for jid, job in sorted(JOBS.items(),
                    key=lambda x: x[1].created, reverse=True):
                jobs_list.append({
                    "id":       jid,
                    "status":   job.status,
                    "progress": job.progress,
                    "created":  job.created,
                    "finished": job.finished,
                    "mode":     "avant/après" if job.params.get("image_before") else "image unique",
                })
            self._json(jobs_list)

        elif path.startswith("/api/job/") and path.endswith("/state"):
            jid = path.split("/")[3]
            job = JOBS.get(jid)
            if not job:
                self._json({"error": "job introuvable"}, 404)
                return
            self._json({
                "id":       job.id,
                "status":   job.status,
                "progress": job.progress,
                "logs":     job.logs[-50:],
                "results":  job.results,
                "created":  job.created,
                "finished": job.finished,
            })

        elif path.startswith("/api/job/") and path.endswith("/rapport"):
            jid = path.split("/")[3]
            job = JOBS.get(jid)
            if not job or not job.results.get("rapport"):
                self._json({"error": "rapport non disponible"}, 404)
                return
            self._serve_file(job.results["rapport"], "text/html")

        elif path.startswith("/api/job/") and path.endswith("/download"):
            # Télécharge le CSV global
            jid = path.split("/")[3]
            job = JOBS.get(jid)
            if not job or not job.results.get("stats_csv"):
                self._json({"error": "CSV non disponible"}, 404)
                return
            self._serve_file(job.results["stats_csv"], "text/csv",
                             download=f"statistiques_{jid[:8]}.csv")

        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/api/jobs/create":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                params = json.loads(body)
            except:
                self._json({"error": "JSON invalide"}, 400)
                return

            # Validation minimale
            if not params.get("image_after"):
                self._json({"error": "image_after est obligatoire"}, 400)
                return

            job_id = uuid.uuid4().hex[:12]
            job    = Job(job_id, params)
            JOBS[job_id] = job

            # Lancer le pipeline dans un thread séparé
            def run():
                pipeline = FloodPipeline(job)
                pipeline.run()

            t = threading.Thread(target=run, daemon=True)
            t.start()

            self._json({"job_id": job_id, "status": "started"}, 201)

        elif path.startswith("/api/job/") and path.endswith("/cancel"):
            jid = path.split("/")[3]
            job = JOBS.get(jid)
            if job and job.status == "running":
                job.status = "cancelled"
                job.log("Job annulé par l'utilisateur", "WARN")
                job._save_state()
            self._json({"ok": True})

        else:
            self._json({"error": "not found"}, 404)

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, fpath, mime, download=None):
        if not os.path.exists(fpath):
            self._json({"error": f"fichier introuvable: {fpath}"}, 404)
            return
        with open(fpath, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(body))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(body)


# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT","8080"))
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"""
╔══════════════════════════════════════════════════════════╗
║   🌊  Plateforme Gestion de Crise Inondation — CRTS      ║
╠══════════════════════════════════════════════════════════╣
║   URL :  http://localhost:{PORT}                          ║
║   Jobs:  {RESULTS_DIR}
║                                                          ║
║   Ctrl+C pour arrêter                                    ║
╚══════════════════════════════════════════════════════════╝
""")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrêté.")
