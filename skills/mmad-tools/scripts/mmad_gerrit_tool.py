#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Standalone Gerrit CLI.

Read and write access to Gerrit changes, diffs, files and projects via the
authenticated REST API (/a/...). Self-contained: depends only on `httpx`
(`pip install httpx`) and reads credentials from the environment.

Auth: HTTP Digest (some Gerrit servers require Digest rather than Basic).
Gerrit REST responses are prefixed with )]}'\\n which is stripped automatically.

Environment:
    GERRIT_SERVER     Gerrit base URL, e.g. https://gerrit.example.com
    GERRIT_USERNAME   username
    GERRIT_PASSWORD   HTTP password (Gerrit -> Settings -> HTTP Credentials)

Usage (read):
    uv run mmad_gerrit_tool.py list-changes --query "status:open" --limit 25
    uv run mmad_gerrit_tool.py get-change 12345
    uv run mmad_gerrit_tool.py get-change-detail 12345
    uv run mmad_gerrit_tool.py get-change-diff 12345 --revision current
    uv run mmad_gerrit_tool.py get-change-messages 12345
    uv run mmad_gerrit_tool.py get-change-comments 12345
    uv run mmad_gerrit_tool.py get-patch 12345 --revision current
    uv run mmad_gerrit_tool.py related-changes 12345
    uv run mmad_gerrit_tool.py get-file-content 12345 path/to/file.c
    uv run mmad_gerrit_tool.py list-projects --prefix amlogic/ --limit 100
    uv run mmad_gerrit_tool.py project-branches amlogic/foo --limit 50
    uv run mmad_gerrit_tool.py project-tags amlogic/foo --limit 50
    uv run mmad_gerrit_tool.py health

Usage (write):
    uv run mmad_gerrit_tool.py set-review 12345 --message "LGTM" --label Code-Review=+1

All results are printed as JSON to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any
from urllib.parse import quote

TAG = "gerrit"
_GERRIT_MAGIC = b")]}'\n"
_CHANGE_OPTIONS = [
    "DETAILED_ACCOUNTS",
    "DETAILED_LABELS",
    "MESSAGES",
    "CURRENT_REVISION",
    "CURRENT_COMMIT",
]


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
    server = _env("GERRIT_SERVER")
    username = _env("GERRIT_USERNAME")
    password = _env("GERRIT_PASSWORD")
    if not server:
        fail("missing required setting: set GERRIT_SERVER")
    if not username:
        fail("missing required setting: set GERRIT_USERNAME")
    if not password:
        fail("missing required setting: set GERRIT_PASSWORD")
    return server.rstrip("/"), username, password


def _make_client():
    import httpx

    server, username, password = _settings()
    auth = httpx.DigestAuth(username, password)
    client = httpx.Client(auth=auth, follow_redirects=True, timeout=30)
    return client, f"{server}/a"


def _parse(response: Any) -> Any:
    """Strip the Gerrit magic prefix and parse JSON."""
    content = response.content
    if content.startswith(_GERRIT_MAGIC):
        content = content[len(_GERRIT_MAGIC) :]
    return json.loads(content)


def _change_to_dict(change: dict[str, Any]) -> dict[str, Any]:
    current_rev = change.get("current_revision")
    commit_info: dict[str, Any] = {}
    if current_rev and "revisions" in change:
        rev_data = change["revisions"].get(current_rev, {})
        commit = rev_data.get("commit", {})
        commit_info = {
            "subject": commit.get("subject"),
            "message": commit.get("message"),
            "author": commit.get("author", {}).get("name"),
            "committer": commit.get("committer", {}).get("name"),
            "patch_set": rev_data.get("_number"),
            "ref": rev_data.get("ref"),
        }
    labels: dict[str, Any] = {}
    for label_name, label_data in change.get("labels", {}).items():
        labels[label_name] = {
            "approved_by": label_data.get("approved", {}).get("name"),
            "rejected_by": label_data.get("rejected", {}).get("name"),
        }
    return {
        "id": change.get("id"),
        "change_number": change.get("_number"),
        "project": change.get("project"),
        "branch": change.get("branch"),
        "subject": change.get("subject"),
        "status": change.get("status"),
        "owner": change.get("owner", {}).get("name"),
        "created": change.get("created"),
        "updated": change.get("updated"),
        "insertions": change.get("insertions"),
        "deletions": change.get("deletions"),
        "topic": change.get("topic"),
        "hashtags": change.get("hashtags"),
        "labels": labels,
        "commit": commit_info,
    }


