"""Reachy command-line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .browser import check_browser, run_interactive_session
from .campaign import (
    CampaignError,
    CampaignWorker,
    approve_campaign,
    create_campaign,
    pause_campaign,
    preview_campaign,
    reconcile_campaign,
    resume_campaign,
    set_global_pause,
    start_campaign,
    stop_campaign,
)
from .config import ReachyConfig
from .agent import AutonomousOutreachAgent
from .copywriting import (
    STYLE_CATALOG,
    AICopyAgent,
    analyze_spam_risk,
    preview_styles_on_leads,
)
from .db import Database
from .health import compute_health, run_health_checks
from .ingest import discover_leads, import_file
from .logging_utils import setup_logging
from .normalize import normalize_email
from .oauth import GoogleOAuth, OAuthError, TokenCipher
from .providers.factory import build_provider, provider_check
from .replies import approve_reply_draft, list_reply_drafts, record_bounce, sync_replies
from .report import generate_daily_report, send_daily_report_email
from .sample_qc import approve_list, create_sample, record_review
from .scoring import ICPProfile, load_icp, save_icp
from .suppression import add_suppression, list_suppression, remove_suppression
from .tracking import calculate_open_stats, record_open_event
from .verify import DnspythonBackend, VerificationPolicy, verify_contacts
from .warmup import get_account_warmup_status, plan_warmup_batches


def main(argv: Optional[list[str]] = None) -> None:
    if argv is None:
        raw_argv = sys.argv[1:]
    else:
        raw_argv = list(argv)

    # Normalize position of global flags (--home, --json) so they can appear anywhere
    normalized_argv: list[str] = []
    global_args: list[str] = []
    i = 0
    while i < len(raw_argv):
        arg = raw_argv[i]
        if arg == "--home" and i + 1 < len(raw_argv):
            global_args.extend([arg, raw_argv[i + 1]])
            i += 2
        elif arg.startswith("--home="):
            global_args.append(arg)
            i += 1
        elif arg == "--json":
            global_args.append(arg)
            i += 1
        else:
            normalized_argv.append(arg)
            i += 1
    argv = global_args + normalized_argv

    parser = _parser()
    args = parser.parse_args(argv)
    config = ReachyConfig.load(home=args.home)
    config.ensure_home()
    setup_logging(config.log_path, json_logs=args.json)
    db = Database(config.db_path)
    db.migrate()
    try:
        exit_code = _dispatch(args, config, db)
    except (CampaignError, OAuthError, KeyError, ValueError, FileNotFoundError, RuntimeError) as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}))
        else:
            print(f"error: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        db.close()
    raise SystemExit(exit_code or 0)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="reachy", description="Reachy self-hosted B2B prospecting and outreach")
    parser.add_argument("--home", help="Reachy home directory (default: ~/.reachy)")
    parser.add_argument("--json", action="store_true", help="Emit JSON to stdout")
    parser.add_argument("--version", action="version", version=f"reachy {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create the database and run migrations")
    sub.add_parser("doctor", help="Run installation diagnostics").add_argument("--headed", action="store_true")
    pause = sub.add_parser("pause", help="Enable global pause")
    pause.add_argument("--resume", action="store_true", help="Disable global pause instead")

    icp = sub.add_parser("icp", help="Manage ICP profiles")
    icp_sub = icp.add_subparsers(dest="icp_command", required=True)
    icp_create = icp_sub.add_parser("create")
    icp_create.add_argument("--name", required=True)
    icp_create.add_argument("--file", help="JSON profile file")
    icp_create.add_argument("--industry", action="append", default=[])
    icp_create.add_argument("--state", action="append", default=[])
    icp_create.add_argument("--city", action="append", default=[])
    icp_create.add_argument("--min-reviews", type=int)
    icp_create.add_argument("--min-rating", type=float)
    icp_sub.add_parser("list")

    imp = sub.add_parser("import", help="Import a JSON/CSV lead file")
    imp.add_argument("--file", required=True)
    imp.add_argument("--source", default="import")
    imp.add_argument("--list", dest="list_name", required=True)
    imp.add_argument("--query", help="Original discovery query")
    imp.add_argument("--icp", help="ICP profile name")
    imp.add_argument("--no-verify", action="store_true")

    disc = sub.add_parser("discover", help="Run browser-assisted Google Maps discovery")
    disc.add_argument("query")
    disc.add_argument("--limit", type=int, default=10)
    disc.add_argument("--list", dest="list_name", required=True)
    disc.add_argument("--icp")
    disc.add_argument("--headed", action="store_true")
    disc.add_argument("--backend", default="auto", choices=["auto", "playwright", "agent-browser"])
    disc.add_argument("--no-enrich", action="store_true")
    disc.add_argument("--no-verify", action="store_true")

    leads = sub.add_parser("leads", help="Inspect leads")
    leads_sub = leads.add_subparsers(dest="leads_command", required=True)
    leads_list = leads_sub.add_parser("list")
    leads_list.add_argument("--list", dest="list_name")
    leads_list.add_argument("--limit", type=int, default=50)

    listing = sub.add_parser("list", help="Manage lead lists and sample QC")
    listing_sub = listing.add_subparsers(dest="list_command", required=True)
    l_create = listing_sub.add_parser("create")
    l_create.add_argument("--name", required=True)
    l_create.add_argument("--icp")
    l_sample = listing_sub.add_parser("sample")
    l_sample.add_argument("--list", dest="list_name", required=True)
    l_sample.add_argument("--size", type=int, default=10)
    l_sample.add_argument("--seed", type=int)
    l_sample.add_argument("--threshold", type=int, default=2)
    l_review = listing_sub.add_parser("review")
    l_review.add_argument("--review-id", type=int, required=True)
    l_review.add_argument("--incorrect", default="", help="1-based comma-separated sample indices")
    l_review.add_argument("--notes", default="")
    l_review.add_argument("--reviewer", default="user")
    l_approve = listing_sub.add_parser("approve")
    l_approve.add_argument("--list", dest="list_name", required=True)
    l_approve.add_argument("--reviewer", default="user")
    l_approve.add_argument("--notes", default="")
    listing_sub.add_parser("show").add_argument("--list", dest="list_name", required=True)

    accounts = sub.add_parser("accounts", help="Manage sending accounts")
    accounts_sub = accounts.add_subparsers(dest="accounts_command", required=True)
    a_smtp = accounts_sub.add_parser("add-smtp")
    a_smtp.add_argument("--email", required=True)
    a_smtp.add_argument("--host", required=True)
    a_smtp.add_argument("--port", type=int, default=587)
    a_smtp.add_argument("--username")
    a_smtp.add_argument("--imap-host")
    a_smtp.add_argument("--imap-port", type=int, default=993)
    a_smtp.add_argument("--display-name", default="")
    a_smtp.add_argument("--password-env", default="REACHY_SMTP_PASSWORD")
    a_smtp.add_argument("--daily-limit", type=int, default=10)
    a_smtp.add_argument("--permitted-use-acknowledged", action="store_true")
    a_gmail = accounts_sub.add_parser("add-gmail")
    a_gmail.add_argument("--email", required=True)
    a_gmail.add_argument("--client-secrets", default=None, help="Path to Google client_secrets.json (optional if set in .env)")
    a_gmail.add_argument("--client-id", default=None, help="Google OAuth 2.0 Client ID (or set REACHY_GOOGLE_CLIENT_ID in .env)")
    a_gmail.add_argument("--client-secret", default=None, help="Google OAuth 2.0 Client Secret (or set REACHY_GOOGLE_CLIENT_SECRET in .env)")
    a_gmail.add_argument("--display-name", default="")
    a_gmail.add_argument("--daily-limit", type=int, default=10)
    a_gmail.add_argument("--port", type=int, default=0)
    a_gmail.add_argument("--open-browser", action="store_true")
    a_gmail.add_argument("--permitted-use-acknowledged", action="store_true")
    a_mock = accounts_sub.add_parser("add-mock")
    a_mock.add_argument("--email", default="mock@reachy.invalid")
    a_mock.add_argument("--daily-limit", type=int, default=1000)
    accounts_sub.add_parser("list")
    a_check = accounts_sub.add_parser("check")
    a_check.add_argument("--id", type=int)
    a_disconnect = accounts_sub.add_parser("disconnect")
    a_disconnect.add_argument("--id", type=int, required=True)

    campaign = sub.add_parser("campaign", help="Create and run campaigns")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)
    c_create = campaign_sub.add_parser("create")
    c_create.add_argument("--name", required=True)
    c_create.add_argument("--list", dest="list_name", required=True)
    c_create.add_argument("--account", type=int)
    c_create.add_argument("--steps", required=True, help="JSON file: [{subject,body,delay_days}]")
    c_create.add_argument("--policy", help="JSON policy file")
    c_create.add_argument("--sender-identity", help="Real sender name and role")
    c_create.add_argument("--jurisdiction", default="US")
    c_create.add_argument("--test-send", action="store_true", help="Submit only to REACHY_TEST_RECIPIENT")
    c_create.add_argument("--live-send", action="store_true", help="Submit to real recipients (requires approval)")
    c_preview = campaign_sub.add_parser("preview")
    c_preview.add_argument("--id", type=int, required=True)
    c_preview.add_argument("--limit", type=int, default=3)
    c_approve = campaign_sub.add_parser("approve")
    c_approve.add_argument("--id", type=int, required=True)
    c_approve.add_argument("--by", required=True)
    c_approve.add_argument("--notes", default="")
    c_start = campaign_sub.add_parser("start")
    c_start.add_argument("--id", type=int, required=True)
    c_run = campaign_sub.add_parser("run")
    c_run.add_argument("--max", type=int, default=25)
    c_run.add_argument("--worker", default="worker")
    c_pause = campaign_sub.add_parser("pause")
    c_pause.add_argument("--id", type=int, required=True)
    c_resume = campaign_sub.add_parser("resume")
    c_resume.add_argument("--id", type=int, required=True)
    c_stop = campaign_sub.add_parser("stop")
    c_stop.add_argument("--id", type=int, required=True)
    c_reconcile = campaign_sub.add_parser("reconcile")
    c_reconcile.add_argument("--id", type=int, required=True)
    campaign_sub.add_parser("show").add_argument("--id", type=int, required=True)
    c_batches = campaign_sub.add_parser("plan-batches", help="Plan safe daily warmup batches with human jitter")
    c_batches.add_argument("--id", type=int, required=True, help="Campaign ID")
    c_batches.add_argument("--start-date", help="Start date (YYYY-MM-DD)")
    c_batches.add_argument("--no-skip-weekends", action="store_true", help="Include weekends")
    c_batches.add_argument("--start-hour", type=int, default=9, help="Window start hour UTC (default 9)")
    c_batches.add_argument("--end-hour", type=int, default=17, help="Window end hour UTC (default 17)")

    replies = sub.add_parser("replies", help="Reply synchronization and drafting")
    replies_sub = replies.add_subparsers(dest="replies_command", required=True)
    r_sync = replies_sub.add_parser("sync")
    r_sync.add_argument("--account", type=int, required=True)
    r_sync.add_argument("--days", type=int, default=7)
    replies_sub.add_parser("list").add_argument("--limit", type=int, default=50)
    replies_sub.add_parser("drafts")
    r_approve = replies_sub.add_parser("approve-draft")
    r_approve.add_argument("--id", type=int, required=True)
    r_approve.add_argument("--by", default="user")

    bounce = sub.add_parser("bounce", help="Record a bounce event")
    bounce.add_argument("--account", type=int, required=True)
    bounce.add_argument("--email", required=True)
    bounce.add_argument("--kind", choices=["hard", "soft"], default="hard")

    suppress = sub.add_parser("suppress", help="Global suppression list")
    suppress_sub = suppress.add_subparsers(dest="suppress_command", required=True)
    s_add = suppress_sub.add_parser("add")
    s_add.add_argument("--email", required=True)
    s_add.add_argument("--reason", choices=["manual", "legal", "unsubscribe", "complaint", "hard_bounce"], default="manual")
    s_add.add_argument("--notes", default="")
    s_remove = suppress_sub.add_parser("remove")
    s_remove.add_argument("--email", required=True)
    s_remove.add_argument(
        "--force", action="store_true",
        help="Required to remove unsubscribe, complaint, or legal suppressions after review",
    )
    suppress_sub.add_parser("list")

    health = sub.add_parser("health", help="Sender health report")
    health.add_argument("--account", type=int)
    health.add_argument("--days", type=int, default=14)
    health.add_argument("--check-provider", action="store_true")
    health.add_argument("--no-auto-pause", action="store_true")

    export = sub.add_parser("export", help="Export customer data")
    export.add_argument("--out", required=True)
    backup = sub.add_parser("backup", help="Back up the database")
    backup.add_argument("--out", required=True)
    restore = sub.add_parser("restore", help="Restore a database backup")
    restore.add_argument("--from", dest="source", required=True)
    audit = sub.add_parser("audit", help="Show audit log")
    audit.add_argument("--limit", type=int, default=100)

    browser = sub.add_parser("browser", help="Browser diagnostics and interactive worker")
    browser_sub = browser.add_subparsers(dest="browser_command", required=True)
    b_check = browser_sub.add_parser("check")
    b_check.add_argument("--headed", action="store_true")
    b_check.add_argument("--url")
    b_open = browser_sub.add_parser("open")
    b_open.add_argument("--url", required=True)

    # Copywriting, Sample Approval & AI Generation
    copy = sub.add_parser("copy", help="Copywriting styles, sample approval, AI copy generation, and spam score")
    copy_sub = copy.add_subparsers(dest="copy_command", required=True)
    copy_sub.add_parser("styles", help="List available conversion copy styles")
    cp_sample = copy_sub.add_parser("sample", help="Preview styles rendered on leads for approval")
    cp_sample.add_argument("--list", dest="list_name", required=True)
    cp_sample.add_argument("--limit", type=int, default=3)
    cp_sample.add_argument("--style", choices=list(STYLE_CATALOG.keys()))
    cp_gen = copy_sub.add_parser("generate", help="AI Agent writes tailored campaign steps")
    cp_gen.add_argument("--job", required=True, help="Job/campaign objective or role")
    cp_gen.add_argument("--industry", required=True, help="Target industry/category")
    cp_gen.add_argument("--value-prop", required=True, help="Core value proposition or offer")
    cp_gen.add_argument("--style", default="work_done_first", choices=list(STYLE_CATALOG.keys()))
    cp_gen.add_argument("--followups", type=int, default=2)
    cp_gen.add_argument("--out", help="Write steps to JSON file")
    cp_spam = copy_sub.add_parser("check-spam", help="Analyze copy for spam trigger words")
    cp_spam.add_argument("--subject")
    cp_spam.add_argument("--body")
    cp_spam.add_argument("--file", help="Path to campaign steps JSON file")

    # Warmup Status
    warmup = sub.add_parser("warmup", help="Inspect account warmup and safe limits")
    warmup_sub = warmup.add_subparsers(dest="warmup_command", required=True)
    w_status = warmup_sub.add_parser("status", help="Show warmup status and limits")
    w_status.add_argument("--account", type=int, help="Account ID")

    # Open Tracking & Bounce Telemetry
    tracking = sub.add_parser("tracking", help="Open rate telemetry and bounce monitoring")
    tracking_sub = tracking.add_subparsers(dest="tracking_command", required=True)
    tr_open = tracking_sub.add_parser("record-open", help="Record an email open event")
    tr_open.add_argument("--token", required=True, help="Tracking token or message ID")
    tr_open.add_argument("--user-agent", default="cli")
    tr_open.add_argument("--ip", default="127.0.0.1")
    tr_stats = tracking_sub.add_parser("stats", help="Compute open rates and stats")
    tr_stats.add_argument("--campaign", type=int, help="Campaign ID filter")
    tr_stats.add_argument("--account", type=int, help="Account ID filter")

    # Autonomous Outreach Agent Execution
    agent = sub.add_parser("agent", help="Autonomous outreach agent execution")
    agent_sub = agent.add_subparsers(dest="agent_command", required=True)
    ag_send = agent_sub.add_parser("send", help="Agent autonomous dispatch loop with safety gates")
    ag_send.add_argument("--campaign", type=int, help="Target campaign ID")
    ag_send.add_argument("--max", type=int, default=25, help="Max messages to send")
    ag_send.add_argument("--pace", type=float, default=0.0, help="Human pacing delay between sends in seconds")
    ag_send.add_argument("--no-sync", action="store_true", help="Skip post-send reply sync")

    # Outreach & Deliverability Reporting
    report = sub.add_parser("report", help="Outreach and deliverability reports")
    report_sub = report.add_subparsers(dest="report_command", required=True)
    rep_daily = report_sub.add_parser("daily", help="Generate 24-hour outreach and health report")
    rep_daily.add_argument("--date", help="Report date (YYYY-MM-DD)")
    rep_daily.add_argument("--account", type=int, help="Filter by account ID")
    rep_daily.add_argument("--email", help="Email report to this address")
    rep_daily.add_argument("--markdown", action="store_true", help="Print Markdown output")

    return parser


def _dispatch(args, config: ReachyConfig, db: Database) -> int:
    if args.command == "init":
        _out(args, {"ok": True, "home": str(config.home), "database": str(config.db_path), "schema_version": db.schema_version()})
        return 0
    if args.command == "doctor":
        return _doctor(args, config, db)
    if args.command == "pause":
        set_global_pause(db, not args.resume)
        _out(args, {"global_pause": not args.resume})
        return 0
    if args.command == "icp":
        return _icp(args, db)
    if args.command == "import":
        return _import(args, config, db)
    if args.command == "discover":
        return _discover(args, config, db)
    if args.command == "leads":
        return _leads(args, db)
    if args.command == "list":
        return _list(args, db)
    if args.command == "accounts":
        return _accounts(args, config, db)
    if args.command == "campaign":
        return _campaign(args, config, db)
    if args.command == "replies":
        return _replies(args, config, db)
    if args.command == "bounce":
        _out(args, record_bounce(db, args.account, args.email, kind=args.kind))
        return 0
    if args.command == "suppress":
        return _suppress(args, db)
    if args.command == "health":
        return _health(args, config, db)
    if args.command == "export":
        return _export(args, db)
    if args.command == "backup":
        path = db.backup(args.out)
        _out(args, {"ok": True, "backup": str(path)})
        return 0
    if args.command == "restore":
        if os.path.exists(config.db_path):
            raise RuntimeError("stop the worker and move the current database aside before restoring")
        Database.restore(args.source, config.db_path)
        _out(args, {"ok": True, "restored": str(config.db_path)})
        return 0
    if args.command == "audit":
        rows = db.fetchall("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (args.limit,))
        _out(args, [dict(row) for row in rows])
        return 0
    if args.command == "browser":
        if args.browser_command == "check":
            report = check_browser(headless=not args.headed, target_url=args.url)
            _out(args, report.as_dict())
            return 0 if report.success else 1
        run_interactive_session(args.url)
        return 0
    if args.command == "copy":
        return _copy(args, db)
    if args.command == "warmup":
        return _warmup(args, db)
    if args.command == "tracking":
        return _tracking(args, db)
    if args.command == "agent":
        return _agent(args, config, db)
    if args.command == "report":
        return _report(args, config, db)
    return 1


def _doctor(args, config: ReachyConfig, db: Database) -> int:
    report: dict[str, Any] = {
        "version": __version__,
        "python": sys.version.split()[0],
        "home": str(config.home),
        "database": str(config.db_path),
        "schema_version": db.schema_version(),
        "secret_key_source": "env" if os.environ.get("REACHY_SECRET_KEY") else str(config.secret_key_path),
        "test_recipient_configured": bool(config.test_recipient),
        "global_pause": db.get_setting("global_pause", "0") == "1",
        "browser": check_browser(headless=not args.headed).as_dict(),
    }
    accounts = db.fetchall("SELECT * FROM accounts ORDER BY id")
    report["accounts"] = [
        {"id": row["id"], "email": row["email"], "provider": row["provider"], "status": row["status"]}
        for row in accounts
    ]
    _out(args, report)
    return 0


def _icp(args, db: Database) -> int:
    if args.icp_command == "list":
        rows = db.fetchall("SELECT id, name, updated_at FROM icp_profiles ORDER BY id")
        _out(args, [dict(row) for row in rows])
        return 0
    if args.file:
        data = _load_json(args.file)
        icp = ICPProfile.from_dict(data)
        icp.name = args.name
    else:
        icp = ICPProfile(
            name=args.name,
            industries=args.industry,
            states=[state.upper() for state in args.state],
            cities=args.city,
            min_reviews=args.min_reviews,
            min_rating=args.min_rating,
        )
    icp_id = save_icp(db, icp)
    _out(args, {"ok": True, "icp_id": icp_id, "name": icp.name})
    return 0


def _resolve_icp(db: Database, name: Optional[str]):
    if not name:
        return None, None
    found = load_icp(db, name)
    if not found:
        raise KeyError(f"ICP profile not found: {name}")
    return found[0], found[1]


def _import(args, config: ReachyConfig, db: Database) -> int:
    icp_id, icp = _resolve_icp(db, args.icp)
    policy = VerificationPolicy(allow_catch_all=config.allow_catch_all, smtp_probe_enabled=config.catch_all_probe_enabled)
    stats = import_file(
        db,
        args.file,
        source=args.source,
        list_name=args.list_name,
        source_query=args.query,
        icp=icp,
        icp_profile_id=icp_id,
        verify=not args.no_verify,
        dns_backend=DnspythonBackend() if not args.no_verify else None,
        verification_policy=policy,
    )
    _out(args, {"ok": True, **stats})
    return 0


def _discover(args, config: ReachyConfig, db: Database) -> int:
    records = discover_leads(
        args.query, limit=args.limit, headed=args.headed, backend=args.backend, enrich=not args.no_enrich
    )
    icp_id, icp = _resolve_icp(db, args.icp)
    from .ingest import import_records

    policy = VerificationPolicy(allow_catch_all=config.allow_catch_all, smtp_probe_enabled=config.catch_all_probe_enabled)
    stats = import_records(
        db,
        records,
        source="google_maps",
        list_name=args.list_name,
        source_query=args.query,
        icp=icp,
        icp_profile_id=icp_id,
        verify=not args.no_verify,
        dns_backend=DnspythonBackend() if not args.no_verify else None,
        verification_policy=policy,
    )
    _out(args, {"ok": True, **stats})
    return 0


def _leads(args, db: Database) -> int:
    if args.list_name:
        rows = db.fetchall(
            """SELECT l.id, l.name, l.category, l.city, l.state, l.website, l.phone,
                      l.qualification_score, l.qualification_reason, l.flags_json,
                      c.email, c.verification_status
               FROM leads l JOIN list_leads ll ON ll.lead_id=l.id
               LEFT JOIN contacts c ON c.lead_id=l.id AND c.is_primary=1
               WHERE ll.list_id=(SELECT id FROM lists WHERE name=?)
               ORDER BY l.qualification_score DESC, l.id LIMIT ?""",
            (args.list_name, args.limit),
        )
    else:
        rows = db.fetchall(
            """SELECT l.*, c.email, c.verification_status FROM leads l
               LEFT JOIN contacts c ON c.lead_id=l.id AND c.is_primary=1
               ORDER BY l.id DESC LIMIT ?""",
            (args.limit,),
        )
    _out(args, [dict(row) for row in rows])
    return 0


def _get_list(db: Database, name: str) -> dict[str, Any]:
    row = db.fetchone("SELECT * FROM lists WHERE name = ?", (name,))
    if not row:
        raise KeyError(f"list not found: {name}")
    return dict(row)


def _list(args, db: Database) -> int:
    if args.list_command == "create":
        from .ingest import ensure_list

        icp_id, _ = _resolve_icp(db, args.icp)
        list_id = ensure_list(db, args.name, icp_id)
        _out(args, {"ok": True, "list_id": list_id, "name": args.name})
        return 0
    if args.list_command == "sample":
        listing = _get_list(db, args.list_name)
        result = create_sample(db, int(listing["id"]), size=args.size, seed=args.seed, threshold=args.threshold)
        _out(args, {"ok": True, **result})
        return 0
    if args.list_command == "review":
        indices = [int(part) for part in args.incorrect.split(",") if part.strip()]
        result = record_review(db, args.review_id, indices, notes=args.notes, reviewer=args.reviewer)
        _out(args, {"ok": True, **result})
        return 0
    if args.list_command == "approve":
        listing = _get_list(db, args.list_name)
        result = approve_list(db, int(listing["id"]), args.reviewer, notes=args.notes)
        _out(args, {"ok": True, **result})
        return 0
    if args.list_command == "show":
        listing = _get_list(db, args.list_name)
        review = db.fetchone(
            "SELECT * FROM sample_reviews WHERE list_id=? ORDER BY id DESC LIMIT 1", (listing["id"],)
        )
        approval = db.fetchone("SELECT * FROM list_approvals WHERE list_id=?", (listing["id"],))
        _out(
            args,
            {
                "list": listing,
                "latest_sample": dict(review) if review else None,
                "approval": dict(approval) if approval else None,
            },
        )
        return 0
    return 1


def _cipher(config: ReachyConfig) -> TokenCipher:
    return TokenCipher(key_path=config.secret_key_path)


def _accounts(args, config: ReachyConfig, db: Database) -> int:
    from .db import utcnow
    from .oauth import TokenStore

    if args.accounts_command == "list":
        rows = db.fetchall("SELECT * FROM accounts ORDER BY id")
        _out(args, [{k: row[k] for k in row.keys() if k != "config_json"} for row in rows])
        return 0
    if args.accounts_command == "add-mock":
        now = utcnow()
        account_id = db.insert(
            """INSERT INTO accounts(email, display_name, provider, config_json, status, daily_limit,
                   authorized_at, created_at, updated_at)
               VALUES (?, ?, 'mock', ?, 'ACTIVE', ?, ?, ?, ?)""",
            (
                args.email, "Mock Sender",
                json.dumps({"permitted_use_acknowledged_at": now, "display_name": "Mock Sender"}),
                args.daily_limit, now, now, now,
            ),
        )
        db.audit("user", "account.created", "account", account_id, {"provider": "mock"})
        _out(args, {"ok": True, "account_id": account_id, "provider": "mock"})
        return 0
    if args.accounts_command == "add-smtp":
        password = os.environ.get(args.password_env)
        if not password:
            password = getpass.getpass(f"SMTP password for {args.email}: ")
        now = utcnow()
        config_json = {
            "host": args.host,
            "port": args.port,
            "username": args.username or args.email,
            "imap_host": args.imap_host,
            "imap_port": args.imap_port,
            "display_name": args.display_name,
            "permitted_use_acknowledged_at": now if args.permitted_use_acknowledged else None,
        }
        account_id = db.insert(
            """INSERT INTO accounts(email, display_name, provider, config_json, status, daily_limit,
                   authorized_at, created_at, updated_at)
               VALUES (?, ?, 'smtp', ?, ?, ?, ?, ?, ?)""",
            (args.email, args.display_name, json.dumps(config_json), "ACTIVE", args.daily_limit, now, now, now),
        )
        TokenStore(db).store(account_id, {"password": password}, _cipher(config))
        db.audit("user", "account.created", "account", account_id, {"provider": "smtp"})
        _out(args, {"ok": True, "account_id": account_id, "provider": "smtp"})
        return 0
    if args.accounts_command == "add-gmail":
        now = utcnow()
        config_json = {
            "display_name": args.display_name,
            "permitted_use_acknowledged_at": now if args.permitted_use_acknowledged else None,
        }
        account_id = db.insert(
            """INSERT INTO accounts(email, display_name, provider, config_json, scopes, status,
                   daily_limit, created_at, updated_at)
               VALUES (?, ?, 'gmail', ?, ?, 'PENDING_AUTH', ?, ?, ?)""",
            (
                args.email, args.display_name, json.dumps(config_json),
                "https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.readonly",
                args.daily_limit, now, now,
            ),
        )
        oauth = GoogleOAuth(_cipher(config))
        oauth.authorize(
            db,
            account_id,
            client_secrets_path=args.client_secrets,
            client_id=args.client_id,
            client_secret=args.client_secret,
            port=args.port,
            open_browser=args.open_browser,
        )
        db.execute(
            "UPDATE accounts SET status='ACTIVE', authorized_at=?, updated_at=? WHERE id=?",
            (utcnow(), utcnow(), account_id),
        )
        db.audit("user", "account.authorized", "account", account_id, {"provider": "gmail"})
        _out(args, {"ok": True, "account_id": account_id, "provider": "gmail"})
        return 0
    if args.accounts_command == "check":
        rows = db.fetchall("SELECT * FROM accounts ORDER BY id")
        results = []
        for row in rows:
            account = dict(row)
            if args.id and int(row["id"]) != args.id:
                continue
            ok, detail = provider_check(db, account, cipher=_cipher(config), oauth=GoogleOAuth(_cipher(config)))
            results.append({"id": row["id"], "email": row["email"], "ok": ok, "detail": detail})
        _out(args, results)
        return 0 if all(item["ok"] for item in results) else 1
    if args.accounts_command == "disconnect":
        account = db.fetchone("SELECT * FROM accounts WHERE id=?", (args.id,))
        if not account:
            raise KeyError(f"account {args.id} not found")
        if account["provider"] == "gmail":
            GoogleOAuth(_cipher(config)).disconnect(db, args.id)
        else:
            TokenStore(db).delete(args.id)
            db.execute(
                "UPDATE accounts SET status='REVOKED', revoked_at=?, updated_at=? WHERE id=?",
                (utcnow(), utcnow(), args.id),
            )
            db.audit("user", "account.disconnected", "account", args.id, {"provider": account["provider"]})
        _out(args, {"ok": True, "account_id": args.id, "status": "REVOKED"})
        return 0
    return 1


def _campaign(args, config: ReachyConfig, db: Database) -> int:
    cipher = _cipher(config)
    oauth = GoogleOAuth(cipher)
    factory = lambda account: build_provider(db, account, cipher=cipher, oauth=oauth)  # noqa: E731

    if args.campaign_command == "create":
        if args.test_send and args.live_send:
            raise ValueError("choose either --test-send or --live-send")
        listing = _get_list(db, args.list_name)
        steps = _load_json(args.steps)
        if not isinstance(steps, list):
            raise ValueError("--steps must contain a JSON list")
        policy = _load_json(args.policy) if args.policy else {}
        policy.setdefault("jurisdiction", args.jurisdiction)
        campaign_id = create_campaign(
            db,
            args.name,
            int(listing["id"]),
            steps,
            account_id=args.account,
            policy=policy,
            test_mode=not args.live_send,
            dry_run=not (args.test_send or args.live_send),
            sender_identity=args.sender_identity,
            target_jurisdiction=args.jurisdiction,
        )
        _out(args, {"ok": True, "campaign_id": campaign_id, "status": "DRAFT"})
        return 0
    if args.campaign_command == "preview":
        _out(args, preview_campaign(db, args.id, limit=args.limit))
        return 0
    if args.campaign_command == "approve":
        _out(args, approve_campaign(db, args.id, args.by, notes=args.notes, config=config))
        return 0
    if args.campaign_command == "start":
        _out(args, start_campaign(db, args.id, config))
        return 0
    if args.campaign_command == "run":
        worker = CampaignWorker(db, config, factory, worker_id=args.worker)
        _out(args, worker.run_once(max_messages=args.max))
        return 0
    if args.campaign_command == "pause":
        pause_campaign(db, args.id)
        _out(args, {"ok": True, "campaign_id": args.id, "status": "PAUSED"})
        return 0
    if args.campaign_command == "resume":
        resume_campaign(db, args.id)
        _out(args, {"ok": True, "campaign_id": args.id, "status": "RUNNING"})
        return 0
    if args.campaign_command == "stop":
        stop_campaign(db, args.id)
        _out(args, {"ok": True, "campaign_id": args.id, "status": "STOPPED"})
        return 0
    if args.campaign_command == "reconcile":
        _out(args, reconcile_campaign(db, args.id, factory, config))
        return 0
    if args.campaign_command == "show":
        campaign = db.fetchone("SELECT * FROM campaigns WHERE id=?", (args.id,))
        if not campaign:
            raise KeyError(f"campaign {args.id} not found")
        steps = db.fetchall("SELECT * FROM campaign_steps WHERE campaign_id=? ORDER BY step_number", (args.id,))
        counts = db.fetchall("SELECT state, COUNT(*) AS c FROM messages WHERE campaign_id=? GROUP BY state", (args.id,))
        _out(args, {"campaign": dict(campaign), "steps": [dict(s) for s in steps], "messages": {r["state"]: r["c"] for r in counts}})
        return 0
    if args.campaign_command == "plan-batches":
        from .models import parse_iso
        start_d = parse_iso(args.start_date).date() if args.start_date else None
        plan = plan_warmup_batches(
            db,
            args.id,
            start_date=start_d,
            skip_weekends=not args.no_skip_weekends,
            business_start_hour=args.start_hour,
            business_end_hour=args.end_hour,
        )
        _out(args, plan)
        return 0
    return 1


def _replies(args, config: ReachyConfig, db: Database) -> int:
    if args.replies_command == "list":
        rows = db.fetchall("SELECT * FROM replies ORDER BY id DESC LIMIT ?", (args.limit,))
        _out(args, [dict(row) for row in rows])
        return 0
    if args.replies_command == "drafts":
        _out(args, list_reply_drafts(db))
        return 0
    if args.replies_command == "approve-draft":
        _out(args, approve_reply_draft(db, args.id, args.by))
        return 0
    if args.replies_command == "sync":
        account = db.fetchone("SELECT * FROM accounts WHERE id=?", (args.account,))
        if not account:
            raise KeyError(f"account {args.account} not found")
        cipher = _cipher(config)
        provider = build_provider(db, dict(account), cipher=cipher, oauth=GoogleOAuth(cipher))
        try:
            since = datetime.now(timezone.utc) - timedelta(days=args.days)
            _out(args, sync_replies(db, args.account, provider, since=since))
        finally:
            provider.close()
        return 0
    return 1


def _suppress(args, db: Database) -> int:
    if args.suppress_command == "list":
        _out(args, list_suppression(db))
        return 0
    if args.suppress_command == "add":
        added = add_suppression(db, args.email, args.reason, source="cli", notes=args.notes, actor="user")
        _out(args, {"ok": True, "added": added, "email": normalize_email(args.email), "reason": args.reason})
        return 0
    if args.suppress_command == "remove":
        _out(
            args,
            {"ok": remove_suppression(db, args.email, actor="user", force=args.force)},
        )
        return 0
    return 1


def _health(args, config: ReachyConfig, db: Database) -> int:
    cipher = _cipher(config)
    oauth = GoogleOAuth(cipher)

    def checker(account):
        return provider_check(db, account, cipher=cipher, oauth=oauth) if args.check_provider else (True, "not checked")

    if args.account:
        account = db.fetchone("SELECT * FROM accounts WHERE id=?", (args.account,))
        if not account:
            raise KeyError(f"account {args.account} not found")
        report = compute_health(
            db, args.account, days=args.days,
            provider_check=(lambda: checker(dict(account))) if args.check_provider else None,
        )
        _out(args, report.as_dict())
        return 0
    reports = run_health_checks(
        db, days=args.days, auto_pause=not args.no_auto_pause,
        provider_checker=checker, actor="health_check",
    )
    _out(args, [report.as_dict() for report in reports])
    return 0


def _copy(args, db: Database) -> int:
    if args.copy_command == "styles":
        _out(args, [s.as_dict() for s in STYLE_CATALOG.values()])
        return 0
    if args.copy_command == "sample":
        list_row = _get_list(db, args.list_name)
        preview = preview_styles_on_leads(db, int(list_row["id"]), limit=args.limit)
        if args.style:
            preview["styles"] = [s for s in preview["styles"] if s["id"] == args.style]
            preview["samples"] = {args.style: preview["samples"].get(args.style, [])}
        _out(args, preview)
        return 0
    if args.copy_command == "generate":
        agent = AICopyAgent()
        steps = agent.generate_campaign_steps(
            job_description=args.job,
            target_industry=args.industry,
            value_proposition=args.value_prop,
            style_id=args.style,
            num_followups=args.followups,
        )
        if args.out:
            dest = Path(args.out).expanduser()
            dest.write_text(json.dumps(steps, indent=2), encoding="utf-8")
        _out(args, {"ok": True, "style": args.style, "steps": steps, "out": str(args.out) if args.out else None})
        return 0
    if args.copy_command == "check-spam":
        if args.file:
            steps_data = _load_json(args.file)
            results = []
            for i, st in enumerate(steps_data, 1):
                sub = st.get("subject", "")
                body = st.get("body", "")
                analysis = analyze_spam_risk(sub, body)
                results.append({"step": i, "subject": sub, "spam_analysis": analysis.as_dict()})
            _out(args, results)
            return 0
        if not args.subject or not args.body:
            raise ValueError("provide either --file or both --subject and --body")
        analysis = analyze_spam_risk(args.subject, args.body)
        _out(args, analysis.as_dict())
        return 0
    return 1


def _warmup(args, db: Database) -> int:
    if args.warmup_command == "status":
        if args.account:
            status = get_account_warmup_status(db, args.account)
            _out(args, status.as_dict())
            return 0
        accounts = db.fetchall("SELECT id FROM accounts WHERE status != 'REVOKED' ORDER BY id")
        statuses = [get_account_warmup_status(db, int(acc["id"])).as_dict() for acc in accounts]
        _out(args, statuses)
        return 0
    return 1


def _tracking(args, db: Database) -> int:
    if args.tracking_command == "record-open":
        res = record_open_event(db, args.token, user_agent=args.user_agent, ip_address=args.ip)
        _out(args, res)
        return 0
    if args.tracking_command == "stats":
        stats = calculate_open_stats(db, campaign_id=args.campaign, account_id=args.account)
        _out(args, stats)
        return 0
    return 1


def _agent(args, config: ReachyConfig, db: Database) -> int:
    if args.agent_command == "send":
        cipher = _cipher(config)
        oauth = GoogleOAuth(cipher)
        factory = lambda account: build_provider(db, account, cipher=cipher, oauth=oauth)  # noqa: E731
        agent = AutonomousOutreachAgent(db, config, factory)
        result = agent.execute_sends(
            campaign_id=args.campaign,
            max_messages=args.max,
            pace_seconds=args.pace,
            sync_after=not args.no_sync,
        )
        _out(args, result)
        return 0 if result.get("ok", False) else 1
    return 1


def _report(args, config: ReachyConfig, db: Database) -> int:
    if args.report_command == "daily":
        from .models import parse_iso

        target_date = parse_iso(args.date).date() if args.date else None
        report_data = generate_daily_report(db, target_date=target_date, account_id=args.account)
        if args.email:
            cipher = _cipher(config)
            oauth = GoogleOAuth(cipher)
            factory = lambda account: build_provider(db, account, cipher=cipher, oauth=oauth)  # noqa: E731
            dispatch = send_daily_report_email(
                db, args.email, report_data, account_id=args.account, provider_factory=factory
            )
            _out(args, {"report": report_data.as_dict(), "email_dispatch": dispatch})
            return 0
        if args.markdown:
            print(report_data.format_markdown())
            return 0
        _out(args, report_data.as_dict())
        return 0
    return 1


def _export(args, db: Database) -> int:
    tables = [
        "leads", "contacts", "lists", "list_leads", "sample_reviews", "list_approvals",
        "campaigns", "campaign_steps", "messages", "message_events", "replies",
        "reply_drafts", "suppression", "accounts", "audit_log",
    ]
    payload: dict[str, Any] = {"exported_at": datetime.now(timezone.utc).isoformat(), "tables": {}}
    for table in tables:
        rows = db.fetchall(f"SELECT * FROM {table}")
        data = []
        for row in rows:
            item = dict(row)
            if table == "accounts":
                item.pop("config_json", None)
                item.pop("scopes", None)
            data.append(item)
        payload["tables"][table] = data
    destination = Path(args.out).expanduser()
    destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    _out(args, {"ok": True, "export": str(destination), "tables": {k: len(v) for k, v in payload["tables"].items()}})
    return 0


def _load_json(path: str) -> Any:
    return json.loads(Path(path).expanduser().read_text(encoding="utf-8"))


def _out(args, payload: Any) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
        return
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(payload)


if __name__ == "__main__":
    main()
