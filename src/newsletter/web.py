import hashlib
import json
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
    delete_history_entry,
    delete_pending_newsletter,
    get_api_cost_breakdown,
    get_api_usage_stats,
    get_article_stats,
    get_db_diagnostic,
    get_email_sends,
    get_email_stats,
    get_failed_emails,
    get_history_entries,
    get_history_for_landing,
    get_last_newsletter_emails,
    get_latest_email_status,
    get_linkedin_post,
    get_newsletter_by_id,
    get_pending_newsletters,
    get_pipeline_runs,
    get_sent_newsletters,
    get_subscriber_list,
    get_subscriber_growth,
    get_subscriber_stats,
    requeue_newsletter,
    init_db,
    remove_subscriber,
    update_newsletter_html,
    update_retry_status,
    update_subscriber_email,
)
from .generator import render_html
from . import main as main_module
from .main import run_pipeline, start_scheduler_thread
from .emailer import send_newsletter

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
    # Migrate env var subscribers to DB
    env_emails = settings.subscriber_list
    if env_emails:
        migrated = 0
        for email in env_emails:
            if add_subscriber(settings.database_path, email.strip().lower()):
                migrated += 1
        if migrated:
            logger.info(f"Migrated {migrated} env subscribers to DB")
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
    newsletters = get_history_for_landing(settings.database_path, limit=5)
    return template.render(newsletters=newsletters)


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


@app.get("/newsletter/{newsletter_id}", response_class=HTMLResponse)
async def newsletter_detail(newsletter_id: str):
    newsletter = get_newsletter_by_id(settings.database_path, newsletter_id)
    if newsletter is None:
        return HTMLResponse("<h1>Newsletter not found</h1>", status_code=404)
    return HTMLResponse(newsletter["html_content"])


@app.get("/newsletter/{newsletter_id}/linkedin")
async def newsletter_linkedin(newsletter_id: str):
    post = get_linkedin_post(settings.database_path, newsletter_id)
    if post is None:
        return JSONResponse(status_code=404, content={"error": "Newsletter not found"})
    return {"newsletter_id": newsletter_id, "linkedin_post": post}


@app.get("/health")
async def health():
    t = main_module._scheduler_thread
    scheduler_alive = t is not None and t.is_alive()
    status = "ok" if scheduler_alive else "degraded"
    return {"status": status, "scheduler_alive": scheduler_alive}


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
    return get_subscriber_stats(settings.database_path)


@app.get("/api/dashboard/subscribers/growth")
async def api_subscriber_growth(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_subscriber_growth(settings.database_path)


@app.get("/api/dashboard/subscribers/list")
async def api_subscriber_list(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_subscriber_list(settings.database_path)


class UpdateEmailRequest(BaseModel):
    old_email: str
    new_email: str


@app.patch("/api/dashboard/subscribers/update-email")
async def api_update_subscriber_email(
    request: UpdateEmailRequest,
    dashboard_token: str | None = Cookie(default=None)
):
    err = _require_auth(dashboard_token)
    if err:
        return err

    success = update_subscriber_email(
        settings.database_path,
        request.old_email,
        request.new_email
    )

    if success:
        return {"success": True, "message": f"Email updated from {request.old_email} to {request.new_email}"}
    else:
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": f"Subscriber with email {request.old_email} not found"}
        )


class AddSubscriberRequest(BaseModel):
    email: str


@app.post("/api/dashboard/subscribers/add")
async def api_add_subscriber(
    request: AddSubscriberRequest,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err

    email = request.email.strip().lower()
    if not EMAIL_RE.match(email):
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "Invalid email address"},
        )

    added = add_subscriber(settings.database_path, email)
    if added:
        return {"ok": True, "message": f"Subscriber {email} added successfully"}
    return JSONResponse(
        status_code=409,
        content={"ok": False, "message": f"{email} is already an active subscriber"},
    )


class RemoveSubscriberRequest(BaseModel):
    email: str


