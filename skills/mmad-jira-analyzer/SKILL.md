---
name: mmad-jira-analyzer
description: 对 Jira Issue 进行深度根因分析并给出修复建议。当用户要求分析某个 Jira issue 时使用此 skill，维护当前分析工作区的 JIRA.md 和 docs/xxx，支持下载 Jira 附件、查询 Confluence 和 OpenGrok、分析日志、定位可疑代码，并用 mmad-memory 沉淀可复用经验。
argument-hint: "<ISSUE-KEY>(如 SWPL-12345)"
---

# Jira Issue 深度分析

## 触发条件

当用户要求以下操作时使用此 skill：

- "分析 Jira issue XXX"
- "帮我看看这个 Jira 问题"
- "对 ISSUE-123 进行根因分析"
- "调查这个 bug"

## 核心步骤

- 用 `mmad-tools` 建立 Jira 分析工作区，确认各种分析工具可用
- 用 `mmad-grill-with-docs` 跟用户拉通目标、对齐概念：读完 issue 基本信息后，先和用户对齐「这次分析要解决到什么程度」以及领域术语，再深入
- 查 `mmad-memory` 历史经验：建好工作区后先做一次初筛，分析拿到错误码/函数名后再深入检索
- 参考外部资料，比如 Confluence 文档、OpenGrok 代码
- 查 Gerrit 变更，排查可疑文件/模块的近期改动与相关 CL
- 分析附件日志，沿时间线定位异常链
- 读本地代码的 AGENTS.md, 必要时使用 `codebase-onboarding` 建立代码库认知
- **核心工作流**：修改 → 构建 → 验证，循环迭代直到解决问题。修改由你完成；构建不要自行尝试，先询问构建命令；验证后需要拉取新的 attachments（日志等）继续分析。每轮 loop 后都更新 JIRA.md。
- 整理最终结论
- 沉淀 `mmad-memory`


## Prerequests

- 开工前先跑 `mmad-tools` 脚本的 `health` 确认连通性和凭证；失败就按 `mmad-tools` 的《health 失败 → 向用户索取环境变量》索取并配置后重试，不要带着坏凭证继续往下做
- 关于jira处理的一些关键信息，如果jira里没有提供，需要向用户确认，包括：chipset model（如S905X4）、tdk version（如tdk-v3.18）、arch（arm or aarch）等。确认后立即写进 `JIRA.md` 的 Facts，避免每轮重问，也方便沉淀 memory 时带上环境信息

## 步骤详解

### 建立分析工作区

先从用户请求中识别 issue key。若当前目录已经是该 issue 的分析工作区，先读取 `JIRA.md` 和 `docs/` 恢复进展。

分析目录下包含三类内容：

1. `JIRA.md`：当前 issue 的分析总入口
2. `docs/xxx`：分析过程中的各类文档和证据
3. 代码：被分析的本地代码

工作区结构：

```text
JIRA.md                    # 当前 issue 的分析总入口
attachments/               # 原始附件和解压后的附件
docs/
├── issue.md               # Jira 元信息、描述、关键评论
├── attachments.md         # 附件清单和状态
├── timeline.md            # 时间线
├── evidence.md            # 日志、代码、命令、链接证据
└── next-steps.md          # 后续动作和阻塞项
代码/                       # 被分析的本地代码
```

`JIRA.md` 是当前分析的活文档，保持短而最新：

```md
# PROJ-123 Jira Analysis

## Current State

一句话说明当前定位到哪里。

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
```

建立工作区优先调用 `mmad-tools` skill 的 Jira 脚本：在分析目录下执行 `uv run <skills>/mmad-tools/scripts/mmad_jira_tool.py setup <ISSUE-KEY>`（优先 `uv run`，按脚本内 PEP 723 声明自动备依赖；无 uv 时回退 `python3`，需自行装好 `jira` 依赖），它会建目录、拉取 Jira 元信息/描述/评论、下载附件（压缩包自动解压），并生成 `JIRA.md` 和 `docs/` 骨架（已存在的不覆盖）。运行前确保环境里已有 `JIRA_SERVER`/`JIRA_USERNAME`/`JIRA_PASSWORD`。如果该脚本不可用，直接用当前可用的 Jira/CLI/MCP 能力完成同样的工作。

