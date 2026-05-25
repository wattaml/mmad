---
name: mmad-tools
description: 通过命令行查询 Confluence、Jira、Gerrit、OpenGrok。当需要查 Jira issue/评论/附件、Confluence 文档/附件、Gerrit change/diff/文件、或 OpenGrok 代码搜索时使用。每个服务对应 scripts/ 下一个可独立执行的脚本，凭证从环境变量读取，结果以 JSON 打印到 stdout。
---

# CLI Tools — Confluence / Jira / Gerrit / OpenGrok

`scripts/` 下有 4 个互相独立的命令行脚本，分别封装一个服务的只读查询能力：

| 脚本 | 服务 | 依赖 | 环境变量 | 说明 |
| --- | --- | --- | --- | --- |
| `mmad_jira_tool.py` | Jira | `jira` | `JIRA_SERVER`(或`JIRA_URL`) / `JIRA_USERNAME`(或`JIRA_USER`) / `JIRA_PASSWORD` | — |
| `mmad_confluence_tool.py` | Confluence | `atlassian-python-api`, `httpx` | `CONFLUENCE_SERVER` + (`CONFLUENCE_TOKEN` 或 `CONFLUENCE_USERNAME`+`CONFLUENCE_PASSWORD`) | 优先使用 Personal Access Token（`CONFLUENCE_TOKEN`），没有时才回退到用户名密码 |
| `mmad_gerrit_tool.py` | Gerrit | `httpx` | `GERRIT_SERVER` / `GERRIT_USERNAME` / `GERRIT_PASSWORD` | `GERRIT_PASSWORD` 是 Gerrit → Settings → HTTP Credentials 生成的 HTTP 密码，不是登录密码 |
| `mmad_opengrok_tool.py` | OpenGrok | `httpx` | `OPENGROK_SERVER` | 无需账号密码 |

## 脚本用法

- 每个脚本都是自包含的（不 import 其它脚本，也不依赖 `aiyo`/`ext` 包），可单独执行。
- **优先用 `uv` 执行**：脚本头部内嵌了 PEP 723 依赖声明，`uv run scripts/<脚本>.py <子命令> [参数]` 会自动按声明把依赖装进临时环境再运行，无需手动 `pip install`，也不依赖任何已激活的 venv。下面所有示例都以 `uv run` 给出。
- 没有 `uv` 时才回退到普通解释器：`python3 scripts/<脚本>.py ...`，此时需自行保证 `jira` / `atlassian-python-api` / `httpx` 等依赖已装在该解释器里。
- 正常结果是 JSON，打印到 **stdout**；日志和错误打印到 **stderr**，方便管道里只取 JSON。
- 每个脚本都有 `-h`，每个子命令也有 `-h`。
- **读 vs 写**：各脚本既有只读查询子命令，也有会改动远端的写子命令（在下文各服务里单列为「写」分组、`-h` 里标 `[write]`）。涉及写的有：Jira 的 `add-comment` / `do-transition` / `assign`、Confluence 的 `add-comment` / `create-page` / `update-page`、Gerrit 的 `set-review`；OpenGrok 全为只读。
- **写子命令必须先经用户确认**：调用任何写子命令（发评论、流转状态、指派、建/改页面、打分 review 等）前，**必须先把要执行的完整命令、目标对象（issue / page / change）和将写入的内容告诉用户，得到明确同意后再执行**，且一次只做用户确认过的那一步，不要自动或批量触发写操作。只读子命令无需确认。

## 前置要求（Prerequisite）：先确保 `health` 通过

凭证**只从环境变量读取**（具体变量见上表），脚本本身不会写 `.env`。**在调用任何子命令之前，先跑一次目标服务的 `health` 确认凭证和连通性。** 缺失或无效时脚本的行为是可预期的：

- 缺少必需变量：`_settings()` 直接以非 0 退出，stderr 打印 `missing required setting: ...` 或 `missing credentials: ...`。
- 变量齐全但连接/认证失败：`health` 返回 `{"status": "error", "message": ...}`。

**agent 的进程环境在启动时就固定了**——用户后续在终端里 `export` 的变量，本会话的 Bash 子进程读不到。所以 `health` 失败时不要在本会话里折腾，也**不要静默放弃、不要猜测或编造凭证、不要在凭证未就绪时硬跑业务子命令**。按以下步骤处理：

