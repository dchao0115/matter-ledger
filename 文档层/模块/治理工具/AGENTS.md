---
name: "文档治理 CLI 模块"
uri: "module://demo/docgov"
type: "module"
created: "2026-10-04"
updated: "2026-10-11"
status: "active"
project: "project://demo"
related: ["code://demo/docgov","doc://demo/cli-reference","doc://demo/ontology","doc://demo/tool-verification","decision://demo/separate-docs","decision://demo/l3-rule-layer","decision://demo/fingerprint-normalization"]
tags: ["文档治理"]
---

# 文档治理 CLI 模块

## 职责

读取项目绑定、文档 YAML 和代码资产登记，解析 URI、查询关联、检查结构与核对指纹，并按规则层执行 L3 业务规则检查。它是本地工具，不调用 AI API、不生成业务代码、不执行文档里的命令，不修复检查发现的问题。

代码实体为 code://demo/docgov。catalog.py 负责读取、校验、指纹；queries.py 负责上下文与影响查询；logic.py 负责校验规则定义并执行规则；docgov.py 负责参数、回执和复制；view.py 负责把索引渲染成离线 HTML 视图。这些是同一模块的内部实现，不为每个文件另建模块。

## 输入与输出

输入：--config 指向 project.json；文档和代码根分别绑定；ontology.json 定义类型关系与规则层，assets.json 定义代码资产。命令详情由 doc://demo/cli-reference 持有。

输出：成功为 JSON 回执，退出码 0；结构、参数、定位、严格同步检查失败，或逻辑检查出现 error 级违反与规则定义错误为退出码 2。帮助由 argparse 输出。查询不写文件；index 写治理 state 并生成注册表视图，checkpoint 写治理 state；init 只创建不存在的新项目目录。

错误不静默忽略；未绑定的外部 URI 报告未绑定。指纹覆盖本模块代码、主记录、直接关联的现行专题、全局规则及直接依赖模块的主记录。它不能自动判断自然语言和代码语义相同，不能推断未登记的调用关系。

## 开发与验证

运行环境为 Python 3.10+ 和 PyYAML 6.x，验证环境以 doc://demo/tool-verification 为准。配置位置可分离，资源位置不得逃出绑定根，不跟随资源中的 symlink/junction。

修改解析或关系查询时验证坏输入与实际 CLI；修改同步逻辑时验证源代码、主记录和证据变化；修改指纹逻辑时验证行尾（CRLF/LF）与 BOM 不影响指纹，跨平台可复现；修改复制逻辑时验证原项目不被覆盖及移动后可定位；修改规则引擎或规则时验证每条规则的违反与通过两种情况、规则定义错误不被静默跳过，以及检查不写文件。检查入口在代码资产的 tests 内，属于代码而非文档。

## 关联资料

现行：doc://demo/cli-reference、doc://demo/ontology。验证：doc://demo/tool-verification。重要决定：decision://demo/separate-docs、decision://demo/l3-rule-layer、decision://demo/fingerprint-normalization。共享要求：doc://demo/development。
