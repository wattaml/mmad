#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["atlassian-python-api", "httpx"]
# ///
"""Standalone Confluence CLI.

Read and write access to Confluence content, spaces and attachments.
Self-contained: depends on `atlassian-python-api` (`pip install atlassian-python-api`)
and `httpx` (for attachment downloads), reading credentials from the environment.

Authentication: prefer a Personal Access Token (CONFLUENCE_TOKEN); otherwise
fall back to basic auth (CONFLUENCE_USERNAME + CONFLUENCE_PASSWORD).

Environment:
    CONFLUENCE_SERVER     Confluence base URL, e.g. https://confluence.example.com
    CONFLUENCE_TOKEN      Personal Access Token (preferred)
    CONFLUENCE_USERNAME   username (basic-auth fallback)
    CONFLUENCE_PASSWORD   password (basic-auth fallback)

Usage (read):
    uv run mmad_confluence_tool.py search "space = ENG AND title ~ 'release'" --limit 10
    uv run mmad_confluence_tool.py get-page 665519915
    uv run mmad_confluence_tool.py get-page-by-title ENG "Release Notes"
    uv run mmad_confluence_tool.py spaces --limit 25
    uv run mmad_confluence_tool.py children 665519915 --limit 20
    uv run mmad_confluence_tool.py descendants 665519915 --limit 200
    uv run mmad_confluence_tool.py labels 665519915
    uv run mmad_confluence_tool.py comments 665519915
    uv run mmad_confluence_tool.py attachments 665519915
    uv run mmad_confluence_tool.py download-attachment 665519915 att123 --save-path ./f.pdf
    uv run mmad_confluence_tool.py health

Usage (write):
    uv run mmad_confluence_tool.py add-comment 665519915 "Linked SWPL-123 analysis."
    uv run mmad_confluence_tool.py create-page ENG "New Page" --body "<p>hi</p>" --parent-id 665519915
    uv run mmad_confluence_tool.py update-page 665519915 --body "<p>updated</p>"

All results are printed as JSON to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

TAG = "confluence"


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


def _settings() -> dict[str, str]:
    server = _env("CONFLUENCE_SERVER")
    token = _env("CONFLUENCE_TOKEN")
    username = _env("CONFLUENCE_USERNAME")
    password = _env("CONFLUENCE_PASSWORD")
    if not server:
        fail("missing required setting: set CONFLUENCE_SERVER")
    if not token and not (username and password):
        fail("missing credentials: set CONFLUENCE_TOKEN or CONFLUENCE_USERNAME+CONFLUENCE_PASSWORD")
    return {
        "server": server.rstrip("/"),
        "token": token,
        "username": username,
        "password": password,
    }


def _client(cfg: dict[str, str]):
    try:
        from atlassian import Confluence
    except ImportError:
        fail("missing dependency: run `pip install atlassian-python-api` first")
    if cfg["token"]:
        return Confluence(url=cfg["server"], token=cfg["token"])
    return Confluence(url=cfg["server"], username=cfg["username"], password=cfg["password"])


def _page_to_dict(page: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": page.get("id"),
        "title": page.get("title"),
        "type": page.get("type"),
        "space": page.get("space", {}).get("key"),
        "version": page.get("version", {}).get("number"),
        "created_by": page.get("version", {}).get("by", {}).get("displayName"),
        "created": page.get("version", {}).get("when"),
        "body": page.get("body", {}).get("storage", {}).get("value"),
        "ancestors": [
            {"id": a.get("id"), "title": a.get("title")} for a in page.get("ancestors", [])
        ],
    }


def cmd_search(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    results = confluence.cql(args.cql, limit=args.limit) or {}
    pages = results.get("results", [])
    simplified = [
        {
            "id": p.get("content", {}).get("id"),
            "title": p.get("content", {}).get("title"),
            "type": p.get("content", {}).get("type"),
            "space": p.get("resultGlobalContainer", {}).get("title"),
            "url": p.get("url"),
            "last_modified": p.get("lastModified"),
            "excerpt": p.get("excerpt"),
        }
        for p in pages
    ]
    emit({"total": len(simplified), "results": simplified})


def cmd_get_page(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    page = confluence.get_page_by_id(
        str(args.page_id), expand="body.storage,version,space,ancestors"
    )
    if not isinstance(page, dict):
        fail(f"page '{args.page_id}' not found")
    emit(_page_to_dict(page))


def cmd_get_page_by_title(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    page = confluence.get_page_by_title(
        args.space_key, args.title, expand="body.storage,version,space"
    )
    emit(_page_to_dict(page) if page else None)


def cmd_spaces(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    result = confluence.get_all_spaces(limit=args.limit) or {}
    spaces = result.get("results", []) if isinstance(result, dict) else []
    emit([{"key": s.get("key"), "name": s.get("name"), "type": s.get("type")} for s in spaces])


def cmd_children(args: argparse.Namespace) -> None:
    cfg = _settings()
    confluence = _client(cfg)
    children = (
        confluence.get_page_child_by_type(str(args.page_id), type="page", limit=args.limit) or []
    )
    emit(
        [
            {
                "id": c.get("id"),
                "title": c.get("title"),
                "url": cfg["server"] + c.get("_links", {}).get("webui", ""),
            }
            for c in children
        ]
    )


def cmd_descendants(args: argparse.Namespace) -> None:
    cfg = _settings()
    confluence = _client(cfg)
    results = confluence.cql(
        f"ancestor = {int(str(args.page_id))} and type = page", limit=args.limit
    ) or {}
    pages = results.get("results", [])
    emit(
        [
            {
                "id": p.get("content", {}).get("id"),
                "title": p.get("content", {}).get("title"),
                "url": cfg["server"] + (p.get("url") or ""),
            }
            for p in pages
        ]
    )


def cmd_labels(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    result = confluence.get_page_labels(str(args.page_id)) or {}
    labels = result.get("results", []) if isinstance(result, dict) else []
    emit([{"name": l.get("name"), "prefix": l.get("prefix"), "id": l.get("id")} for l in labels])


def cmd_comments(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    comments = (
        confluence.get_page_child_by_type(
            str(args.page_id), type="comment", expand="body.storage,version"
        )
        or []
    )
    emit(
        [
            {
                "id": c.get("id"),
                "author": c.get("version", {}).get("by", {}).get("displayName"),
                "created": c.get("version", {}).get("when"),
                "body": c.get("body", {}).get("storage", {}).get("value"),
            }
            for c in comments
        ]
    )


def cmd_attachments(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    attachments = confluence.get_attachments_from_content(str(args.page_id)) or {}
    results = attachments.get("results", [])
    emit(
        [
            {
                "id": a.get("id"),
                "title": a.get("title"),
                "filename": a.get("title"),
                "mime_type": a.get("metadata", {}).get("mediaType"),
                "size": a.get("extensions", {}).get("fileSize"),
                "created": a.get("version", {}).get("when"),
                "author": a.get("version", {}).get("by", {}).get("displayName"),
                "download_url": a.get("_links", {}).get("download"),
            }
            for a in results
        ]
    )


def cmd_download_attachment(args: argparse.Namespace) -> None:
    import httpx

    cfg = _settings()
    confluence = _client(cfg)
    attachment_id = str(args.attachment_id)
    attachments = confluence.get_attachments_from_content(str(args.page_id)) or {}
    attachment = next(
        (
            a
            for a in attachments.get("results", [])
            if a.get("id") == attachment_id
            or a.get("id") == f"att{attachment_id}"
            or str(a.get("id", "")).lstrip("att") == attachment_id.lstrip("att")
        ),
        None,
    )
    if attachment is None:
        fail(
            f"attachment '{attachment_id}' not found on page '{args.page_id}'. "
            "Run `attachments <page_id>` to list available attachment ids."
        )
    filename = attachment.get("title", attachment_id)
    url = cfg["server"] + attachment.get("_links", {}).get("download", "")
    dest = Path(args.save_path) if args.save_path else Path.cwd() / filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    if cfg["token"]:
        auth, headers = None, {"Authorization": f"Bearer {cfg['token']}"}
    else:
        auth, headers = (cfg["username"], cfg["password"]), {}
    with httpx.Client(auth=auth, headers=headers, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    emit({"saved_to": str(dest), "size": len(resp.content), "filename": filename})


def _body_from_args(args: argparse.Namespace) -> str:
    """Resolve page/comment body text from --body or --body-file."""
    if getattr(args, "body_file", None):
        return Path(args.body_file).read_text(encoding="utf-8")
    if args.body is not None:
        return args.body
    fail("provide the content via --body or --body-file")
    return ""  # unreachable; keeps type checkers happy


def cmd_add_comment(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    result = confluence.add_comment(str(args.page_id), _body_from_args(args)) or {}
    emit({"page_id": str(args.page_id), "comment_id": result.get("id"), "type": result.get("type")})


def cmd_create_page(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    page = confluence.create_page(
        space=args.space_key,
        title=args.title,
        body=_body_from_args(args),
        parent_id=args.parent_id,
        representation=args.representation,
    )
    emit(_page_to_dict(page) if isinstance(page, dict) else page)


def cmd_update_page(args: argparse.Namespace) -> None:
    confluence = _client(_settings())
    page_id = str(args.page_id)
    title = args.title
    if not title:
        current = confluence.get_page_by_id(page_id, expand="version") or {}
        title = current.get("title")
        if not title:
            fail(f"page '{page_id}' not found; cannot infer title (pass --title)")
    page = confluence.update_page(
        page_id=page_id,
        title=title,
        body=_body_from_args(args),
        representation=args.representation,
        minor_edit=args.minor,
    )
    emit(_page_to_dict(page) if isinstance(page, dict) else page)


def cmd_health(args: argparse.Namespace) -> None:
    import httpx

    cfg = _settings()
    if cfg["token"]:
        auth, headers = None, {"Authorization": f"Bearer {cfg['token']}"}
    else:
        auth, headers = (cfg["username"], cfg["password"]), {}
    try:
        with httpx.Client(auth=auth, headers=headers, follow_redirects=True, timeout=10) as client:
            resp = client.get(f"{cfg['server']}/rest/api/space?limit=1")
            resp.raise_for_status()
        emit({"name": "confluence", "status": "ok", "message": cfg["server"]})
    except Exception as exc:  # noqa: BLE001 - report failures as data
        emit({"name": "confluence", "status": "error", "message": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Confluence CLI (read + write)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("search", help="search content with CQL")
    p.add_argument("cql")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("get-page", help="fetch full page content by id")
    p.add_argument("page_id")
    p.set_defaults(func=cmd_get_page)

    p = sub.add_parser("get-page-by-title", help="fetch a page by space key and exact title")
    p.add_argument("space_key")
    p.add_argument("title")
    p.set_defaults(func=cmd_get_page_by_title)

    p = sub.add_parser("spaces", help="list spaces")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_spaces)

    p = sub.add_parser("children", help="list direct child pages")
    p.add_argument("page_id")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_children)

    p = sub.add_parser("descendants", help="list all descendant pages (recursive, via CQL)")
    p.add_argument("page_id")
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_descendants)

    p = sub.add_parser("labels", help="list labels on a page")
    p.add_argument("page_id")
    p.set_defaults(func=cmd_labels)

    p = sub.add_parser("comments", help="list comments on a page")
    p.add_argument("page_id")
    p.set_defaults(func=cmd_comments)

    p = sub.add_parser("attachments", help="list attachments on a page")
    p.add_argument("page_id")
    p.set_defaults(func=cmd_attachments)

    p = sub.add_parser("download-attachment", help="download an attachment")
    p.add_argument("page_id")
    p.add_argument("attachment_id")
    p.add_argument("--save-path", default=None)
    p.set_defaults(func=cmd_download_attachment)

    p = sub.add_parser("add-comment", help="[write] add a comment to a page")
    p.add_argument("page_id")
    p.add_argument("--body", default=None, help="comment body (storage/HTML or plain text)")
    p.add_argument("--body-file", default=None, help="read the comment body from a file")
    p.set_defaults(func=cmd_add_comment)

    p = sub.add_parser("create-page", help="[write] create a new page")
    p.add_argument("space_key")
    p.add_argument("title")
    p.add_argument("--body", default=None, help="page body in the chosen representation")
    p.add_argument("--body-file", default=None, help="read the page body from a file")
    p.add_argument("--parent-id", default=None, help="parent page id (optional)")
    p.add_argument("--representation", default="storage", choices=["storage", "wiki"])
    p.set_defaults(func=cmd_create_page)

    p = sub.add_parser("update-page", help="[write] update an existing page's body/title")
    p.add_argument("page_id")
    p.add_argument("--title", default=None, help="new title (keep current if omitted)")
    p.add_argument("--body", default=None, help="new body in the chosen representation")
    p.add_argument("--body-file", default=None, help="read the new body from a file")
    p.add_argument("--representation", default="storage", choices=["storage", "wiki"])
    p.add_argument("--minor", action="store_true", help="mark as a minor edit")
    p.set_defaults(func=cmd_update_page)

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
