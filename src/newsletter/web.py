import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from .config import settings
from .db import add_subscriber, init_db, remove_subscriber
from .main import start_scheduler_thread

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(settings.database_path)
    start_scheduler_thread()
    logger.info("Scheduler thread started")
    yield


app = FastAPI(title="Knowledge in Chain", lifespan=lifespan)


class SubscribeRequest(BaseModel):
    email: str


EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")


@app.get("/", response_class=HTMLResponse)
async def landing():
    template = jinja_env.get_template("landing.html")
    return template.render()


@app.post("/api/subscribe")
async def subscribe(req: SubscribeRequest):
    email = req.email.strip().lower()
    if not EMAIL_RE.match(email):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Invalid email address."},
        )
    added = add_subscriber(settings.database_path, email)
    if added:
        return {"ok": True, "message": "You're subscribed! Welcome aboard."}
    return {"ok": True, "message": "You're already subscribed!"}


@app.get("/api/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(email: str = ""):
    email = email.strip().lower()
    if email and EMAIL_RE.match(email):
        removed = remove_subscriber(settings.database_path, email)
    else:
        removed = False

    template = jinja_env.get_template("unsubscribe.html")
    return template.render(email=email, removed=removed)


@app.get("/health")
async def health():
    return {"status": "ok"}
