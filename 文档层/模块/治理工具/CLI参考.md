---
name: "CLI 使用与启动说明"
uri: "doc://demo/cli-reference"
type: "document"
created: "2026-10-04"
updated: "2026-10-11"
status: "active"
project: "project://demo"
related: ["module://demo/docgov","doc://demo/tool-verification","doc://demo/ontology"]
tags: ["文档治理"]
kind: "procedure"
links: [{"type":"describes","target":"module://demo/docgov"}]
---

# CLI 使用与启动说明

## 环境与位置

需要 Python 3.10+、PyYAML 6.x。依赖清单是代码根 packages/governance/docgov/requirements.txt；由 Agent 安装并执行。没有模型 API、服务端、数据库或 Docker 依赖。

以下命令在交付包根执行，默认文档、代码和治理层平级。分开存放后，把执行命令中的脚本与 config 位置换成实际位置；正式文档引用继续使用 URI。配置中的根路径相对 project.json 所在目录解析。

```powershell
python -m pip install -r "代码层/packages/governance/docgov/requirements.txt"
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" check
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" context project://demo
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" context module://demo/docgov
```

## 给 Agent 的启动话术

> 使用我提供的文档入口、治理 CLI 位置和 project.json。本次任务是：填写实际任务。先读取文档入口，再通过 context 取得项目和目标模块的主记录、全局规则与关联说明；核对当前代码及任务状态后执行。文档只写文档根，代码只写代码根，索引和核对记录写治理 state。按已授权范围完成必要修改、验证与接续记录，不自行增加模型 API 调用层。

启动话术通过当前 Agent 客户端正常输入，不依赖源码旁 AGENTS.md 自动加载。不能只提供一个 URI 而不告诉 Agent 解析入口。本文不是客户端自动配置或通用 Agent 调度器。

## 命令参考

所有业务命令成功输出 JSON、退出码 0；无效参数、结构、URI 或检查失败退出码 2。帮助由 --help 提供。多个写命令由一个收尾 Agent 顺序执行；当前实现不支持并发写 index/checkpoint/init。

| 命令 | 用途及写入 |
|---|---|
| schema | 读取类型、关系、状态定义与规则层；只读 |
| list | 列出当前扫描到的对象；只读 |
| resolve URI | 返回实际路径与存在状态；只读 |
| show URI | 返回元信息与正文；只读 |
| links URI --direction in/out/both | 查入站、出站关系；只读 |
| context URI | 项目或模块主记录、规则、现行和演进材料；只读 |
| context URI --history | 额外包含关联归档；只读 |
| impact URI | 沿反向 depends_on 查传递调用方和相关记录；只读 |
| check | 检查结构，返回核对状态；只读 |
| check --strict | 结构失败、活动模块未核对或指纹变化则失败；只读 |
| check --logic | 结构检查后执行规则层的 L3 业务规则，结果放在 logic 字段；可与 --strict 同用；只读 |
| index | 重建治理 state/index.json，并生成注册表视图 state/viewer/registry.html |
| checkpoint 模块URI --evidence 验证URI --actor 实际核对者 | 实际核对完成后写 state/checkpoints.json（当前值）并追加 state/checkpoints.jsonl（历史，带 seq 与时间） |
| init --target 新目录 --project-id 小写ID --name 中文名称 | 复制为新项目，不覆盖既有目录、不复制旧 state |
| export --target 输出目录 [--bundle-name 名称] [--bundle-version 版本] [--omit URI ...] [--omit-note 理由] [--include-code] | 导出交付单元：manifest + 对象 + 核对历史 + 文件，输出 `.docgov.tar.gz` |
| import --archive 包路径 --target 新目录 | 导入交付单元到新的项目位置，校验 bundle_hash 与每个文件指纹，恢复文件并写 import-receipt.json |

例：已对治理工具完成实际验证并更新验证文档后，由执行 Agent 登记：

```powershell
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" checkpoint module://demo/docgov --evidence doc://demo/tool-verification --actor agent:current
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" check --strict
```

actor 是实际执行者的标记，不具备身份认证功能，不能冒充用户批准。

## 逻辑检查

check --logic 执行治理层 ontology.json 中 rule_layer 登记、状态为 active 的规则；规则的字段与首批规则见 doc://demo/ontology。结构检查未通过时不执行规则，logic 字段说明原因。

```powershell
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" check --logic
```

logic 字段分三段。business_state 给出结论（全过、有提醒、有警告、有错误、未执行）、计数、每条规则的结果，以及 violations：每条违反写明规则、严重程度、对象 URI 与所在根内位置、涉及对象、业务语言的决策点、方案 A、方案 B 和推荐。run_state 给出执行状态（succeeded、partial、failed、skipped）与规则层自身的定义错误和告警。contract 给出下一步动作和覆盖限制。

