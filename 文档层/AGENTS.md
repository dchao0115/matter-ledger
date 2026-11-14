---
name: "全局工作入口"
uri: "doc://demo/agent-entry"
type: "document"
created: "2026-10-04"
updated: "2026-10-04"
status: "active"
project: "project://demo"
related: ["project://demo","doc://demo/writing","doc://demo/development","doc://demo/module-boundary","doc://demo/module-layout","doc://demo/workflow-rule","doc://demo/workflow","doc://demo/cli-reference"]
tags: ["文档治理"]
kind: "rule"
links: [{"type":"governs","target":"project://demo"}]
---

# 全局工作入口

开始项目任务先读取 project://demo；修改模块先读取该模块的主记录。CLI 的 context 命令返回全局规则、主记录与关联材料，读取顺序见 doc://demo/cli-reference。代码目录不维护独立文档，本文件不会凭目录位置自动约束异地代码；任务启动必须显式提供本入口和项目绑定。

- 目标、范围和限制以项目主记录及当前用户指令为依据。历史讨论不能覆盖现行规则。
- 主记录拥有模块职责、输入输出和开发约定；需要更详细的内容时引用专题，勿复制另一份模块说明。
- 修改前查接口和依赖，重要取舍记录真实备选；范围内常规工作不反复请求确认。
- 根据实际改动验证并同步现行说明，活动记录保存结果、未完成项和下一动作。检查没有运行就明确记录。
- 文档以 URI 引用；位置变更更新绑定或索引，不修改资产身份。
- 用已有 Agent 和工具完成任务，不自行增加模型 API 调用层或通用运行时。
- 已归档材料仅供追溯；候选、计划、未核对和已实现必须区分。

写作、代码开发、模块拆分与存放、Workflow 形式、完整作业流程分别由 doc://demo/writing、doc://demo/development、doc://demo/module-boundary、doc://demo/module-layout、doc://demo/workflow-rule、doc://demo/workflow 持有。
