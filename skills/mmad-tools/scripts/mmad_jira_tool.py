#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["jira", "httpx"]
# ///
"""Standalone Jira CLI.

Read and write access to Jira issues, comments, attachments and projects.
Self-contained: depends only on the `jira` Python package (`pip install jira`)
and reads credentials from environment variables.

Environment:
    JIRA_SERVER / JIRA_URL     Jira base URL, e.g. https://jira.example.com
    JIRA_USERNAME / JIRA_USER  username
    JIRA_PASSWORD              password or API token

Usage (read):
    uv run mmad_jira_tool.py search "project = FOO AND status = Open" --max-results 20
    uv run mmad_jira_tool.py get FOO-123
    uv run mmad_jira_tool.py comments FOO-123
    uv run mmad_jira_tool.py links FOO-123
    uv run mmad_jira_tool.py changelog FOO-123
    uv run mmad_jira_tool.py watchers FOO-123
    uv run mmad_jira_tool.py attachments FOO-123
    uv run mmad_jira_tool.py download-attachment 45678 --save-path ./out.zip
    uv run mmad_jira_tool.py transitions FOO-123
    uv run mmad_jira_tool.py projects
    uv run mmad_jira_tool.py setup FOO-123       # build an analysis workspace in CWD
    uv run mmad_jira_tool.py health

Usage (write):
    uv run mmad_jira_tool.py add-comment FOO-123 "Root cause: ..."
    uv run mmad_jira_tool.py do-transition FOO-123 "In Progress"
    uv run mmad_jira_tool.py assign FOO-123 jdoe          # use "-" to unassign

All results are printed as JSON to stdout; diagnostics go to stderr.
The `setup` subcommand instead writes files into the current directory and
prints a human-readable status line.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TAG = "jira"


def log(msg: str) -> None:
    print(f"[{TAG}] {msg}", file=sys.stderr)


def fail(msg: str, code: int = 1) -> "Any":
    print(f"[{TAG}] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return ""


def _settings() -> tuple[str, str, str]:
    server = _env("JIRA_SERVER", "JIRA_URL")
    username = _env("JIRA_USERNAME", "JIRA_USER")
    password = _env("JIRA_PASSWORD")
    if not server:
        fail("missing required setting: set JIRA_SERVER (or JIRA_URL)")
    if not username:
        fail("missing required setting: set JIRA_USERNAME (or JIRA_USER)")
    if not password:
        fail("missing required setting: set JIRA_PASSWORD")
    return server.rstrip("/"), username, password


def _client():
    try:
        from jira import JIRA
    except ImportError:
        fail("missing dependency: run `pip install jira` first")
    server, username, password = _settings()
    try:
        return JIRA(server=server, basic_auth=(username, password))
    except Exception as exc:  # noqa: BLE001 - surface auth/connection failures
        fail(f"failed to connect to Jira: {exc}")


def _issue_to_dict(issue: Any) -> dict[str, Any]:
    f = issue.fields
    return {
        "key": issue.key,
        "summary": getattr(f, "summary", None),
        "status": str(getattr(f, "status", None)),
        "issue_type": str(getattr(f, "issuetype", None)),
        "priority": str(getattr(f, "priority", None)),
        "assignee": str(getattr(f, "assignee", None)),
        "reporter": str(getattr(f, "reporter", None)),
        "created": str(getattr(f, "created", None)),
        "updated": str(getattr(f, "updated", None)),
        "description": getattr(f, "description", None),
        "labels": getattr(f, "labels", []),
        "components": [str(c) for c in getattr(f, "components", [])],
        "fix_versions": [str(v) for v in getattr(f, "fixVersions", [])],
    }


def _normalize_fields(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, str):
        raw = value.strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = [part.strip() for part in raw.split(",")]
        value = parsed
    if isinstance(value, list):
        aliases = {"issueType": "issuetype", "issue_type": "issuetype"}
        fields = [aliases.get(str(x), str(x)) for x in value if str(x).strip()]
        return ",".join(fields) if fields else None
    return str(value)


def cmd_search(args: argparse.Namespace) -> None:
    jira = _client()
    fields = _normalize_fields(args.fields)
    issues = jira.search_issues(args.jql, maxResults=args.max_results, fields=fields)
    result = [_issue_to_dict(i) for i in issues]
    emit({"total": len(result), "issues": result})


def cmd_get(args: argparse.Namespace) -> None:
    jira = _client()
    emit(_issue_to_dict(jira.issue(str(args.issue_key))))


def cmd_transitions(args: argparse.Namespace) -> None:
    jira = _client()
    transitions = jira.transitions(str(args.issue_key))
    emit([{"id": t["id"], "name": t["name"]} for t in transitions])


def cmd_projects(args: argparse.Namespace) -> None:
    jira = _client()
    emit([{"key": p.key, "name": p.name} for p in jira.projects()])


def cmd_comments(args: argparse.Namespace) -> None:
    jira = _client()
    comments = jira.comments(str(args.issue_key))
    emit(
        [
            {
                "id": c.id,
                "author": str(c.author),
                "created": str(c.created),
                "body": c.body,
            }
            for c in comments
        ]
    )


def cmd_links(args: argparse.Namespace) -> None:
    jira = _client()
    issue = jira.issue(str(args.issue_key), fields="issuelinks,subtasks,parent")
    f = issue.fields
    links: list[dict[str, Any]] = []
    for link in getattr(f, "issuelinks", []) or []:
        link_type = getattr(link, "type", None)
        if getattr(link, "outwardIssue", None) is not None:
            other, direction = link.outwardIssue, getattr(link_type, "outward", "relates to")
        elif getattr(link, "inwardIssue", None) is not None:
            other, direction = link.inwardIssue, getattr(link_type, "inward", "relates to")
        else:
            continue
        links.append(
            {
                "type": getattr(link_type, "name", None),
                "direction": direction,
                "key": other.key,
                "summary": getattr(other.fields, "summary", None),
                "status": str(getattr(other.fields, "status", None)),
            }
        )
    parent = getattr(f, "parent", None)
    subtasks = [
        {"key": s.key, "summary": getattr(s.fields, "summary", None), "status": str(getattr(s.fields, "status", None))}
        for s in (getattr(f, "subtasks", []) or [])
    ]
    emit(
        {
            "parent": parent.key if parent is not None else None,
            "subtasks": subtasks,
            "links": links,
        }
    )


def cmd_changelog(args: argparse.Namespace) -> None:
    jira = _client()
    issue = jira.issue(str(args.issue_key), expand="changelog")
    histories = getattr(getattr(issue, "changelog", None), "histories", []) or []
    emit(
        [
            {
                "author": str(getattr(h, "author", None)),
                "created": str(getattr(h, "created", None)),
                "items": [
                    {
                        "field": getattr(it, "field", None),
                        "from": getattr(it, "fromString", None),
                        "to": getattr(it, "toString", None),
                    }
                    for it in getattr(h, "items", []) or []
                ],
            }
            for h in histories
        ]
    )


def cmd_watchers(args: argparse.Namespace) -> None:
    jira = _client()
    watchers = jira.watchers(str(args.issue_key))
    emit(
        {
            "count": getattr(watchers, "watchCount", None),
            "watchers": [str(w) for w in getattr(watchers, "watchers", []) or []],
        }
    )


def cmd_attachments(args: argparse.Namespace) -> None:
    jira = _client()
    issue = jira.issue(str(args.issue_key), fields="attachment")
    attachments = getattr(issue.fields, "attachment", []) or []
    emit(
        [
            {
                "id": a.id,
                "filename": a.filename,
                "size": a.size,
                "mime_type": a.mimeType,
                "created": str(a.created),
                "author": str(a.author),
                "content_url": a.content,
            }
            for a in attachments
        ]
    )


def cmd_download_attachment(args: argparse.Namespace) -> None:
    import httpx

    _, username, password = _settings()
    jira = _client()
    attachment = jira.attachment(str(args.attachment_id))
    filename = attachment.filename
    dest = Path(args.save_path) if args.save_path else Path.cwd() / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(auth=(username, password), follow_redirects=True) as client:
        resp = client.get(attachment.content)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    emit({"saved_to": str(dest), "size": len(resp.content), "filename": filename})


def cmd_add_comment(args: argparse.Namespace) -> None:
    jira = _client()
    comment = jira.add_comment(str(args.issue_key), args.body)
    emit(
        {
            "issue": str(args.issue_key),
            "comment_id": comment.id,
            "author": str(getattr(comment, "author", None)),
            "created": str(getattr(comment, "created", None)),
        }
    )


def cmd_do_transition(args: argparse.Namespace) -> None:
    jira = _client()
    key = str(args.issue_key)
    # accept a transition id or a (case-insensitive) transition name
    available = jira.transitions(key)
    match = next(
        (t for t in available if args.transition in (t["id"], t["name"])),
        None,
    ) or next(
        (t for t in available if t["name"].lower() == args.transition.lower()),
        None,
    )
    if match is None:
        names = ", ".join(f"{t['name']}({t['id']})" for t in available) or "(none available)"
        fail(f"no transition matching '{args.transition}'. Available: {names}")
    jira.transition_issue(key, match["id"], comment=args.comment)
    emit(
        {
            "issue": key,
            "applied_transition": {"id": match["id"], "name": match["name"]},
            "status": str(jira.issue(key, fields="status").fields.status),
        }
    )


def cmd_assign(args: argparse.Namespace) -> None:
    jira = _client()
    key = str(args.issue_key)
    # "-" unassigns; "auto" lets Jira pick the default assignee
    assignee = {"-": None, "auto": "-1"}.get(args.assignee, args.assignee)
    jira.assign_issue(key, assignee)
    emit({"issue": key, "assignee": str(jira.issue(key, fields="assignee").fields.assignee)})


def cmd_health(args: argparse.Namespace) -> None:
    import httpx

    server, username, password = _settings()
    try:
        with httpx.Client(auth=(username, password), follow_redirects=True, timeout=10) as client:
            resp = client.get(f"{server}/rest/api/2/myself")
            resp.raise_for_status()
        emit({"name": "jira", "status": "ok", "message": server})
    except Exception as exc:  # noqa: BLE001 - report failures as data
        emit({"name": "jira", "status": "error", "message": str(exc)})


# --- setup: build a Jira analysis workspace ---------------------------------
#
# Lays out, in the current directory:
#     JIRA.md              # living analysis doc (skeleton if absent, kept if present)
#     attachments/         # raw attachments (archives extracted to extracted/)
#     docs/{issue,attachments,timeline,evidence,next-steps}.md


def _field(issue: Any, name: str, default: Any = "") -> Any:
    value = getattr(issue.fields, name, None)
    return value if value is not None else default


def _names(items: Any, attr: str = "name") -> list[str]:
    return [getattr(i, attr, str(i)) for i in (items or [])]


def _classify(filename: str) -> str:
    lower = filename.lower()
    if lower.endswith((".log", ".txt", ".dmesg", ".logcat")):
        return "log"
    if lower.endswith((".zip", ".tar", ".tar.gz", ".tgz", ".gz", ".7z", ".rar")):
        return "archive"
    if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
        return "image"
    if lower.endswith((".mp4", ".mkv", ".mov", ".ts")):
        return "video"
    return "other"


def _extract_archive(path: Path, dest_root: Path) -> Path | None:
    """Extract a zip/tar archive into dest_root/<archive-name>/; return its dir."""
    out = dest_root / path.name
    try:
        if zipfile.is_zipfile(path):
            out.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(path) as zf:
                zf.extractall(out)
            return out
        if tarfile.is_tarfile(path):
            out.mkdir(parents=True, exist_ok=True)
            with tarfile.open(path) as tf:
                tf.extractall(out)
            return out
    except Exception as exc:  # noqa: BLE001 - keep going on a bad archive
        log(f"extract failed {path.name}: {exc}")
    return None


def _download_attachments(issue: Any, attach_dir: Path, do_extract: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    attachments = _field(issue, "attachment", []) or []
    if not attachments:
        log("no attachments")
        return rows

    attach_dir.mkdir(parents=True, exist_ok=True)
    extracted_root = attach_dir / "extracted"

    for att in attachments:
        filename = getattr(att, "filename", "unknown")
        size = int(getattr(att, "size", 0) or 0)
        mime = getattr(att, "mimeType", "")
        created = str(getattr(att, "created", ""))
        author = getattr(getattr(att, "author", None), "displayName", "")
        kind = _classify(filename)
        target = attach_dir / filename
        status = "downloaded"
        extracted_at = ""

        try:
            target.write_bytes(att.get())  # raw bytes via the jira client
            log(f"downloaded {filename} ({size} bytes)")
        except Exception as exc:  # noqa: BLE001 - record failure, keep going
            status = "failed"
            log(f"download failed {filename}: {exc}")

        if status == "downloaded" and do_extract and kind == "archive":
            out = _extract_archive(target, extracted_root)
            if out is not None:
                extracted_at = str(out.relative_to(attach_dir.parent))

        rows.append(
            {
                "filename": filename,
                "type": kind,
                "size": size,
                "mime": mime,
                "author": author,
                "created": created,
                "status": status,
                "path": str(target.relative_to(attach_dir.parent)),
                "extracted": extracted_at,
            }
        )
    return rows


def _render_issue_md(issue: Any, key: str) -> str:
    components = ", ".join(_names(_field(issue, "components", []))) or "-"
    labels = ", ".join(_field(issue, "labels", []) or []) or "-"
    fix_versions = ", ".join(_names(_field(issue, "fixVersions", []))) or "-"
    affects = ", ".join(_names(_field(issue, "versions", []))) or "-"
    reporter = getattr(_field(issue, "reporter", None), "displayName", "-")
    assignee = getattr(_field(issue, "assignee", None), "displayName", "-")
    priority = getattr(_field(issue, "priority", None), "name", "-")
    status = getattr(_field(issue, "status", None), "name", "-")
    issuetype = getattr(_field(issue, "issuetype", None), "name", "-")
    description = _field(issue, "description", "") or "_(no description)_"

    lines = [
        f"# {key}: {_field(issue, 'summary', '')}",
        "",
        "## Metadata",
        "",
        f"- Type: {issuetype}",
        f"- Status: {status}",
        f"- Priority: {priority}",
        f"- Components: {components}",
        f"- Labels: {labels}",
        f"- Affects Versions: {affects}",
        f"- Fix Versions: {fix_versions}",
        f"- Reporter: {reporter}",
        f"- Assignee: {assignee}",
        f"- Created: {_field(issue, 'created', '-')}",
        f"- Updated: {_field(issue, 'updated', '-')}",
        "",
        "## Description",
        "",
        description,
        "",
        "## Comments",
        "",
    ]

    comments = getattr(issue.fields, "comment", None)
    comment_list = getattr(comments, "comments", []) if comments else []
    if not comment_list:
        lines.append("_(no comments)_")
    else:
        for c in comment_list:
            author = getattr(getattr(c, "author", None), "displayName", "unknown")
            created = getattr(c, "created", "")
            body = getattr(c, "body", "") or ""
            lines += [f"### {author} @ {created}", "", body, ""]

    return "\n".join(lines).rstrip() + "\n"


def _render_attachments_md(key: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"# {key} Attachments", ""]
    if not rows:
        lines.append("_(no attachments)_")
        return "\n".join(lines) + "\n"

    lines += [
        "| File | Type | Size(B) | Status | Path | Extracted | Author | Time |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        extracted = f"`{r['extracted']}`" if r["extracted"] else "-"
        lines.append(
            f"| {r['filename']} | {r['type']} | {r['size']} | {r['status']} | "
            f"`{r['path']}` | {extracted} | {r['author']} | {r['created']} |"
        )
    failed = [r["filename"] for r in rows if r["status"] != "downloaded"]
    if failed:
        lines += ["", "## Download Failures", ""]
        lines += [f"- {name}" for name in failed]
        lines += ["", "> Record failed items in JIRA.md Open Questions / Next Steps."]
    return "\n".join(lines) + "\n"


def _render_jira_md(key: str, summary: str) -> str:
    return f"""# {key} Jira Analysis