@app.delete("/api/dashboard/subscribers/remove")
async def api_remove_subscriber(
    request: RemoveSubscriberRequest,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err

    email = request.email.strip().lower()
    removed = remove_subscriber(settings.database_path, email)
    if removed:
        return {"ok": True, "message": f"Subscriber {email} deactivated"}
    return JSONResponse(
        status_code=404,
        content={"ok": False, "message": f"Active subscriber {email} not found"},
    )


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
    stats = get_api_usage_stats(settings.database_path)
    breakdown = get_api_cost_breakdown(settings.database_path)
    stats["by_step"] = breakdown["by_step"]
    stats["by_model"] = breakdown["by_model"]
    return stats


@app.get("/api/dashboard/emails")
async def api_emails(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    stats = get_email_stats(settings.database_path)
    last = get_last_newsletter_emails(settings.database_path)
    sends = get_email_sends(settings.database_path)
    return {
        "total_sent": stats["total_sent"],
        "total_failed": stats["total_failed"],
        "pipeline_run_id": last["pipeline_run_id"],
        "recent": last["recent"],
        "sends": sends,
    }


@app.get("/api/dashboard/emails/failed")
async def api_failed_emails(
    dashboard_token: str | None = Cookie(default=None),
    days: int = 7,
):
    err = _require_auth(dashboard_token)
    if err:
        return err
    failed = get_failed_emails(settings.database_path, days=days)
    # Group by recipient to show unique emails
    unique_recipients = {}
    for entry in failed:
        email = entry["recipient"]
        if email not in unique_recipients:
            unique_recipients[email] = entry
    return {
        "total": len(failed),
        "unique_recipients": len(unique_recipients),
        "failed_emails": list(unique_recipients.values()),
    }


class RetryEmailsRequest(BaseModel):
    recipients: list[str]


@app.post("/api/dashboard/emails/retry")
async def api_retry_emails(
    request: RetryEmailsRequest,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err

    if not request.recipients:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": "No recipients provided"}
        )

    # Get the most recent sent newsletter (with full content)
    sent_newsletters = get_sent_newsletters(settings.database_path, limit=1)
    if not sent_newsletters:
        return JSONResponse(
            status_code=404,
            content={"ok": False, "message": "No sent newsletter found to retry"}
        )

    # Get full newsletter content including HTML
    newsletter_id = sent_newsletters[0]["id"]
    sent_newsletter = get_newsletter_by_id(settings.database_path, newsletter_id)

    if not sent_newsletter or not sent_newsletter.get("html_content"):
        return JSONResponse(
            status_code=404,
            content={"ok": False, "message": "Newsletter content not found"}
        )

    # Extract edition number from json_data if available
    try:
        json_data = json.loads(sent_newsletter.get("json_data", "{}"))
        edition_number = json_data.get("edition_number", "")
        if edition_number:
            subject = f"Knowledge in Chain - Edition #{edition_number}"
        else:
            subject = sent_newsletter.get("subject", "Knowledge in Chain Newsletter")
    except (json.JSONDecodeError, KeyError):
        subject = sent_newsletter.get("subject", "Knowledge in Chain Newsletter")

    # Send newsletter to failed recipients
    try:
        result = send_newsletter(
            html_content=sent_newsletter["html_content"],
            from_email=settings.newsletter_from_email,
            subscribers=request.recipients,
            api_key=settings.resend_api_key,
            base_url=settings.base_url,
            db_path=settings.database_path,
            pipeline_run_id="manual_retry",
            subject=subject,
        )

        # Update retry_status on original failed entries
        for recipient in request.recipients:
            retry_result = get_latest_email_status(
                settings.database_path, recipient, "manual_retry"
            )
            if retry_result == "sent":
                update_retry_status(settings.database_path, recipient, "resolved")
            elif retry_result == "failed":
                update_retry_status(settings.database_path, recipient, "retry_failed")

        return {
            "ok": True,
            "sent": result["sent"],
            "failed": result["failed"],
            "message": f"Retry complete: {result['sent']} sent, {result['failed']} failed",
        }
    except Exception as e:
        logger.exception("Failed to retry emails")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "message": f"Error: {str(e)}"}
        )


