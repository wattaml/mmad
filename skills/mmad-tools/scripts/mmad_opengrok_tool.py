#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""Standalone OpenGrok query CLI.

Read-only source-code search and file reading against an OpenGrok index.
Self-contained: depends only on `httpx` (`pip install httpx`). OpenGrok needs
no credentials, only a server URL. Tries the REST API first and falls back to
scraping the HTML search results page when the API is unavailable.

Environment:
    OPENGROK_SERVER   OpenGrok base URL, e.g. https://opengrok.example.com

OpenGrok is an inherently read-only code index, so this CLI is read-only too.

Usage:
    uv run mmad_opengrok_tool.py list-projects
    uv run mmad_opengrok_tool.py search-code "amlvideo_open" --projects kernel --max-results 50
    uv run mmad_opengrok_tool.py search-definition "vdec_init"
    uv run mmad_opengrok_tool.py search-symbol "g_vdec"
    uv run mmad_opengrok_tool.py search-path "drivers/media"
    uv run mmad_opengrok_tool.py search-history "fix vdec deadlock" --projects kernel
    uv run mmad_opengrok_tool.py read-file /kernel/drivers/foo.c
    uv run mmad_opengrok_tool.py read-file drivers/foo.c --project kernel
    uv run mmad_opengrok_tool.py file-history /kernel/drivers/foo.c
    uv run mmad_opengrok_tool.py health

`--projects` may be repeated or omitted (search all). Results print as JSON
to stdout; diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote

TAG = "opengrok"


def log(msg: str) -> None:
    print(f"[{TAG}] {msg}", file=sys.stderr)


