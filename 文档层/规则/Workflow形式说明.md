---
name: "Workflow 形式说明"
uri: "doc://demo/workflow-rule"
type: "document"
created: "2026-10-05"
updated: "2026-10-05"
status: "active"
project: "project://demo"
related: ["doc://demo/module-boundary","doc://demo/module-rules","doc://demo/ontology","doc://demo/workflow-entry"]
tags: ["文档治理"]
kind: "rule"
links: [{"type":"governs","target":"project://demo"}]
---

# Workflow 形式说明

Workflow 描述“一件事怎么被编排执行”。按执行控制权分两种 kind，场景与做法不同，不能混用。

## 编排型 Workflow（orchestrated）

流程控制执行，AI 是执行单元。

- 适用：多个独立子任务、批量、并行或流水线；要求确定性与可复现（审计、迁移、多角度调研）。
- 做法：声明输入、输出、步骤与失败分类；步骤固定；可机械校验；失败大声报错，不静默。
- 不适用：步骤含大量 AI 判断、需要边跑边调整。

## 引导型 Workflow（guided）

流程引导 AI，AI 是执行主体。

- 适用：有业务触发、步骤含 AI 判断、跨模块编排、需要灵活调整与事后迭代。
- 做法：声明触发、用到的模块（含各自输入输出）、要读的提示词与规则、验收；由 AI Agent 执行，保留判断空间。
- 不适用：要求强确定性和可复现的编排。

## 选择判据

看执行控制权：流程控制执行选编排型；流程引导 AI 选引导型。两者共用“用途”与“关联资料”，其余章节按 kind 强制。

## 与模块的关系

Workflow 用 depends_on 指向它用到的模块；模块只声明自己的输入输出，不反向定义 Workflow。视图据此显示每个 Workflow 用了哪些模块。

## 不纳入的形式

运行时引擎、事件流与进程生命周期不属于文档治理范围；本规则只描述 Workflow 的声明形态，不描述其执行引擎。
