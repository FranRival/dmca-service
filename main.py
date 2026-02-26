from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import shutil
import json
from urllib.parse import urlparse

# -----------------------------
# INIT
# -----------------------------

load_dotenv()
app = FastAPI()

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN")

if not all([WP_URL, WP_USER, WP_APP_PASSWORD, INTERNAL_TOKEN]):
    raise Exception("Faltan variables en el .env")

EVIDENCE_PATH = "storage/evidencias"
LOG_FILE = "logs/dmca_log.json"

os.makedirs(EVIDENCE_PATH, exist_ok=True)
os.makedirs("logs", exist_ok=True)

# -----------------------------
# FORMULARIO
# -----------------------------

@app.get("/", response_class=HTMLResponse)
def form():
    return f"""
    <html>
        <body>
            <h2>DMCA Request</h2>
            <form action="/dmca" method="post" enctype="multipart/form-data">
                
                <label>Token interno:</label><br>
                <input type="password" name="token" required><br><br>

                <label>URL denunciada:</label><br>
                <input type="url" name="url" required><br><br>

                <label>Motivo:</label><br>
                <textarea name="motivo" required></textarea><br><br>

                <label>Imagen de evidencia:</label><br>
                <input type="file" name="evidencia" accept="image/*" required><br><br>

                <button type="submit">Enviar denuncia</button>
            </form>
        </body>
    </html>
    """

# -----------------------------
# HELPERS
# -----------------------------

def extract_slug(url):
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return path.split("/")[-1]

def validate_domain(url):
    return url.startswith(WP_URL)

def get_post_id(slug):
    try:
        r = requests.get(
            f"{WP_URL}/wp-json/wp/v2/posts",
            params={"slug": slug},
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return data[0]["id"]
    except Exception:
        return None

def trash_post(post_id):
    try:
        r = requests.post(
            f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
            json={"status": "trash"},
            auth=(WP_USER, WP_APP_PASSWORD),
            timeout=10
        )
        return r.status_code == 200
    except Exception:
        return False

# -----------------------------
# ENDPOINT DMCA
# -----------------------------

@app.post("/dmca")
async def dmca(
    token: str = Form(...),
    url: str = Form(...),
    motivo: str = Form(...),
    evidencia: UploadFile = File(...)
):
    # Seguridad
    if token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")

    if not validate_domain(url):
        raise HTTPException(status_code=400, detail="URL no pertenece al dominio permitido")

    slug = extract_slug(url)
    post_id = get_post_id(slug)

    if not post_id:
        raise HTTPException(status_code=404, detail="Post not found")

    # Guardar evidencia
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{slug}_{evidencia.filename}"
    filepath = os.path.join(EVIDENCE_PATH, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(evidencia.file, buffer)

    # Ejecutar trash
    success = trash_post(post_id)

    if not success:
        raise HTTPException(status_code=500, detail="Error trashing post")

    # Guardar log JSON real
    log_entry = {
        "date": datetime.now().isoformat(),
        "url": url,
        "slug": slug,
        "post_id": post_id,
        "motivo": motivo,
        "evidence": filename,
        "status": "trashed"
    }

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return {"status": "success", "post_id": post_id}