工作区建好、读完 issue 基本信息后，**先做一次 memory 初筛**：用 issue key + components + 现象描述调用 `memory_search`（`tags="jira,analysis"`），看有没有近乎重复、已解决的历史案例。命中就用它指导后面 Confluence/OpenGrok/Gerrit/log 的方向，少走弯路；没命中也只花很小代价。更精确的第二轮检索（带错误码/函数名/模块名）放在《查询memory历史经验》。

### 跟用户拉通目标、对齐概念

深入分析前，先用 `mmad-grill-with-docs` skill 和用户做一轮对齐——避免方向跑偏、术语理解不一致后返工。重点拉通两件事：

- **目标**：这次到底要交付到什么程度（定位根因？给出可验证的修复？还是只缩小到某一层），有没有时间/版本/优先级约束，怎样算「完成」。
- **概念**：issue 描述、日志、用户口中的关键术语和现象的确切含义，确认双方对同一个词的理解一致（如具体的模块名、状态、错误码、复现条件）。

执行要求：

- 把对齐后的目标和关键术语写进 `JIRA.md` 的 Facts / Open Questions；与术语相关的领域定义按 `mmad-grill-with-docs` 的约定沉淀（如 `CONTEXT.md`），不要混进 `JIRA.md`。
- 这一步偏轻量：issue 已经很明确时快速确认即可，不要为对齐而对齐；issue 模糊或跨模块时再多花时间。

### 查 Confluence 模块文档

优先调用 `mmad-tools` skill 的 Confluence 脚本完成页面搜索、子页面列表和内容读取；如果该脚本不可用，再用当前可用的 MCP 或其他方式。

在 "MMAD+-+Docs" 页面（ID: 665519915）下：

1. 获取子页面列表。
2. 根据 Issue 的 components 匹配模块名。
3. 读取匹配模块的文档内容。
4. 提取调试步骤、错误码含义、常见原因、关键词。

执行要求：

- 先按 Jira components、标题关键词、日志中的模块名匹配页面。
- 如果没有精确匹配，找相邻模块、公共调试指南、历史分析经验。
- 至少记录页面 ID、页面标题、为什么相关。
- 将页面 ID、标题、链接、相关原因和提取出的关键词写入 `docs/evidence.md`。
- 不要把整页文档照抄进记忆，只保留后续分析要用的知识点和链接。

### 查 OpenGrok 代码

优先调用 `mmad-tools` skill 的 OpenGrok 脚本完成代码搜索、定义查找和文件读取；如果该脚本不可用，再用当前可用的 MCP 或其他方式。

根据 Jira 信息、Confluence 关键词、日志中的函数名/模块名/错误码，调用 OpenGrok 查相关代码。

优先关注yocto-sdk下aml-comp/multimedia的代码，其全景图参考 [multimedia-linux](./references/multimedia-linux.md)

优先查这些内容：

- 日志打印点
- 错误码定义和返回路径
- 关键函数的调用链
- 与 Jira 组件直接相关的模块

每轮查询都要带着明确问题，例如“这个错误是谁打印的”“这个返回码在哪些分支返回”。

将代码文件、函数、行号、分支条件、调用链和排除项写入 `docs/evidence.md`。如果发现代码库结构信息对后续所有问题都可复用，才考虑更新项目级 `AGENTS.md` 或 `docs/codebase/`；不要把单个 Jira 的临时分析写进去。

### 查 Gerrit 变更

优先调用 `mmad-tools` skill 的 Gerrit 脚本完成 change 查询、diff 和评论查看；如果该脚本不可用，再用当前可用的 MCP 或其他方式。

定位到可疑文件/模块后，用 Gerrit 排查“最近的改动是不是引入点”——这对回归类问题（“上个版本还好，这个版本坏了”）往往是最快路径：

1. 按 issue key / topic / hashtag 查是否已有引用本 issue 的 change（可能是修复尝试，也可能是引入问题的提交），例如 `list-changes --query "message:SWPL-12345"`。
2. 按可疑文件/模块路径查最近合入的 change，看改动时间和现象出现时间是否吻合。
3. 对可疑 change 用 `get-change-detail` / `get-change-diff` / `get-change-messages` 看具体改了什么、谁审的、合入时间。

执行要求：

- 先用 `list-changes` 拿到 change 号，再取详情，避免一次拉太多。
- 把 change 号、subject、owner、合入时间、相关文件、与现象的时间关系写入 `docs/evidence.md`；与时间线相关的合入点写入 `docs/timeline.md`。
- change 与现象时间吻合且改了可疑路径时，作为重点假设记入 `JIRA.md`；但仍需日志/代码证据印证，不能只凭时间巧合定论。

