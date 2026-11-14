# MatterLedger · 事项台账

> 给 AI 项目一个自包含的上下文存放处：事情到哪一步、为什么这样定、哪些方案被否、改这里会影响谁，都在一个目录里，AI 可以直接查。

**English** — MatterLedger is a copyable governance package for AI-driven projects. It keeps every matter, decision and module in one self-contained place. A human-readable document layer and a machine-queryable ontology run in parallel; a local CLI lets an agent retrieve context (`context`), trace impact (`impact`), and check consistency (`check`). It does not call any model API and does not replace your agent.

## 它解决什么问题

和 AI 一起做一个会持续多轮的项目，上下文通常散在四个地方：聊天记录、文档、代码、人的记忆。

结果是四种常见故障：

- AI 改完代码，不知道现行说明也要同步；
- 决定做了，只留下结论，没留下为什么，也没留下哪些方案被否；
- 事情一多，说不清每件到哪一步；
- 换一个会话，AI 从零开始猜。

MatterLedger 把这些收进一个可复制的目录：**一个事项一行台账，一个模块一份主记录，一个决定一份决策记录**。

## 三个层次

- **文档层**：给人读。现行说明只写「现在是什么」，演进记录写「怎么变成现在这样」。
- **代码层**：只放源码、测试和机器定义。不放 README、设计说明和操作手册。
- **治理层**：项目绑定、ontology、代码资产登记、索引与核对指纹。

三层可以放在不同磁盘位置，用 `project.json` 绑定；文档里只用稳定 URI，不写本机绝对路径。

## 双轨并行

同一条事实有两个入口：

- **文档轨**：Markdown + YAML 元信息 + 稳定 URI，人读。
- **本体轨**：对象与关系（project / module / document / decision / activity / code / workflow；depends_on / affects / supersedes / implements / verifies 等），机器查。

两条轨用 URI 对齐。CLI 的 `context` 从一个 URI 拉出主记录、规则和相关材料；`impact` 沿依赖反查影响面；`check` 查结构与跨对象规则。

## 它回答的四个问题

1. 接手一个模块，先读什么？—— `context module://...`
2. 这个决定为什么这么做？哪些方案被否了？—— 决策记录里的「真实备选」
3. 改这里会影响谁？—— `impact`
4. 现在有几件事，各自到哪一步？—— 事项台账

## 三份文档，各管一段

- **现行说明 = 资产负债表**：只写当前有效的行为，不写「以前是……现在是……」。
- **演进记录 = 流水账**：一次作业一份，写目标、完成、验证、下一步。
- **决策记录 = 取舍台账**：强制写「真实备选 + 未采用理由」，状态三态 `proposed` / `implemented` / `rejected`，替代关系用 `supersedes` 登记。

多数项目只保留第一份。真正让下一个人（或下一轮 AI）接得上的，是后两份。

## 三个真实取舍

这个包自己就是按这套方法做出来的。三个例子：

**1. 文档与代码分离（采纳）**
- 未采用：沿用 DSH，在代码包旁放 AGENTS.md 和 README。理由：不符合独立文档层的偏好，代码区仍要维护文档。
- 代价：启动任务必须显式提供文档入口和 `project.json`，不能依赖目录自动发现。

**2. 规则层放进 ontology.json（采纳）**
- 未采用：独立 rules.json（多一个要绑定和复制的文件）；写进代码（规则失去登记、停用、追溯来源的能力）；引入 OWL/SHACL（个人项目的规矩都是确定性的图与状态判断，用不上）。
- 结果：`check --logic` 能报出跨对象违反，并给人方案 A / 方案 B。

**3. 指纹归一化 BOM 与行尾（采纳）**
- 未采用：只靠 `.gitattributes` 固定 LF（依赖每个使用者的 git 配置，对已有 CRLF 检出无效）。
- 结果：Windows 检出与 Linux 检出的指纹一致，跨平台 `check --strict` 不再误报。

## 快速开始

环境：Python 3.10+，PyYAML 6.x。

```bash
python -m pip install -r "代码层/packages/governance/docgov/requirements.txt"

python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" check
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" context project://demo
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" check --logic
```

复制成一个新项目：

```bash
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" init --target "../my-project" --project-id my-project --name "我的项目"
```

把下面这段话给 AI：

> 使用我提供的文档入口、治理 CLI 位置和 project.json。本次任务是：填写实际任务。先读取文档入口，再通过 context 取得项目和目标模块的主记录、全局规则与关联说明；核对当前代码及任务状态后执行。文档只写文档根，代码只写代码根，索引和核对记录写治理 state。按已授权范围完成必要修改、验证与接续记录，不自行增加模型 API 调用层。

## 目录

```text
文档层/
  项目主记录.md          项目目标、边界、当前状态
  规则/                  写作、开发、作业、Workflow、本体
  现行/                  当前架构与专题
  演进/决策/             为什么这样选，真实备选与未采用理由
  演进/作业/             一次任务发生了什么
  模块/<模块>/AGENTS.md  每个模块一份主记录
  模板/                  可复制模板（事项台账、决策记录、模块主记录等）
代码层/
  packages/              可复用模块
  apps/  vendor/  scripts/  tests/
治理层/
  project.json           文档根、代码根、治理数据的绑定
  ontology.json          对象、关系、状态定义与规则层
  assets.json            代码资产登记
  state/                 索引与核对指纹（可重建）
```

## 适用与不适用

适用：
- 个人或小团队，AI 主导编码；
- 项目会持续多轮，需要跨会话接续；
- 希望 AI 在动手前先知道边界、理由和影响面。

不适用：
- 需要多人审批流、分支策略、PR 流程；
- 需要对外发布、运营、多租户；
- 想把它当成模型调用层或 Agent 运行时。它不调用任何模型 API。

## 来源与边界

- 参考了 DeepSeek Harness 的 harness 分层、模块契约与文档写作规则，并做了裁剪：去掉团队协作、发布流程与 TypeScript/Cordis 机制。**这不是 DeepSeek 官方项目，也不包含其源码。**
- 当前 61 项测试通过（Linux / Python 3.11；此前在 Windows / Python 3.12 上验证）。
- `check` 不能证明文档与代码语义一致；指纹只证明字节级内容稳定。
- 「事项台账」目前是文档模板，阶段由人或 Agent 维护，CLI 不推断阶段。

## License

代码 MIT；文档 CC BY 4.0。