@app.get("/api/dashboard/pipeline-runs")
async def api_pipeline_runs(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_pipeline_runs(settings.database_path)


@app.get("/api/dashboard/pending-newsletters")
async def api_pending_newsletters(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_pending_newsletters(settings.database_path, include_sent=True)


@app.delete("/api/dashboard/pending-newsletters/{newsletter_id}")
async def api_delete_pending_newsletter(
    newsletter_id: str,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err
    deleted = delete_pending_newsletter(settings.database_path, newsletter_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"ok": False, "message": "Newsletter not found or already sent"})
    return {"ok": True}


@app.post("/api/dashboard/pending-newsletters/{newsletter_id}/requeue")
async def api_requeue_newsletter(
    newsletter_id: str,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err
    requeued = requeue_newsletter(settings.database_path, newsletter_id)
    if not requeued:
        return JSONResponse(status_code=404, content={"ok": False, "message": "Newsletter not found or not in sent status"})
    return {"ok": True, "message": "Newsletter moved back to pending"}


class EditNewsletterRequest(BaseModel):
    edition_number: int
    edition_date: str


@app.patch("/api/dashboard/pending-newsletters/{newsletter_id}")
async def api_edit_pending_newsletter(
    newsletter_id: str,
    req: EditNewsletterRequest,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err
    newsletter = get_newsletter_by_id(settings.database_path, newsletter_id)
    if newsletter is None or newsletter["status"] != "pending":
        return JSONResponse(status_code=404, content={"ok": False, "message": "Newsletter not found or already sent"})
    try:
        data = json.loads(newsletter["json_data"])
    except (json.JSONDecodeError, TypeError):
        return JSONResponse(status_code=400, content={"ok": False, "message": "Newsletter has no valid JSON data"})
    new_html = render_html(data, req.edition_number, req.edition_date)
    updated = update_newsletter_html(settings.database_path, newsletter_id, new_html)
    if not updated:
        return JSONResponse(status_code=500, content={"ok": False, "message": "Failed to update newsletter"})
    return {"ok": True, "message": f"Updated to Edition #{req.edition_number}"}


@app.get("/api/dashboard/newsletter-history")
async def api_newsletter_history(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_history_entries(settings.database_path)


@app.delete("/api/dashboard/newsletter-history/{history_id}")
async def api_delete_history(
    history_id: int,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err
    deleted = delete_history_entry(settings.database_path, history_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"ok": False, "message": "History entry not found"})
    return {"ok": True}


class TriggerRequest(BaseModel):
    mode: str = "dry-run"


@app.post("/api/dashboard/trigger-pipeline")
async def trigger_pipeline(
    req: TriggerRequest | None = None,
    dashboard_token: str | None = Cookie(default=None),
):
    err = _require_auth(dashboard_token)
    if err:
        return err

    mode = (req.mode if req else "dry-run").strip().lower()
    allowed = {"dry-run", "preview", "send-pending"}
    if mode not in allowed:
        return JSONResponse(
            status_code=400,
            content={"ok": False, "message": f"Invalid mode. Choose from: {', '.join(sorted(allowed))}"},
        )

    if mode == "dry-run":
        kwargs: dict = {"dry_run": True}
    else:
        kwargs = {"mode": mode}

    t = threading.Thread(target=run_pipeline, kwargs=kwargs, daemon=True)
    t.start()
    return {"ok": True, "message": f"Pipeline triggered ({mode}). Check pipeline runs for progress."}


@app.get("/api/dashboard/db-diagnostic")
async def api_db_diagnostic(dashboard_token: str | None = Cookie(default=None)):
    err = _require_auth(dashboard_token)
    if err:
        return err
    return get_db_diagnostic(settings.database_path)