### 分析log

优先分析 `attachments` 中 `type=log` 且 `status=downloaded` 的文件。带着文档关键词去筛日志，不要盲读全部附件。

先做两轮检索：

1. 用 Confluence 提取的模块关键词、错误码、关键函数名筛选。
2. 用通用故障词补充筛选：`error` / `fail` / `timeout` / `panic` / `exception` / `warning`。

执行要求：

- 小文件（< 200KB）可直接读取全文。
- 大文件优先用关键词过滤。
- 关注时间顺序：先出现的异常通常更接近根因，后续报错可能只是连锁反应。
- 关注组件交界处，例如 HAL / framework / driver / service 的调用边界。
- 将关键日志文件、时间戳、关键词、短摘录和判断写入 `docs/evidence.md`；时间顺序写入 `docs/timeline.md`。

### 查询memory历史经验

这是第二轮（深入）检索：用分析过程中拿到的错误码、函数名、模块名、调用链等更精确的线索，在《建立分析工作区》初筛的基础上再查一遍，并把两轮结论合并。

先从 issue key、模块名、关键词、错误码、现象描述中提取检索词，再用 `memory_search`。

执行要求：

- 至少检索一次 `tags="jira,analysis"` 的历史案例。
- 对命中的历史 issue，不要只停留在 memory 摘要；必须继续使用 Jira 工具探索 summary、description、comments、attachments 或可见元信息。
- 判断本次 issue 和历史 issue 是否同模块、同触发条件、同根因、同修复路径。
- 如果历史案例不够相似，要说明“看过但不能直接复用”的原因。
- 将可复用或排除的历史案例摘要写入 `docs/evidence.md`，并在 `JIRA.md` 中更新当前判断。

### 参考本地代码的 AGENTS.md

进入本地代码前，先读取代码根目录及相关子目录的 `AGENTS.md`，了解代码库结构、构建方式、模块职责和约定。

**如果代码库没有 `AGENTS.md`**：不要盲目全局搜索代码，先**询问用户是否用 `mmad-codebase-onboarding` skill 为该代码库建立认知**（它会生成 agent 中立的 `AGENTS.md`，作为本节依赖的代码库地图）。用户同意就先跑 `mmad-codebase-onboarding` 生成 `AGENTS.md` 再回到本节；用户拒绝则按需做最小范围的局部探索，并在 `JIRA.md` 的 Open Questions 中记录缺少代码库地图这一限制。

执行要求：

- 优先用 `AGENTS.md` 描述的目录结构和模块划分定位与 Jira 组件相关的代码，而不是盲目全局搜索。
- 把 OpenGrok / 日志中定位到的函数名、文件路径映射到本地代码，确认实际实现和分支逻辑。
- `AGENTS.md` 中记录的构建命令、测试方式、限制条件，作为下一步「核心工作流」的依据。
- 如果 `AGENTS.md` 与实际不符，在 `JIRA.md` 的 Open Questions 中记录，必要时向用户确认或重新运行 `mmad-codebase-onboarding` 更新。

### 核心工作流：修改 → 构建 → 验证

定位到可疑代码后，进入「修改代码 → 构建 → 验证」的循环，持续迭代直到问题解决：

1. **修改代码**：由你完成。基于证据链做最小化、可验证的改动，并在 `docs/evidence.md` 记录改了什么、为什么改。
2. **构建**：不要直接尝试构建。先向用户询问该模块的构建命令（可参考 `AGENTS.md`），由用户确认或执行。
3. **验证**：明确写出需要验证的现象、用例和预期结果。验证后拉取新的 attachments（如日志、截图等）继续分析下一轮。
   - 先用 `adb devices` 查询是否已连接设备。
   - 如果已连接，向用户询问是否需要由 agent 直接操作 adb 完成验证；得到同意后再执行 adb 命令。
   - 如果未连接或用户不同意，则把验证交给用户进行，等待用户回传结果。
   - **验证完成后**：如果有新的日志或附件被上传到 Jira issue，重新运行 `uv run <skills>/mmad-tools/scripts/mmad_jira_tool.py setup <ISSUE-KEY>` 或手动下载最新附件到 `attachments/`，确保工作区信息是最新的。

执行要求：