def fail(msg: str, code: int = 1) -> "Any":
    print(f"[{TAG}] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def emit(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _server() -> str:
    server = os.environ.get("OPENGROK_SERVER")
    if not server:
        fail("missing required setting: set OPENGROK_SERVER")
    return server.rstrip("/")


def _strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    return re.sub(r"\s+", " ", text).strip()


def _extract_project_from_path(path: str) -> str | None:
    parts = path.strip("/").split("/", 1)
    return parts[0] if parts and parts[0] else None


def _extract_projects_from_homepage(html_text: str) -> list[str]:
    match = re.search(
        r'<select[^>]*id="project"[^>]*>(?P<body>.*?)</select>',
        html_text,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return []
    projects = re.findall(r'<option[^>]*value="([^"]+)"', match.group("body"), re.IGNORECASE)
    return sorted(dict.fromkeys(projects))


def _list_projects(client: Any, server: str) -> list[str]:
    try:
        resp = client.get(f"{server}/api/v1/projects")
        resp.raise_for_status()
        projects = resp.json()
        if isinstance(projects, (dict, list)):
            return sorted(str(p) for p in projects)
    except Exception:
        pass
    resp = client.get(f"{server}/")
    resp.raise_for_status()
    return _extract_projects_from_homepage(resp.text)


def _parse_search_html(html_text: str, search_type: str, max_results: int) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    current_dir = ""

    row_re = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    dir_re = re.compile(
        r'<tr\b[^>]*class="[^"]*\bdir\b[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>.*?</tr>',
        re.IGNORECASE | re.DOTALL,
    )
    file_td_re = re.compile(r'<td[^>]*class="f"[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)
    code_td_re = re.compile(r"<td[^>]*><code[^>]*>(.*?)</code></td>", re.IGNORECASE | re.DOTALL)
    file_link_re = re.compile(r"<a[^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    snippet_re = re.compile(
        r'<a[^>]*class="s"[^>]*href="[^"#]*#(?P<line>\d+)"[^>]*>(?P<body>.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for row_match in row_re.finditer(html_text):
        row_html = row_match.group(0)
        dir_match = dir_re.search(row_html)
        if dir_match:
            current_dir = _strip_tags(dir_match.group(1))
            continue

        file_td_match = file_td_re.search(row_html)
        if not file_td_match or not current_dir:
            continue

        file_link_match = file_link_re.search(file_td_match.group(1))
        if not file_link_match:
            continue

        filename = _strip_tags(file_link_match.group(1))
        if not filename:
            continue

        path = f"{current_dir.rstrip('/')}/{filename}"
        project = _extract_project_from_path(path)

        if search_type == "path":
            results.append({"project": project, "path": path})
            if len(results) >= max_results:
                break
            continue

        code_td_match = code_td_re.search(row_html)
        snippets = snippet_re.findall(code_td_match.group(1) if code_td_match else "")
        if snippets:
            for line_number, snippet_html in snippets:
                results.append(
                    {
                        "project": project,
                        "path": path,
                        "line_number": int(line_number),
                        "line": _strip_tags(snippet_html),
                    }
                )
                if len(results) >= max_results:
                    break
        else:
            results.append({"project": project, "path": path})

        if len(results) >= max_results:
            break

    return results[:max_results]


def _search_api_results(
    client: Any, server: str, search_type: str, query: str, max_results: int, project: str | None
) -> list[dict[str, Any]]:
    params: dict[str, Any] = {search_type: query, "maxresults": max_results}
    if project:
        params["projects"] = project
    resp = client.get(f"{server}/api/v1/search", params=params)
    resp.raise_for_status()
    data = resp.json()

    results: list[dict[str, Any]] = []
    raw_results = data.get("results", {})
    if isinstance(raw_results, dict):
        for project_name, hits in raw_results.items():
            if not isinstance(hits, list):
                continue
            for hit in hits:
                entry: dict[str, Any] = {"project": project_name}
                if "path" in hit:
                    entry["path"] = hit["path"]
                if "lineno" in hit:
                    entry["line_number"] = hit["lineno"]
                if "line" in hit:
                    entry["line"] = hit["line"]
                results.append(entry)
    elif isinstance(raw_results, list):
        results = raw_results
    return results[:max_results]


def _search_html_results(
    client: Any, server: str, search_type: str, query: str, max_results: int, project: str | None
) -> list[dict[str, Any]]:
    params: list[tuple[str, str | int]] = [(search_type, query), ("n", max_results)]
    if project:
        params.append(("project", project))
    resp = client.get(f"{server}/search", params=params)
    resp.raise_for_status()
    return _parse_search_html(resp.text, search_type, max_results)


def _normalize_projects(projects: Any) -> list[str]:
    if isinstance(projects, str):
        return [projects]
    if isinstance(projects, list):
        return [str(p) for p in projects if str(p).strip()]
    return []


def _search(search_type: str, query: str, projects: Any, max_results: int) -> None:
    import httpx

    query = (query or "").strip()
    if not query:
        fail("missing required arg 'query'")
    server = _server()
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        project_list = _normalize_projects(projects) or _list_projects(client, server)
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        targets: list[str | None] = project_list or [None]

        for project in targets:
            remaining = max_results - len(results)
            if remaining <= 0:
                break
            try:
                hits = _search_api_results(client, server, search_type, query, remaining, project)
            except Exception as api_exc:
                try:
                    hits = _search_html_results(
                        client, server, search_type, query, remaining, project
                    )
                except Exception as html_exc:
                    errors.append(f"{project or '*'}: API {api_exc}; HTML {html_exc}")
                    continue
            results.extend(hits)

        if search_type == "path":
            path_results = [{"project": r.get("project"), "path": r.get("path")} for r in results]
            if path_results:
                emit(path_results[:max_results])
                return
        elif results:
            emit(results[:max_results])
            return

        if errors:
            fail("search failed for all projects: " + "; ".join(errors[:5]))
        emit([])


def cmd_list_projects(args: argparse.Namespace) -> None:
    import httpx

    server = _server()
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        emit(_list_projects(client, server))


def cmd_search_code(args: argparse.Namespace) -> None:
    _search("full", args.query, args.projects, args.max_results)


def cmd_search_definition(args: argparse.Namespace) -> None:
    _search("defs", args.query, args.projects, args.max_results)


def cmd_search_symbol(args: argparse.Namespace) -> None:
    _search("refs", args.query, args.projects, args.max_results)


def cmd_search_path(args: argparse.Namespace) -> None:
    _search("path", args.query, args.projects, args.max_results)


def cmd_search_history(args: argparse.Namespace) -> None:
    # OpenGrok's "hist" field does full-text search over commit history.
    _search("hist", args.query, args.projects, args.max_results)


def cmd_read_file(args: argparse.Namespace) -> None:
    import httpx

    server = _server()
    file_path = args.file_path
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        try:
            params: dict[str, str] = {"path": file_path}
            if args.project:
                params["project"] = args.project
            resp = client.get(f"{server}/api/v1/file/content", params=params)
            resp.raise_for_status()
            emit({"file_path": file_path, "content": resp.text})
            return
        except Exception:
            pass

        # Fallback to the /download endpoint.
        normalized = file_path.strip()
        if normalized.startswith("/"):
            download_path = normalized.lstrip("/")
        elif args.project:
            download_path = f"{args.project}/{normalized.lstrip('/')}"
        else:
            fail(
                "file_path must include the project prefix like '/project/path/to/file' "
                "or pass --project"
            )
        url = f"{server}/download/{quote(download_path, safe='/')}"
        resp = client.get(url)
        resp.raise_for_status()
        emit({"file_path": file_path, "content": resp.text})


def cmd_file_history(args: argparse.Namespace) -> None:
    import httpx

    server = _server()
    file_path = args.file_path.strip()
    if not file_path.startswith("/"):
        if args.project:
            file_path = f"/{args.project.strip('/')}/{file_path.lstrip('/')}"
        else:
            fail(
                "file_path must start with the project prefix like '/project/path/to/file' "
                "or pass --project"
            )
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        resp = client.get(
            f"{server}/api/v1/history", params={"path": file_path, "max": args.max_results}
        )
        resp.raise_for_status()
        data = resp.json()
        entries = data.get("entries", data) if isinstance(data, dict) else data
        rows = [
            {
                "revision": e.get("revision"),
                "date": e.get("date"),
                "author": e.get("author"),
                "message": e.get("message"),
                "files": e.get("files"),
            }
            for e in (entries or [])
            if isinstance(e, dict)
        ]
        emit({"file_path": file_path, "total": len(rows), "history": rows})


def cmd_health(args: argparse.Namespace) -> None:
    import httpx

    server = _server()
    try:
        with httpx.Client(follow_redirects=True, timeout=5) as client:
            resp = client.head(server)
            resp.raise_for_status()
        emit({"name": "opengrok", "status": "ok", "message": server})
    except Exception as exc:  # noqa: BLE001 - report failures as data
        emit({"name": "opengrok", "status": "error", "message": str(exc)})


def _add_search_parser(sub: Any, name: str, help_text: str, func: Any) -> None:
    p = sub.add_parser(name, help=help_text)
    p.add_argument("query")
    p.add_argument("--projects", action="append", default=None, help="repeatable; omit for all")
    p.add_argument("--max-results", type=int, default=100)
    p.set_defaults(func=func)


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone OpenGrok query CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-projects", help="list indexed projects").set_defaults(
        func=cmd_list_projects
    )
    _add_search_parser(sub, "search-code", "full-text code search", cmd_search_code)
    _add_search_parser(sub, "search-definition", "search definitions", cmd_search_definition)
    _add_search_parser(sub, "search-symbol", "search symbol references", cmd_search_symbol)
    _add_search_parser(sub, "search-path", "search files/dirs by path", cmd_search_path)
    _add_search_parser(sub, "search-history", "full-text search over commit history", cmd_search_history)

    p = sub.add_parser("read-file", help="read one source file")
    p.add_argument("file_path")
    p.add_argument("--project", default=None)
    p.set_defaults(func=cmd_read_file)

    p = sub.add_parser("file-history", help="revision history for one file")
    p.add_argument("file_path")
    p.add_argument("--project", default=None)
    p.add_argument("--max-results", type=int, default=50)
    p.set_defaults(func=cmd_file_history)

    sub.add_parser("health", help="check connectivity").set_defaults(func=cmd_health)

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
