---
name: "工作流目录约束"
uri: "doc://demo/workflow-entry"
type: "document"
created: "2026-10-05"
updated: "2026-10-05"
status: "active"
project: "project://demo"
related: ["doc://demo/workflow-rule","doc://demo/module-rules"]
tags: ["文档治理"]
kind: "rule"
links: [{"type":"governs","target":"project://demo"}]
---

# 工作流目录约束

此处放 Workflow 编排记录，kind 由 doc://demo/workflow-rule 定义。编排型与引导型各按其强制章节书写，用 depends_on 登记用到的模块。

Workflow 只写编排；模块职责与输入输出回到模块主记录，不在此复制。示例仅演示结构，不代表真实编排。