- 每完成一轮 loop（无论成功、失败还是被否定）都要更新 `JIRA.md`：当前状态、本轮改动、验证结果、下一步假设。
- 这是一个human-in-loop的过程，构建和验证可能需要由用户完成。
- 一轮验证失败要分析原因、调整假设，再进入下一轮，不要在没有证据支撑下连续猜测式修改。
- 改动和验证结果同步写入 `docs/evidence.md` 和 `docs/timeline.md`。
- 循环持续到问题被验证修复，或明确判定「当前只能定位到某一层、无法继续」为止。

### 持续维护 JIRA.md 和 docs

每得到一个稳定结论，都要更新工作区文档：

- `JIRA.md`: 当前状态、已确认事实、工作假设、下一步、开放问题。
- `docs/issue.md`: Jira 元信息、描述、关键评论和链接。
- `docs/attachments.md`: 附件状态、类型、解压位置、备注。
- `docs/timeline.md`: Jira 评论、日志时间、复现、修复、验证的时间线。
- `docs/evidence.md`: Confluence、日志、代码、命令、历史案例证据。
- `docs/next-steps.md`: 较长的行动计划、阻塞项、需要用户或其他团队补充的信息。

保持 `JIRA.md` 短小；长证据放 `docs/`。不要使用 `CONTEXT.md` 记录 Jira 分析状态。

### 整理最终结论

整理一份简短结论

- 问题概述
- 根因判断
- 关键证据
- 代码定位
- 修复建议
- 历史案例参考（若有）

要求：

- 根因要写成证据支持的陈述，避免无依据的“可能/怀疑/大概”。
- 每个关键判断后面都要跟日志或代码依据。
- 如果参考了历史 issue，要明确写出哪些案例、哪些点相似、哪些点不同。
- 如果证据不足以支持确定根因，要明确写出“当前只能定位到哪一层”。
- 不要把完整推理长文堆在结论里；详细内容应按需沉淀到 memory。
- 同步更新 `JIRA.md` 的 Current State 和 Next Steps。

### 沉淀memory

按 `mmad-memory` skill 的规范保存可复用经验。至少覆盖：

- Confluence 参考页面和用途说明
- Jira基本信息 / 评论 / 附件 / 日志定位信息
- 人员信息：Reporter、Assignee、关键评论人、相关责任团队或 reviewer
- 日期信息：Issue 创建/更新日期、关键评论日期、日志发生日期、修复或验证日期
- 可疑代码 / 搜索结果 / 变更链接 / 文件路径 / 函数名 / 行号
- 初步发现、证据对应关系、排除项
- 最终根因和修复建议

不要保存长日志、整页文档或长代码；保存摘要、定位信息和链接。

Jira 分析结果写入示例：

```python
memory_store(
    content="""SWPL-12345: Widevine provisioning failed because the TEE service returned -22 during keybox loading.

Context:
- Project/module: webOS26 DRM / Widevine
- Symptom: Playback authorization failed after provisioning.
- People: Reporter=<reporter>, Assignee=<assignee>, Key commenters=<names>, Reviewer=<reviewer>
- Dates: Created=2026-05-01, Updated=2026-05-08, Log time=2026-05-07 14:32 CST, Fix verified=2026-05-09

Evidence:
- Log: `WVCdmFactory: provisioning failed, ret=-22`
- Code: `vendor/amlogic/drm/widevine/.../KeyboxLoader.cpp::LoadKeybox`
- Jira/Gerrit/Confluence: SWPL-12345, Gerrit 123456, MMAD Docs page 665519915

Resolution:
- Validate keybox partition mount state before calling `LoadKeybox`.
""",
    metadata={
        "tags": "jira,analysis,root-cause,widevine,drm,webos26,swpl-12345,keybox",
        "type": "finding",
    },
)
```

## 关键提醒

1. 先文档、再日志、再代码，不要一上来就盲搜代码。
2. **操作 Confluence / Jira / Gerrit / OpenGrok 时，始终优先使用 `mmad-tools` skill 的命令行脚本**；仅在脚本不可用时才降级到 MCP 或其他方式。这是本 skill 和 README.md 的约定。
3. memory 标签要清晰稳定：`jira`、`analysis`、`confluence`、`gerrit`、模块名、项目名、issue key 是常用建议。
4. 根因必须有证据链，至少串起 Jira 现象、日志片段、代码路径中的两个以上。
5. 历史案例只能辅助，不能用历史结论替代本次 issue 的证据。
6. 当前 issue 的进展维护在 `JIRA.md` 和 `docs/xxx`，领域词汇和通用代码库探索不要混进来。
7. 所有结果最终收敛为简短结论，并把进展同步回 `JIRA.md` 完成收尾。
