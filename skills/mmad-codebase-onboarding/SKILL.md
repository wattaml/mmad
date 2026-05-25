---
name: mmad-codebase-onboarding
description: 分析陌生代码库，并创建或更新 AGENTS.md 作为主要的 agent 通用入门文档；更深入的代码库结构写入 docs/codebase/，难以回滚的架构决策写入 docs/adr/。当用户要接手新项目、为任意编码 agent 准备仓库、生成代码库地图，或同步 CLAUDE.md、GEMINI.md、Copilot instructions、Cursor rules 等工具专用说明到 AGENTS.md 时使用。
---

# Codebase Onboarding

系统化探索陌生代码库，并产出能帮助后续 agent 或开发者快速理解、调试、修改项目的文档。

这个 skill 是 agent-neutral 的。除非仓库已有工具专用说明，或用户明确要求某个工具，否则不要默认绑定 Claude Code、Codex、Gemini、Cursor、Copilot 等具体 agent。

## 什么时候使用

- 第一次打开、接手或继承一个项目
- 用户说“帮我理解这个代码库”
- 用户说“onboard me”、“map this repo”、“walk me through this repo”
- 用户希望为后续代码分析沉淀可复用文档
- 用户要求生成或更新 `AGENTS.md`
- 用户要求同步工具专用说明，例如 `CLAUDE.md`、`GEMINI.md`、`.cursorrules`、`.github/copilot-instructions.md`

## 核心原则

不要写一次性的代码导览。要写一份紧凑、有证据支撑的代码库地图，回答这些问题：

- 程序从哪里开始执行？
- 主要请求、数据、事件或命令流如何穿过系统？
- 常见修改应该从哪里下手？
- 修改后用什么命令验证？
- 哪些本地约定必须保留？

## Phase 1: 快速侦察

先收集结构信号，不要通读所有文件。尽量并行检查：

```text
1. 包和构建清单
   package.json, go.mod, Cargo.toml, pyproject.toml, pom.xml, build.gradle,
   Gemfile, composer.json, mix.exs, pubspec.yaml, CMakeLists.txt, Makefile

2. 框架和平台特征
   next.config.*, nuxt.config.*, angular.json, vite.config.*, django settings,
   flask/fastapi 入口, rails config, spring config, embedded/firmware 构建文件

3. 入口点
   main.*, index.*, app.*, server.*, cmd/, src/main/, bin/, tools/, scripts/

4. 目录快照
   查看 2-3 层目录结构，忽略 .git, node_modules, vendor, dist, build,
   __pycache__, .next, target, out, generated artifacts

5. 配置和工具链
   lint/format 配置, type config, Dockerfile, docker-compose*, CI workflows,
   .env.example, build scripts, test config

6. 现有文档和 agent 指令
   README*, docs/, CONTEXT.md, CONTEXT-MAP.md, AGENTS.md, CLAUDE.md,
   GEMINI.md, .cursorrules, .github/copilot-instructions.md
```

优先使用 `rg --files` 和有目标的 `rg` 搜索。只在信号不明确或路径关键时选择性阅读源码。

`CONTEXT.md` 和 `CONTEXT-MAP.md` 可以作为领域背景读取，但本 skill 不创建、不维护它们。领域词汇建模属于 `mmad-grill-with-docs`。

## Phase 2: 架构映射

识别以下内容：

**技术栈**

- 主要语言和版本约束
- 框架和关键库
- 数据库、存储、ORM、消息总线、硬件或平台 API
- 构建工具、包管理器、CI/CD

**架构形态**

- 单体、monorepo、服务、库、CLI、固件树、插件或混合仓库
- 前后端分离、全栈、嵌入式、平台集成等边界
- 接口风格：REST、GraphQL、gRPC、RPC、CLI、事件驱动、文件驱动、硬件边界
- 生成代码和外部集成边界

**关键目录**

把顶层目录和重要嵌套目录映射到职责：

```text
src/api/        -> API handlers
src/domain/     -> business rules
src/lib/        -> shared utilities
tests/          -> automated tests
scripts/        -> local automation
docs/           -> project documentation
```

**主流程**

至少追踪一个代表性流程：

- request -> response
- CLI command -> side effect
- event/log/input file -> processing result
- test fixture -> assertion
- hardware/system callback -> module behavior

用文件路径、函数名、类名作为证据，不要只写抽象判断。

## Phase 3: 约定识别

记录后续修改必须遵守的模式：

**代码约定**

