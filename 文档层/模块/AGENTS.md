---
name: "模块主记录规则"
uri: "doc://demo/module-rules"
type: "document"
created: "2026-10-04"
updated: "2026-10-04"
status: "active"
project: "project://demo"
related: ["doc://demo/development","doc://demo/writing"]
tags: ["文档治理"]
kind: "rule"
links: [{"type":"governs","target":"project://demo"}]
---

# 模块主记录规则

每个模块一个目录、一份 AGENTS.md 主记录，type 为 module，URI 稳定。它承接 DSH 模块 AGENTS.md 的约束与导航职责，并合并精简包 README 的职责说明。

主记录必须有“职责、输入与输出、开发与验证、关联资料”四部分。可以保留完整的小型接口约定，长专题再单独创建；不要为同一模块另写重复 README。全局开发与写作规则只引用。

主记录 related 列出应读现行说明和重要演进记录，depends_on 登记模块依赖。其他文档用 describes、affects 或 verifies 指回模块，CLI 从这些关系汇总。代码资产通过 implements 指向本模块。

源码目录和文档目录不必同名。移动文件保持 URI；拆分成不同职责时才创建新模块身份。退役模块保留必要演进记录并处理调用方，不能仅改状态假装不存在依赖。