## Current State

One line on where the analysis currently stands. ({summary})

## Facts

- ...

## Working Hypotheses

- ...

## Evidence Index

- Jira: `docs/issue.md`
- Attachments: `docs/attachments.md`
- Timeline: `docs/timeline.md`
- Evidence: `docs/evidence.md`

## Next Steps

- [ ] ...

## Open Questions

- ...
"""


def _write_if_absent(path: Path, content: str) -> None:
    """Create skeleton docs without clobbering existing analysis."""
    if path.exists():
        log(f"keep existing {path.name}")
        return
    path.write_text(content, encoding="utf-8")
    log(f"created {path.name}")


def cmd_setup(args: argparse.Namespace) -> None:
    key = args.issue_key.strip()
    workdir = Path(".").resolve()
    docs = workdir / "docs"
    attach_dir = workdir / "attachments"
    docs.mkdir(parents=True, exist_ok=True)

    jira = _client()
    log(f"fetching issue {key}")
    try:
        issue = jira.issue(key)
    except Exception as exc:  # noqa: BLE001 - surface a clear message
        fail(f"failed to fetch issue {key}: {exc}")

    summary = _field(issue, "summary", "")

    # 1) metadata / description / comments
    (docs / "issue.md").write_text(_render_issue_md(issue, key), encoding="utf-8")
    log("wrote docs/issue.md")

    # 2) attachments
    rows = _download_attachments(issue, attach_dir, do_extract=not args.no_extract)
    (docs / "attachments.md").write_text(_render_attachments_md(key, rows), encoding="utf-8")
    log("wrote docs/attachments.md")

    # 3) living doc and remaining skeletons (do not overwrite existing analysis)
    _write_if_absent(workdir / "JIRA.md", _render_jira_md(key, summary))
    _write_if_absent(
        docs / "timeline.md",
        f"# {key} Timeline\n\n- {_field(issue, 'created', '?')} Issue created\n",
    )
    _write_if_absent(
        docs / "evidence.md",
        f"# {key} Evidence\n\n## Confluence\n\n## Logs\n\n## Code\n\n## Prior Cases\n",
    )
    _write_if_absent(docs / "next-steps.md", f"# {key} Next Steps\n\n- [ ] ...\n")

    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    print(f"workspace ready: {workdir}  (setup at {now})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Jira CLI (read + write)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search issues with JQL")
    p.add_argument("jql")
    p.add_argument("--max-results", type=int, default=50)
    p.add_argument("--fields", default=None, help="comma-separated field list")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get", help="fetch one issue by key")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_get)

    p = sub.add_parser("transitions", help="list available transitions")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_transitions)

    p = sub.add_parser("projects", help="list projects")
    p.set_defaults(func=cmd_projects)

    p = sub.add_parser("comments", help="list comments on an issue")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser("links", help="list linked issues, parent and subtasks")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_links)

    p = sub.add_parser("changelog", help="list the issue field change history")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_changelog)

    p = sub.add_parser("watchers", help="list watchers on an issue")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_watchers)

    p = sub.add_parser("attachments", help="list attachments on an issue")
    p.add_argument("issue_key")
    p.set_defaults(func=cmd_attachments)

    p = sub.add_parser("download-attachment", help="download an attachment by id")
    p.add_argument("attachment_id")
    p.add_argument("--save-path", default=None)
    p.set_defaults(func=cmd_download_attachment)

    p = sub.add_parser(
        "setup",
        help="build a Jira analysis workspace (JIRA.md + docs/ + attachments/) in CWD",
    )
    p.add_argument("issue_key")
    p.add_argument(
        "--no-extract", action="store_true", help="do not extract downloaded archives"
    )
    p.set_defaults(func=cmd_setup)

    p = sub.add_parser("add-comment", help="[write] post a comment on an issue")
    p.add_argument("issue_key")
    p.add_argument("body", help="comment text")
    p.set_defaults(func=cmd_add_comment)

    p = sub.add_parser("do-transition", help="[write] move an issue through a workflow transition")
    p.add_argument("issue_key")
    p.add_argument("transition", help="transition id or name (e.g. 'In Progress'); see `transitions`")
    p.add_argument("--comment", default=None, help="optional comment to add with the transition")
    p.set_defaults(func=cmd_do_transition)

    p = sub.add_parser("assign", help="[write] set the assignee ('-' unassigns, 'auto' uses default)")
    p.add_argument("issue_key")
    p.add_argument("assignee", help="username, '-' to unassign, or 'auto'")
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("health", help="check connectivity")
    p.set_defaults(func=cmd_health)

    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - turn library errors into clean exits
        fail(str(exc))


if __name__ == "__main__":
    main()
