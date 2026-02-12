import hashlib
import logging
import re
import secrets
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

from .config import settings
from .db import (
    add_subscriber,
    get_api_usage_stats,
    get_article_stats,
    get_email_stats,
    get_pipeline_runs,
    get_subscriber_stats,
    init_db,
    remove_subscriber,
)
from .main import run_pipeline, start_scheduler_thread

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)

# Auth token store: maps token -> True
_auth_tokens: dict[str, bool] = {}


def _check_auth(token: str | None) -> bool:
    if not token:
        return False
    return _auth_tokens.get(token, False)


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


# ---------------------------------------------------------------------------
# Dashboard auth
# ---------------------------------------------------------------------------

@app.post("/dashboard/login")
async def dashboard_login(password: str = Form(...)):
    expected = settings.dashboard_password
    if not expected:
        return JSONResponse(status_code=403, content={"error": "Dashboard password not configured"})
    if not secrets.compare_digest(password, expected):
        template = jinja_env.get_template("dashboard.html")
        return HTMLResponse(template.render(authenticated=False, error="Invalid password"))
    token = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
    _auth_tokens[token] = True
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="dashboard_token", value=token, httponly=True, max_age=86400)
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(dashboard_token: str | None = Cookie(default=None)):
    authenticated = _check_auth(dashboard_token)
    if not settings.dashboard_password:
        authenticated = True  # No password set = open access
    template = jinja_env.get_template("dashboard.html")
    return HTMLResponse(template.render(authenticated=authenticated, error=None))


# ---------------------------------------------------------------------------
# Dashboard API endpoints
# ---------------------------------------------------------------------------

def _require_auth(token: str | None) -> JSONResponse | None:
    if not settings.dashboard_password:
        return None  # No password = open access
    if not _check_auth(token):
        return JSONResponse(status_code=401, content={"error": "Unauthorized"})
    return None


@app.get("/api/dashboard/subscribers")
async def api_subscribers(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_subscriber_stats(settings.database_path, env_subscribers=settings.subscriber_list)


@app.get("/api/dashboard/articles")
async def api_articles(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_article_stats(settings.database_path)


@app.get("/api/dashboard/api-costs")
async def api_costs(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_api_usage_stats(settings.database_path)


@app.get("/api/dashboard/emails")
async def api_emails(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_email_stats(settings.database_path)


@app.get("/api/dashboard/pipeline-runs")
async def api_pipeline_runs(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_pipeline_runs(settings.database_path)


@app.post("/api/dashboard/trigger-pipeline")
async def trigger_pipeline(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    # Run pipeline in background thread
    t = threading.Thread(target=run_pipeline, kwargs={"dry_run": True}, daemon=True)
    t.start()
    return {"ok": True, "message": "Pipeline triggered (dry-run). Check pipeline runs for progress."}
