---
name: "规则目录约束"
uri: "doc://demo/rules-entry"
type: "document"
created: "2026-10-04"
updated: "2026-10-04"
status: "active"
project: "project://demo"
related: ["doc://demo/writing"]
tags: ["文档治理"]
kind: "rule"
links: [{"type":"governs","target":"project://demo"}]
---

# 规则目录约束

此处维护跨模块稳定规则：写作、开发、作业、本体定义，以及模块拆分与边界、模块存放、Workflow 形式。新规则优先并入已有文件，避免为了补充一句话再增加规则文档。

规则用 governs 声明作用项目或模块。此处不放一次性任务进度、代码实现走读、完整讨论记录；这些按 doc://demo/writing 落位。规则有必要例外时明确条件和原因，不默默改变强制程度。
