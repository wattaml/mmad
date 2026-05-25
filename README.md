# mm-mediadebug — 多媒体 Jira 调试工作流

一整套可复用的 skill，用于多媒体 Jira Issue 的自动化信息采集、代码分析、日志排查。

## 前置条件

- Python 3 + [uv](https://docs.astral.sh/uv/)
- 各服务网络可达（Jira / Confluence / Gerrit / OpenGrok 内网）
- 不再需要对应的 MCP，skills 已提供

## 安装

```bash
cp -r skills /path/to/your/project/
```

## 配置凭证（环境变量）

凭证只从**环境变量**读取，脚本不读 `.env`。建议把变量写进你的 **shell 配置文件**，这样新开的 shell / 启动的 agent 都会自动继承——这是最稳的方式：agent 进程的环境在启动时就固定，启动后再设的变量当前会话读不到，需要重开 agent。

全部环境变量：

| 变量 | 服务 | 必需 | 说明 |
|---|---|---|---|
| `JIRA_SERVER` | Jira | 是 | Jira 地址，如 `https://jira.amlogic.com/`；别名 `JIRA_URL` |
| `JIRA_USERNAME` | Jira | 是 | 用户名；别名 `JIRA_USER` |
| `JIRA_PASSWORD` | Jira | 是 | 密码或 API token |
| `CONFLUENCE_SERVER` | Confluence | 是 | Confluence 地址，如 `https://confluence.amlogic.com/` |
| `CONFLUENCE_TOKEN` | Confluence | 二选一（推荐） | Personal Access Token |
| `CONFLUENCE_USERNAME` | Confluence | 二选一 | 基础认证用户名（无 `CONFLUENCE_TOKEN` 时用） |
| `CONFLUENCE_PASSWORD` | Confluence | 二选一 | 基础认证密码（无 `CONFLUENCE_TOKEN` 时用） |
| `GERRIT_SERVER` | Gerrit | 是 | Gerrit 地址，如 `https://scgit.amlogic.com/` |
| `GERRIT_USERNAME` | Gerrit | 是 | 用户名 |
| `GERRIT_PASSWORD` | Gerrit | 是 | Gerrit → Settings → HTTP Credentials 生成的 HTTP 密码（不是登录密码） |
| `OPENGROK_SERVER` | OpenGrok | 是 | OpenGrok 地址，如 `http://opengrok-linux.amlogic.com:7892/source/`；无需账号密码 |

下面示例用 Confluence 的 PAT（`CONFLUENCE_TOKEN`）；若改用基础认证，把 `CONFLUENCE_TOKEN` 那行换成 `CONFLUENCE_USERNAME` + `CONFLUENCE_PASSWORD` 两行即可。

**Linux / macOS** —— 写进 `~/.zshrc` 或 `~/.bashrc`：

```bash
export JIRA_SERVER=https://jira.amlogic.com/
export JIRA_USERNAME=<your-username>
export JIRA_PASSWORD=<your-password>

export CONFLUENCE_SERVER=https://confluence.amlogic.com/
export CONFLUENCE_TOKEN=<your-token>
# 或基础认证（无 PAT 时，二选一）：
# export CONFLUENCE_USERNAME=<your-username>
# export CONFLUENCE_PASSWORD=<your-password>

export GERRIT_SERVER=https://scgit.amlogic.com/
export GERRIT_USERNAME=<your-username>
export GERRIT_PASSWORD=<your-http-password>

export OPENGROK_SERVER=http://opengrok-linux.amlogic.com:7892/source/
```

写好后 `source ~/.zshrc`（或 `~/.bashrc`，或直接重开终端），再启动 agent。

**Windows（PowerShell）** —— 运行 `notepad $PROFILE` 把下面内容写进 PowerShell profile：

```powershell
$env:JIRA_SERVER = "https://jira.amlogic.com/"
$env:JIRA_USERNAME = "<your-username>"
$env:JIRA_PASSWORD = "<your-password>"

$env:CONFLUENCE_SERVER = "https://confluence.amlogic.com/"
$env:CONFLUENCE_TOKEN = "<your-token>"
# 或基础认证（无 PAT 时，二选一）：
# $env:CONFLUENCE_USERNAME = "<your-username>"
# $env:CONFLUENCE_PASSWORD = "<your-password>"

$env:GERRIT_SERVER = "https://scgit.amlogic.com/"
$env:GERRIT_USERNAME = "<your-username>"
$env:GERRIT_PASSWORD = "<your-http-password>"

$env:OPENGROK_SERVER = "http://opengrok-linux.amlogic.com:7892/source/"
```

写好后重开 PowerShell 让 profile 生效，再启动 agent。也可以用 `setx` 持久化到用户级环境变量（对**新开**的进程生效，当前窗口不生效）：

```powershell
setx JIRA_SERVER "https://jira.amlogic.com/"
setx JIRA_USERNAME "<your-username>"
# ……其余变量同理
```

> `GERRIT_PASSWORD` 是 Gerrit → Settings → HTTP Credentials 生成的 HTTP 密码（不是登录密码）。
> Confluence 优先使用 Personal Access Token（`CONFLUENCE_TOKEN`），没有时才回退到 `CONFLUENCE_USERNAME`+`CONFLUENCE_PASSWORD`。OpenGrok 无需凭证。

## 配置 memory MCP 服务

方式一（推荐）：

```bash
npx add-mcp --global --name memory -t http http://10.68.38.87:8765/mcp
```

方式二，在 MCP 配置中添加：

```json
{ "memory": { "url": "http://10.68.38.87:8765/mcp" } }
```

## 预分析代码（可选）

用 codebase-onboarding 分析自己的代码库，生成 AGENTS.md。

## 搭建工作目录

建议在运行 `mmad-jira-analyzer` 前，创建一个目录专用于分析某个jira。

```bash
export ISSUE=SWPL-XXXXX
mkdir -p ~/jira/$ISSUE && cd ~/jira/$ISSUE
ln -s /path/to/your/code ./         # 如果有需要agent读取、修改、调试的代码库，软链接过来
```

## 使用流程

说"分析 $ISSUE"，它会自动：

1. 拉取 Jira 信息、描述、评论，下载附件
2. 查询 Confluence 文档，提取模块知识
3. 搜索 OpenGrok 代码，定位日志打印点/错误码/关键函数
4. 分析日志文件，追溯异常链条
5. 查询 memory 历史经验，寻找相似案例
6. 迭代 "修改代码 → 编译 → 测试" 直到解决
7. 沉淀可复用经验到 memory

分析过程中自动维护 `JIRA.md` 和 `docs/` 追踪文档。

## 技能一览

| Skill | 作用 | 触发场景 |
|---|---|---|
| mmad-jira-analyzer | Jira Issue 深度根因分析 | 用户说"分析 $ISSUE" |
| mmad-tools | Jira/Confluence/Gerrit/OpenGrok 命令行查询与写入 | 脚本化查询、下载附件、搭建工作区；写操作（评论/流转/建改页面/review 打分）需用户确认 |
| mmad-memory | 长期记忆库，沉淀可复用经验 | 保存/搜索分析结论、代码定位 |
| mmad-codebase-onboarding | 代码库入门文档生成 | 接手新项目、生成 AGENTS.md |
| mmad-grill-with-docs | 架构决策文档验证 | 挑战计划、打磨术语、更新 CONTEXT.md/ADR |
| mmad-gerrit-commit | 按 Amlogic 格式提交代码到 Gerrit | 推送本地改动、写 PD#JIRA 提交信息、push 到 refs/for/<branch> |
| mmad-handoff | 把当前对话压缩成交接文档 | 换 agent / 新会话接力时 |