退出码：出现 error 级违反、规则层定义错误、结构错误，或没有任何规则得以执行时为 2；warning 与 reminder 只报告，退出码仍为 0。工具不修改任何文件，处理方式由人按决策点选择后修改来源文档或关系，再重新检查。

改取值、停用规则或调整严重程度只改 ontology.json；规则引擎没有的判断方式需在代码资产的 logic.py 增加校验函数并补测试。candidate 规则只登记不执行，用于先写下待确认的规矩。

## 提交门禁

逻辑检查默认由收尾 Agent 按 doc://demo/workflow 运行。要让它在提交时强制执行，用包内的门禁包装 gate.py：

```powershell
python "代码层/packages/governance/docgov/gate.py" --config "治理层/project.json"
```

gate.py 等价于 check --strict --logic：结构、核对指纹或 L3 规则任一不通过就返回非零，只读不改。把它装成 git pre-commit 钩子，坏提交会被拦下：

```powershell
python "代码层/packages/governance/docgov/install_gate_hook.py"
```

安装器只在“包所在仓库根就是交付包根”的独立项目里写入 .git/hooks/pre-commit；包嵌在更大仓库里时默认不装（避免影响宿主仓库的每次提交），确认要装时加 --force。已有钩子不覆盖，改为打印内容供手工合并。

## 复制为新项目

在原交付包执行下例；把目标放在源包之外的全新目录。init 复制文档、代码及通用 schema，替换项目 URI 命名空间和项目名称。它不代表业务模块已经开发，也不自动批准复制来的历史决定。

```powershell
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" init --target "../新项目" --project-id my-small-project --name "我的小项目"
```

`init` 用于按模板新建合规项目。对已存在但结构不合规的项目，优先「新建合规目录 + 旧路径留一段迁移说明」，不在原目录内逐步改造——半步合规既过不了 `check`，也当不了模板复制（2026-10-19 Loop Engineering 重建实测：3485 files。边界：旧路径若有活跃外部引用且无法批量改路径，重建会造成大面积悬空引用，此时需先评估引用面）。

复制后填写项目目标和示例模块，审视继承规则。沿用同一规则的治理工具可以复用，但核对指纹须在新项目实际检查后重新登记。新增模块从模板创建主记录，在 assets.json 登记源码 URI、相对位置和 implements，并登记依赖。不要更改既有模块 URI 来表示完全不同的职责。

模板目录不参加索引。复制模板后填写其中所有双花括号标记，清空无依据的关联，分配真实 URI，再运行 check。普通修改不要求新建决策或专题。

## 移动与恢复

文档文件在文档根内移动后重建 index；整体根目录移动后更新 project.json。代码目录内部移动后更新 assets.json 的相对位置。URI 保持不变，随后 resolve、check 和必要业务验证确认结果。

## 交付单元（export / import）

交付单元是把一个项目连同证据交给另一个人的标准形态。它回答三个问题，缺一不算可交接：

1. **输入是不是真被用了**——manifest 的 `files[].sha256` 记录每个对象的内容指纹；`evidence[]` 记录每个活动模块的核对依据与指纹。
2. **审查覆盖哪一版**——`state/checkpoints.jsonl` 保留每次核对的序号与时间，`evidence[]` 取每个模块的最新一条，指向具体验证文档而不是文件名。
3. **缺的是没给还是没有**——`--omit` 声明省略的对象，写为 `availability: declared-omitted` 并带理由；未声明的对象一律视为随包。

硬约束：活动模块的验证文档与项目主记录不可省略，省略即导出失败。导入端只恢复记录与文件，不执行代码、不恢复凭据。

**省略声明写法（命令级）**：`--omit <对象 URI>` 必配 `--omit-note <理由>`，缺理由视为未声明（导出直接失败）。不得省略清单：活动模块的验证文档、项目主记录。三判据的验收标准见本包的交付单元验收说明。

```powershell
# 导出完整包
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" export --target "../交付" --include-code

# 导出并声明省略
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" export --target "../交付" --omit "<要省略的对象 URI>" --omit-note "含未脱敏细节"

# 导入到新位置
python "代码层/packages/governance/docgov/docgov.py" --config "治理层/project.json" import --archive "../交付/xxx.docgov.tar.gz" --target "../接收方项目"
```

包格式：gzip 压缩 tar，含 `manifest.json`、`objects.json`、`checkpoints.jsonl` 与 `files/<URI命名空间>/` 下的原始文件。manifest 自带 `bundle_hash`，导入时校验；对象与文件均可追溯到 URI。

checkpoint 或 index 写入中断时，旧完整文件仍是依据；临时文件不是有效记录，下一次写入可以替换。失去 index 可直接重建；失去核对指纹须重新检查并登记，不根据旧回执补造。本工具不自动修正文档语义、不删除归档、不迁移原项目。