1. 对照上表确定该服务缺哪些变量，并向用户说明用途。
2. **要求用户先把这些变量设好，然后重新打开 agent**；只要新会话能继承到这些环境变量即可，具体方式由用户自行决定（写入 shell profile、启动前手动 `export`、放进被 profile source 的 `.env` 等都行，仅作建议）。** 不要把密码 / token 回显到对话里。**
3. 用户重启 agent 后，重新跑一次 `health`，确认 `status: ok` 再继续后面的子命令。
4. 仍失败则把 `health` 的 `message` 原样反馈给用户，并提示常见原因（网络不可达、密码过期、变量名写错或没被 profile source 到、Gerrit 用的是 HTTP Credentials 密码而非登录密码、Confluence 优先用 PAT），不要反复重试。

## Jira — `mmad_jira_tool.py`

```bash
# 读
uv run scripts/mmad_jira_tool.py search "project = FOO AND status = Open" --max-results 20
uv run scripts/mmad_jira_tool.py search "key = FOO-123" --fields summary,status,assignee
uv run scripts/mmad_jira_tool.py get FOO-123
uv run scripts/mmad_jira_tool.py comments FOO-123
uv run scripts/mmad_jira_tool.py links FOO-123               # 关联 issue / 父子任务
uv run scripts/mmad_jira_tool.py changelog FOO-123           # 字段变更历史
uv run scripts/mmad_jira_tool.py watchers FOO-123
uv run scripts/mmad_jira_tool.py attachments FOO-123
uv run scripts/mmad_jira_tool.py download-attachment 45678 --save-path ./out.zip
uv run scripts/mmad_jira_tool.py transitions FOO-123
uv run scripts/mmad_jira_tool.py projects
uv run scripts/mmad_jira_tool.py setup FOO-123          # 在当前目录搭建分析工作区
uv run scripts/mmad_jira_tool.py health
# 写
uv run scripts/mmad_jira_tool.py add-comment FOO-123 "Root cause: ..."
uv run scripts/mmad_jira_tool.py do-transition FOO-123 "In Progress" --comment "开始排查"
uv run scripts/mmad_jira_tool.py assign FOO-123 jdoe          # "-" 取消指派，"auto" 用默认
```

子命令（读）：`search` `get` `comments` `links` `changelog` `watchers` `attachments` `download-attachment` `transitions` `projects` `setup` `health`。
子命令（写）：`add-comment` `do-transition`（值可用 transition 名或 id，见 `transitions`） `assign`。

`setup <issue_key>` 在**当前目录**铺开一个 Jira 分析工作区（供 `mmad-jira-analyzer` skill 使用）：拉取 issue 元信息/描述/评论写入 `docs/issue.md`，下载附件到 `attachments/`（压缩包自动解压到 `attachments/extracted/`，加 `--no-extract` 可关闭）并生成 `docs/attachments.md`，再补齐 `JIRA.md`、`docs/timeline.md`、`docs/evidence.md`、`docs/next-steps.md` 骨架（已存在的不覆盖）。它不打印 JSON，而是打印一行 `workspace ready: ...` 状态。

## Confluence — `mmad_confluence_tool.py`

优先用 Personal Access Token（`CONFLUENCE_TOKEN`）；否则回退到 `CONFLUENCE_USERNAME`+`CONFLUENCE_PASSWORD` 基础认证。

```bash
# 读
uv run scripts/mmad_confluence_tool.py search "space = ENG AND title ~ 'release'" --limit 10
uv run scripts/mmad_confluence_tool.py get-page 665519915
uv run scripts/mmad_confluence_tool.py get-page-by-title ENG "Release Notes"
uv run scripts/mmad_confluence_tool.py spaces --limit 25
uv run scripts/mmad_confluence_tool.py children 665519915 --limit 20
uv run scripts/mmad_confluence_tool.py descendants 665519915 --limit 200   # 递归列所有子孙页
uv run scripts/mmad_confluence_tool.py labels 665519915
uv run scripts/mmad_confluence_tool.py comments 665519915
uv run scripts/mmad_confluence_tool.py attachments 665519915
uv run scripts/mmad_confluence_tool.py download-attachment 665519915 att123 --save-path ./f.pdf
uv run scripts/mmad_confluence_tool.py health
# 写
uv run scripts/mmad_confluence_tool.py add-comment 665519915 --body "关联 SWPL-123 分析"
uv run scripts/mmad_confluence_tool.py create-page ENG "New Page" --body "<p>hi</p>" --parent-id 665519915
uv run scripts/mmad_confluence_tool.py update-page 665519915 --body-file ./body.html
```

子命令（读）：`search` `get-page` `get-page-by-title` `spaces` `children` `descendants` `labels` `comments` `attachments` `download-attachment` `health`。
子命令（写）：`add-comment` `create-page` `update-page`。正文用 `--body`（直接传内容）或 `--body-file`（从文件读），默认 `storage`（HTML）表示法。

## Gerrit — `mmad_gerrit_tool.py`