def cmd_list_changes(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(
            f"{base}/changes/",
            params={"q": args.query, "n": args.limit, "o": _CHANGE_OPTIONS},
        )
        resp.raise_for_status()
        emit([_change_to_dict(c) for c in _parse(resp)])


def cmd_get_change(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}", params={"o": _CHANGE_OPTIONS})
        resp.raise_for_status()
        emit(_change_to_dict(_parse(resp)))


def cmd_get_change_detail(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}/detail", params={"o": _CHANGE_OPTIONS})
        resp.raise_for_status()
        change = _parse(resp)
        files: dict[str, Any] = {}
        current_rev = change.get("current_revision")
        if current_rev:
            fr = client.get(f"{base}/changes/{args.change_id}/revisions/{current_rev}/files")
            if fr.is_success:
                raw_files = _parse(fr)
                if isinstance(raw_files, dict):
                    files = {
                        path: {
                            "lines_inserted": info.get("lines_inserted", 0)
                            if isinstance(info, dict)
                            else 0,
                            "lines_deleted": info.get("lines_deleted", 0)
                            if isinstance(info, dict)
                            else 0,
                            "size_delta": info.get("size_delta", 0)
                            if isinstance(info, dict)
                            else 0,
                            "status": info.get("status") if isinstance(info, dict) else None,
                        }
                        for path, info in raw_files.items()
                    }
        result = _change_to_dict(change)
        result["files"] = files
        emit(result)


def cmd_get_change_diff(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        fr = client.get(f"{base}/changes/{args.change_id}/revisions/{args.revision}/files")
        fr.raise_for_status()
        parsed_files = _parse(fr)
        if not isinstance(parsed_files, dict):
            fail(f"unexpected response type: expected dict, got {type(parsed_files).__name__}")
        diff_params: dict[str, Any] = {}
        if args.base_revision:
            diff_params["base"] = args.base_revision
        diffs: dict[str, Any] = {}
        for file_path in [p for p in parsed_files.keys() if p != "/COMMIT_MSG"][:20]:
            enc_path = quote(file_path, safe="")
            dr = client.get(
                f"{base}/changes/{args.change_id}/revisions/{args.revision}/files/{enc_path}/diff",
                params=diff_params,
            )
            if dr.is_success:
                diffs[file_path] = _parse(dr)
        emit(diffs)


def cmd_get_change_messages(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}/messages")
        resp.raise_for_status()
        emit(
            [
                {
                    "id": m.get("id"),
                    "author": m.get("author", {}).get("name"),
                    "date": m.get("date"),
                    "message": m.get("message"),
                    "patch_set": m.get("_revision_number"),
                }
                for m in _parse(resp)
            ]
        )


def cmd_get_change_comments(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}/comments")
        resp.raise_for_status()
        by_file = _parse(resp)
        result: dict[str, Any] = {}
        if isinstance(by_file, dict):
            for path, items in by_file.items():
                result[path] = [
                    {
                        "id": c.get("id"),
                        "line": c.get("line"),
                        "patch_set": c.get("patch_set"),
                        "author": c.get("author", {}).get("name"),
                        "updated": c.get("updated"),
                        "in_reply_to": c.get("in_reply_to"),
                        "unresolved": c.get("unresolved"),
                        "message": c.get("message"),
                    }
                    for c in (items or [])
                    if isinstance(c, dict)
                ]
        emit(result)


def cmd_get_patch(args: argparse.Namespace) -> None:
    import base64 as _b64

    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}/revisions/{args.revision}/patch")
        resp.raise_for_status()
        # The patch endpoint returns the patch base64-encoded (no magic prefix).
        try:
            patch = _b64.b64decode(resp.content).decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - fall back to raw text
            patch = resp.text
        emit({"change_id": args.change_id, "revision": args.revision, "patch": patch})


def cmd_related_changes(args: argparse.Namespace) -> None:
    client, base = _make_client()
    with client:
        resp = client.get(f"{base}/changes/{args.change_id}/revisions/{args.revision}/related")
        resp.raise_for_status()
        data = _parse(resp)
        changes = data.get("changes", []) if isinstance(data, dict) else []
        emit(
            [
                {
                    "change_number": c.get("_change_number"),
                    "change_id": c.get("change_id"),
                    "project": c.get("project"),
                    "subject": c.get("commit", {}).get("subject"),
                    "status": c.get("status"),
                }
                for c in changes
            ]
        )


def cmd_get_file_content(args: argparse.Namespace) -> None:
    client, base = _make_client()
    enc_path = quote(args.file_path, safe="")
    with client:
        resp = client.get(
            f"{base}/changes/{args.change_id}/revisions/{args.revision}/files/{enc_path}/content"
        )
        resp.raise_for_status()
        decoded = base64.b64decode(resp.content).decode("utf-8", errors="replace")
        emit({"file_path": args.file_path, "content": decoded})


def cmd_list_projects(args: argparse.Namespace) -> None:
    client, base = _make_client()
    params: dict[str, Any] = {"n": args.limit}
    if args.prefix is not None:
        params["p"] = args.prefix
    with client:
        resp = client.get(f"{base}/projects/", params=params)
        resp.raise_for_status()
        projects = _parse(resp)
        emit(
            [
                {"name": name, "state": info.get("state"), "id": info.get("id")}
                for name, info in projects.items()
            ]
        )


def cmd_project_branches(args: argparse.Namespace) -> None:
    client, base = _make_client()
    enc_project = quote(args.project, safe="")
    with client:
        resp = client.get(f"{base}/projects/{enc_project}/branches", params={"n": args.limit})
        resp.raise_for_status()
        emit(
            [
                {
                    "ref": b.get("ref"),
                    "revision": b.get("revision"),
                    "can_delete": b.get("can_delete"),
                }
                for b in _parse(resp)
            ]
        )


def cmd_project_tags(args: argparse.Namespace) -> None:
    client, base = _make_client()
    enc_project = quote(args.project, safe="")
    with client:
        resp = client.get(f"{base}/projects/{enc_project}/tags", params={"n": args.limit})
        resp.raise_for_status()
        emit(
            [
                {
                    "ref": t.get("ref"),
                    "revision": t.get("revision"),
                    "object": t.get("object"),
                    "message": t.get("message"),
                }
                for t in _parse(resp)
            ]
        )


def _parse_labels(pairs: list[str] | None) -> dict[str, int]:
    """Turn ['Code-Review=+1', 'Verified=1'] into {'Code-Review': 1, 'Verified': 1}."""
    labels: dict[str, int] = {}
    for pair in pairs or []:
        if "=" not in pair:
            fail(f"invalid --label '{pair}'; expected NAME=VALUE like Code-Review=+1")
        name, _, value = pair.partition("=")
        try:
            labels[name.strip()] = int(value)
        except ValueError:
            fail(f"invalid label value in '{pair}'; expected an integer like +1, 0, -1")
    return labels


def cmd_set_review(args: argparse.Namespace) -> None:
    client, base = _make_client()
    payload: dict[str, Any] = {}
    if args.message:
        payload["message"] = args.message
    labels = _parse_labels(args.label)
    if labels:
        payload["labels"] = labels
    if not payload:
        fail("nothing to post: pass --message and/or --label NAME=VALUE")
    with client:
        resp = client.post(
            f"{base}/changes/{args.change_id}/revisions/{args.revision}/review", json=payload
        )
        resp.raise_for_status()
        result = _parse(resp)
        emit(
            {
                "change_id": args.change_id,
                "revision": args.revision,
                "posted_message": bool(args.message),
                "applied_labels": result.get("labels", labels) if isinstance(result, dict) else labels,
            }
        )


def cmd_health(args: argparse.Namespace) -> None:
    import httpx

    server, username, password = _settings()
    try:
        auth = httpx.DigestAuth(username, password)
        with httpx.Client(auth=auth, follow_redirects=True, timeout=10) as client:
            resp = client.get(f"{server}/a/config/server/version")
            resp.raise_for_status()
        emit({"name": "gerrit", "status": "ok", "message": server})
    except Exception as exc:  # noqa: BLE001 - report failures as data
        emit({"name": "gerrit", "status": "error", "message": str(exc)})


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone Gerrit CLI (read + write)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-changes", help="query changes")
    p.add_argument("--query", default="status:open")
    p.add_argument("--limit", type=int, default=25)
    p.set_defaults(func=cmd_list_changes)

    p = sub.add_parser("get-change", help="basic info for a change")
    p.add_argument("change_id")
    p.set_defaults(func=cmd_get_change)

    p = sub.add_parser("get-change-detail", help="detailed change info including files")
    p.add_argument("change_id")
    p.set_defaults(func=cmd_get_change_detail)

    p = sub.add_parser("get-change-diff", help="diff data for a change (first 20 files)")
    p.add_argument("change_id")
    p.add_argument("--revision", default="current")
    p.add_argument("--base-revision", default=None)
    p.set_defaults(func=cmd_get_change_diff)

    p = sub.add_parser("get-change-messages", help="review messages for a change")
    p.add_argument("change_id")
    p.set_defaults(func=cmd_get_change_messages)

    p = sub.add_parser("get-change-comments", help="inline (file/line) review comments")
    p.add_argument("change_id")
    p.set_defaults(func=cmd_get_change_comments)

    p = sub.add_parser("get-patch", help="full unified patch for a revision")
    p.add_argument("change_id")
    p.add_argument("--revision", default="current")
    p.set_defaults(func=cmd_get_patch)

    p = sub.add_parser("related-changes", help="changes in the same relation chain")
    p.add_argument("change_id")
    p.add_argument("--revision", default="current")
    p.set_defaults(func=cmd_related_changes)

    p = sub.add_parser("get-file-content", help="file content from a change revision")
    p.add_argument("change_id")
    p.add_argument("file_path")
    p.add_argument("--revision", default="current")
    p.set_defaults(func=cmd_get_file_content)

    p = sub.add_parser("list-projects", help="list accessible projects")
    p.add_argument("--prefix", default=None)
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(func=cmd_list_projects)

    p = sub.add_parser("project-branches", help="list branches for a project")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_project_branches)

    p = sub.add_parser("project-tags", help="list tags for a project")
    p.add_argument("project")
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_project_tags)

    p = sub.add_parser("set-review", help="[write] post a review message and/or vote labels")
    p.add_argument("change_id")
    p.add_argument("--revision", default="current")
    p.add_argument("--message", default=None, help="review message to post")
    p.add_argument(
        "--label",
        action="append",
        default=None,
        help="repeatable vote like Code-Review=+1 or Verified=1",
    )
    p.set_defaults(func=cmd_set_review)

    p = sub.add_parser("health", help="check connectivity")
    p.set_defaults(func=cmd_health)

    args = parser.parse_args()
    try:
        args.func(args)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 - turn library errors into clean exits
        import httpx

        if isinstance(exc, httpx.HTTPStatusError):
            fail(f"HTTP {exc.response.status_code}: {exc.response.text[:500]}")
        fail(str(exc))


if __name__ == "__main__":
    main()
