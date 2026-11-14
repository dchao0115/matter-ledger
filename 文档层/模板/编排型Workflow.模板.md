---
name: "{{文档名称}}"
uri: "workflow://{{项目ID}}/{{唯一标识}}"
type: "workflow"
kind: "orchestrated"
created: "2026-10-05"
updated: "2026-10-05"
status: "draft"
project: "project://{{项目ID}}"
related: []
tags: ["模板"]
links: []
---

# {{名称}}

## 用途

{{适用于什么场景；为什么需要确定性与可复现}}

## 输入与输出

{{输入来源与格式、输出语义}}

## 步骤

{{固定步骤与顺序；每步用什么}}

## 失败分类

{{完成 / 取消 / 错误分别如何表达；失败是否大声报错}}

## 关联资料

{{用到模块的 URI（用 depends_on 登记）、相关文档}}
