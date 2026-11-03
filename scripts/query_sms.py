"""Read this machine's SMS forwarder database and return message text.

The database is filled by uart_sms_forwarder from a Luat Air780 module.
This tool only reads sqlite. It does not choose which message matters.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TZ = timezone(timedelta(hours=8))
SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(r"E:\re_sms\dist\uart_sms_forwarder-windows-amd64\data\app.db")
CODE_RE = re.compile(r"验证码(?:为|是)?\s*[:：]?\s*(\d{4,8})")


def emit(payload: dict, code: int) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(code)


def redact_codes(content: str) -> str:
    return CODE_RE.sub(lambda m: f"<{len(m.group(1))}位验证码>", content or "")


def load_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("SMS_DB")
    if env:
        return Path(env)
    local = SKILL_ROOT / "config.local.json"
    if local.is_file():
        data = json.loads(local.read_text(encoding="utf-8"))
        configured = data.get("database")
        if configured:
            return Path(configured)
    return DEFAULT_DB


def to_epoch_seconds(value: int | None) -> float | None:
    if not value:
        return None
    if value > 10_000_000_000:
        return value / 1000
    return float(value)


def iso_time(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, TZ).isoformat(timespec="seconds")


def connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SMS database not found: {path}")
    uri = path.resolve().as_posix()
    con = sqlite3.connect(f"file:{uri}?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    return con


def like_pattern(needle: str) -> str:
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def row_payload(row: sqlite3.Row, *, redact: bool) -> dict:
    content = row["content"] or ""
    created = to_epoch_seconds(row["created_at"])
    return {
        "id": row["id"],
        "from": row["from"],
        "to": row["to"],
        "content": redact_codes(content) if redact else content,
        "type": row["type"],
        "status": row["status"],
        "created_at": iso_time(created),
        "age_seconds": int(time.time() - created) if created is not None else None,
    }


def fetch_messages(
    con: sqlite3.Connection,
    *,
    query: str | None,
    within_seconds: float | None,
    newer_than: float | None,
    limit: int,
    incoming_only: bool,
) -> list[sqlite3.Row]:
    sql = [
        'SELECT id, "from", "to", content, type, status, created_at',
        "FROM text_messages",
        "WHERE 1 = 1",
    ]
    params: list[object] = []
    if incoming_only:
        sql.append("AND type = 'incoming'")
    if query:
        sql.append("AND content LIKE ? ESCAPE '\\'")
        params.append(like_pattern(query))
    sql.append("ORDER BY created_at DESC, rowid DESC")
    rows = con.execute(" ".join(sql), params).fetchall()
    selected: list[sqlite3.Row] = []
    now = time.time()
    for row in rows:
        created = to_epoch_seconds(row["created_at"])
        if created is None:
            continue
        if newer_than is not None and created < newer_than:
            continue
        if within_seconds is not None and within_seconds > 0 and (now - created) > within_seconds:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def status_payload(path: Path) -> dict:
    con = connect(path)
    try:
        incoming = con.execute(
            "SELECT COUNT(*) FROM text_messages WHERE type = 'incoming'"
        ).fetchone()[0]
        newest = con.execute(
            "SELECT created_at FROM text_messages WHERE type = 'incoming' "
            "ORDER BY created_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    created = to_epoch_seconds(newest["created_at"]) if newest else None
    ui_open = False
    try:
        import socket

        with socket.create_connection(("127.0.0.1", 8080), timeout=0.4):
            ui_open = True
    except OSError:
        ui_open = False
    return {
        "ok": True,
        "database": str(path),
        "incoming": incoming,
        "newest_incoming_at": iso_time(created),
        "newest_age_seconds": int(time.time() - created) if created else None,
        "ui": "127.0.0.1:8080",
        "ui_open": ui_open,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read recent SMS from the local forwarder database.")
    parser.add_argument("--db", help="sqlite path. Overrides SMS_DB and config.local.json.")
    parser.add_argument("--query", help="optional substring. The caller decides what to search.")
    parser.add_argument("--within", type=float, default=0, help="max age in minutes. 0 means no limit.")
    parser.add_argument("--recent", type=int, default=20, help="how many messages to return.")
    parser.add_argument("--wait", type=float, default=0, help="poll up to N seconds for a match.")
    parser.add_argument("--fresh", action="store_true", help="with --wait, only messages stored after startup.")
    parser.add_argument("--all-types", action="store_true", help="include outgoing messages.")
    parser.add_argument("--redact", action="store_true", help="hide digit runs that follow 验证码.")
    parser.add_argument("--status", action="store_true", help="show database freshness without message text.")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        path = load_db_path(args.db)
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        emit({"ok": False, "error": "config", "message": str(exc)}, 1)

    if args.status:
        try:
            emit(status_payload(path), 0)
        except (OSError, sqlite3.Error) as exc:
            emit({"ok": False, "error": "database", "message": str(exc), "database": str(path)}, 1)

    if args.recent < 1:
        emit({"ok": False, "error": "limit", "message": "--recent must be >= 1"}, 1)
    if args.fresh and args.wait <= 0:
        emit({"ok": False, "error": "fresh", "message": "--fresh requires --wait seconds."}, 1)

    within = None if args.within == 0 else args.within * 60
    started = time.time()
    deadline = started + max(args.wait, 0)
    newer_than = started if args.fresh else None

    try:
        while True:
            con = connect(path)
            try:
                rows = fetch_messages(
                    con,
                    query=args.query,
                    within_seconds=within,
                    newer_than=newer_than,
                    limit=args.recent,
                    incoming_only=not args.all_types,
                )
            finally:
                con.close()
            if rows or time.time() >= deadline:
                break
            time.sleep(2)
    except (OSError, sqlite3.Error) as exc:
        emit({"ok": False, "error": "database", "message": str(exc), "database": str(path)}, 1)

    messages = [row_payload(row, redact=args.redact) for row in rows]
    if not messages:
        emit(
            {
                "ok": False,
                "error": "not_found",
                "query": args.query,
                "within_minutes": args.within,
                "fresh": args.fresh,
                "database": str(path),
                "message": "No SMS in the requested window.",
            },
            2,
        )
    emit(
        {
            "ok": True,
            "query": args.query,
            "database": str(path),
            "messages": messages,
        },
        0,
    )


if __name__ == "__main__":
    main()