走认证 REST 端点（`/a/...`），使用 HTTP Digest 认证；`GERRIT_PASSWORD` 是 Gerrit → Settings → HTTP Credentials 里生成的 HTTP 密码，不是登录密码。

```bash
# 读
uv run scripts/mmad_gerrit_tool.py list-changes --query "status:open" --limit 25
uv run scripts/mmad_gerrit_tool.py get-change 12345
uv run scripts/mmad_gerrit_tool.py get-change-detail 12345
uv run scripts/mmad_gerrit_tool.py get-change-diff 12345 --revision current
uv run scripts/mmad_gerrit_tool.py get-change-messages 12345
uv run scripts/mmad_gerrit_tool.py get-change-comments 12345        # 行级 review 评论
uv run scripts/mmad_gerrit_tool.py get-patch 12345 --revision current
uv run scripts/mmad_gerrit_tool.py related-changes 12345           # 同一关系链上的 change
uv run scripts/mmad_gerrit_tool.py get-file-content 12345 path/to/file.c
uv run scripts/mmad_gerrit_tool.py list-projects --prefix amlogic/ --limit 100
uv run scripts/mmad_gerrit_tool.py project-branches amlogic/foo --limit 50
uv run scripts/mmad_gerrit_tool.py project-tags amlogic/foo --limit 50
uv run scripts/mmad_gerrit_tool.py health
# 写
uv run scripts/mmad_gerrit_tool.py set-review 12345 --message "LGTM" --label Code-Review=+1
```

子命令（读）：`list-changes` `get-change` `get-change-detail` `get-change-diff` `get-change-messages` `get-change-comments` `get-patch` `related-changes` `get-file-content` `list-projects` `project-branches` `project-tags` `health`。
子命令（写）：`set-review`（`--message` 发评论、`--label NAME=VALUE` 打分，可重复；默认作用于 `current` revision）。
`change_id` 可以是 change 号或完整 Change-Id。`get-change-diff` 最多返回前 20 个文件。

## OpenGrok — `mmad_opengrok_tool.py`

无需账号密码，只需 `OPENGROK_SERVER`。先尝试 REST API，不可用时回退到抓取 HTML 搜索结果页。

OpenGrok 本身是只读代码索引，本脚本全为只读，无写操作。

```bash
uv run scripts/mmad_opengrok_tool.py list-projects
uv run scripts/mmad_opengrok_tool.py search-code "amlvideo_open" --projects kernel --max-results 50
uv run scripts/mmad_opengrok_tool.py search-definition "vdec_init"
uv run scripts/mmad_opengrok_tool.py search-symbol "g_vdec"
uv run scripts/mmad_opengrok_tool.py search-path "drivers/media"
uv run scripts/mmad_opengrok_tool.py search-history "fix vdec deadlock" --projects kernel   # 提交历史全文搜索
uv run scripts/mmad_opengrok_tool.py read-file /kernel/drivers/foo.c
uv run scripts/mmad_opengrok_tool.py read-file drivers/foo.c --project kernel
uv run scripts/mmad_opengrok_tool.py file-history /kernel/drivers/foo.c   # 单文件修订历史
uv run scripts/mmad_opengrok_tool.py health
```

子命令：`list-projects` `search-code` `search-definition` `search-symbol` `search-path` `search-history` `read-file` `file-history` `health`。

- `--projects` 可重复多次；省略则搜索所有项目。
- `read-file` / `file-history` 的路径要么带项目前缀（`/project/path/to/file`），要么用 `--project` 指定项目。

## 使用建议

1. **本 skill 是操作 Confluence / Jira / Gerrit / OpenGrok 的首选方式，优先级高于 MCP 工具**。agent 在任何场景（如 `mmad-jira-analyzer`）使用这些服务时，都应优先调用本 skill 的脚本；仅在脚本不可用时才降级到 MCP 或其他方式。
2. 调用任何子命令前先按上文《前置要求：先确保 `health` 通过》确认连通性和凭证；`health` 失败或脚本报缺少环境变量时，先向用户索取环境变量再继续。
3. 先用 `search`/`list-*` 拿到 ID，再用 `get-*` 取详情，避免一次拉太多。
4. stdout 是 JSON，可直接接 `| jq ...` 提取字段。
5. 默认 `uv run scripts/<脚本>.py ...`，由 uv 按脚本内的 PEP 723 声明备好依赖；仅在没有 uv 时才回退到自带依赖的解释器（如 `<venv>/bin/python scripts/mmad_jira_tool.py ...`）。
6. **写子命令（`add-comment` / `do-transition` / `assign` / `create-page` / `update-page` / `set-review`）会改动远端，调用前必须按《脚本用法》的要求先向用户确认。** 只读查询不必确认。