- 文件命名和符号命名
- 模块边界和依赖方向
- 错误处理和日志风格
- 配置加载、feature flag、运行时属性
- async、线程、状态管理模式

**测试约定**

- 测试框架和命令
- 测试文件命名和 fixture 布局
- 单元测试、集成测试、端到端测试的边界
- 如何运行聚焦测试

**工作流约定**

- build、run、lint、format、static check 命令
- 分支、提交、评审约定；只有当文档或 git history 能证明时才记录

如果 git history 不可用或太浅，明确写出来，不要猜。

## Phase 4: 生成 AGENTS.md

### 主产物：AGENTS.md

创建或更新：

```text
AGENTS.md
```

如果 `AGENTS.md` 已存在，先阅读再合并。除非现有说明明显过期或与代码相矛盾，否则保留原有约定。如果仓库存在嵌套 `AGENTS.md`，更新适用于当前 scope 的文件，并说明 scope。

推荐结构：

```md
# Agent Onboarding: [Project Name]

## Purpose
[2-3 句话说明这个项目做什么、服务谁]

## Fast Start
- Setup: `...`
- Build: `...`
- Test: `...`
- Run/debug: `...`

## Work Rules For Agents
- [仓库特定编辑约束]
- [应避免修改的文件或目录]
- [评审、提交、验证要求]

## Tech Stack
| Layer | Technology | Version/Notes |
|---|---|---|

## Architecture At A Glance
[短描述；如果图能显著降低理解成本，可放 Mermaid]

## Entry Points
| Path | Role | Notes |
|---|---|---|

## Module Map
| Path | Responsibility | Key Dependencies |
|---|---|---|

## Main Flows
### [Flow Name]
1. `path:function` receives ...
2. `path:function` validates/transforms ...
3. `path:function` persists/emits/returns ...

## Data And Configuration
- Models/schemas:
- Config sources:
- Runtime state:

## Testing And Verification
- Test commands:
- Test layout:
- Useful focused checks:

## Change Guide
| I want to... | Start here | Verify with |
|---|---|---|

## Conventions To Preserve
- ...

## Known Unknowns
- ...
```

保持可扫描。一般控制在 120-220 行；大型仓库可以拆分。

### 支持文档：docs/codebase 和 docs/adr

当 `AGENTS.md` 会过长、架构地图需要更持久的细节，或仓库已有匹配文档结构时，创建支持文档：

- `docs/codebase/README.md`: 更深入的架构地图、主流程、模块说明
- `docs/adr/NNNN-*.md`: 难以回滚的架构决策

如果存在支持文档，`AGENTS.md` 仍然是入口，并链接过去：

```md
## Deeper References
- Architecture map: `docs/codebase/README.md`
- Architecture decisions: `docs/adr/`
```

如果需要整理领域词汇，交给 `mmad-grill-with-docs`。

### 工具专用说明文件

如果仓库已有 `CLAUDE.md`、`GEMINI.md`、`.cursorrules`、`.github/copilot-instructions.md` 等文件，保持它们简短，并同步指向 `AGENTS.md`。

如果用户明确要求某个工具的说明文件，可以创建或更新对应文件，但 `AGENTS.md` 仍是通用主入口。

## 最佳实践

1. **不要通读所有文件**：先用文件清单和搜索建立地图，再选择性阅读。
2. **验证，不猜测**：配置名和实际代码冲突时，优先相信代表性代码。
3. **尊重现有文档**：增强 `AGENTS.md` 和当前文档，不创建互相竞争的版本。
4. **保持 agent-neutral**：除非工具专用文件需要，否则使用“agent”或“developer”这样的通用表述。
5. **标注未知项**：写“无法确定测试框架”比写错命令更好。
6. **保护用户已有工作**：改已有说明前先读，合并而不是覆盖。

## 避免的问题

- 默认只创建 `CLAUDE.md` 或其他工具专用文件
- 把代码库地图写成 README 的复述
- 罗列所有依赖，而不是说明影响架构和开发方式的依赖
- 只描述显而易见的目录名，不解释职责
- 编造 manifests 或 docs 里不存在的命令
- 写成长篇叙述，导致后续 agent 不能快速扫描

## 完成标准

结束前确认：

- `AGENTS.md` 已存在；如果没有写入，要说明原因。
- 所有引用的文件和命令都真实存在、已验证，或明确标注为 inferred。
- 现有工具专用说明文件已保留，并在需要时链接到 `AGENTS.md`。
- 最终回复列出修改文件和最有价值的未解问题。
