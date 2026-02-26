from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Header
import requests
import os
from dotenv import load_dotenv
from datetime import datetime
import shutil



from fastapi.responses import HTMLResponse

@app.get("/", response_class=HTMLResponse)
def form():
    return """
    <html>
        <body>
            <h2>DMCA Request</h2>
            <form action="/dmca" method="post" enctype="multipart/form-data">
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


load_dotenv()

app = FastAPI()

WP_URL = os.getenv("WP_URL")
WP_USER = os.getenv("WP_USER")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN")

EVIDENCE_PATH = "storage/evidencias"
LOG_FILE = "logs/dmca_log.json"

os.makedirs(EVIDENCE_PATH, exist_ok=True)
os.makedirs("logs", exist_ok=True)

def extract_slug(url):
    return url.rstrip("/").split("/")[-1]

def get_post_id(slug):
    r = requests.get(
        f"{WP_URL}/wp-json/wp/v2/posts",
        params={"slug": slug},
        auth=(WP_USER, WP_APP_PASSWORD)
    )
    data = r.json()
    if not data:
        return None
    return data[0]["id"]

def trash_post(post_id):
    r = requests.post(
        f"{WP_URL}/wp-json/wp/v2/posts/{post_id}",
        json={"status": "trash"},
        auth=(WP_USER, WP_APP_PASSWORD)
    )
    return r.status_code == 200

@app.post("/dmca")
async def dmca(
    url: str = Form(...),
    motivo: str = Form(...),
    evidencia: UploadFile = File(...),
    x_token: str = Header(None)
):
    if x_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=403, detail="Unauthorized")

    slug = extract_slug(url)
    post_id = get_post_id(slug)

    if not post_id:
        raise HTTPException(status_code=404, detail="Post not found")

    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{slug}_{evidencia.filename}"
    filepath = os.path.join(EVIDENCE_PATH, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(evidencia.file, buffer)

    success = trash_post(post_id)

    if not success:
        raise HTTPException(status_code=500, detail="Error trashing post")

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
        f.write(str(log_entry) + "\n")

    return {"status": "success", "post_id": post_id}