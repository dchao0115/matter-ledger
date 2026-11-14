"""L3 逻辑检查：执行 ontology.json 规则层（rule_layer）登记的业务规则。

由 check --logic 在结构检查通过后调用；只读取已加载的对象与关系，报告违反情况和供人选择的处理方案，不修改任何资产。
"""
from __future__ import annotations

import copy
import re
from datetime import date
from pathlib import Path


LIMIT = ("逻辑检查只执行已登记且启用的规则，只依据显式登记的对象与关系判断；未登记的规矩、自然语言语义和业务结果"
         "不在覆盖范围内。工具只报告，不修改资产。")
FEEDBACK = ("option_a", "option_b", "recommend")
SEVERITIES = ("error", "warning", "reminder")
STATUS_NAMES = {"proposed": "待定", "implemented": "已实施", "rejected": "已拒绝", "draft": "草稿", "active": "现行",
                "archived": "已归档", "planned": "计划中", "retired": "已退役", "deprecated": "已停用", "closed": "已关闭"}
RERUN = "在 ontology.json 的 rule_layer 登记规则并设为 active 后再运行 check --logic"


def label(catalog, uri):
    obj = catalog.objects.get(uri)
    return f"「{obj['name']}」（{uri}）" if obj else uri


def state(obj):
    return f"{STATUS_NAMES.get(obj['status'], obj['status'])}（{obj['status']}）"


def relation_names(catalog, relations):
    return "、".join(f"「{catalog.registry['link_types'][r]['name']}」" for r in relations)


def components(graph):
    """Tarjan 强连通分量（迭代实现，避免递归深度限制）；只返回含两个以上节点的分量。"""
    index, low, stack, on_stack, result = {}, {}, [], set(), []
    for root in sorted(graph):
        if root in index:
            continue
        index[root] = low[root] = len(index)
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(sorted(graph.get(root, ()))))]
        while work:
            node, children = work[-1]
            for child in children:
                if child not in index:
                    index[child] = low[child] = len(index)
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(graph.get(child, ())))))
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == index[node]:
                    component = []
                    while True:
                        item = stack.pop()
                        on_stack.discard(item)
                        component.append(item)
                        if item == node:
                            break
                    if len(component) > 1:
                        result.append(sorted(component))
    return result


def shortest_cycle(graph, component):
    """在强连通分量内找经过其首个节点的最短环，作为报告证据。"""
    members, start = set(component), component[0]
    previous, queue = {}, [start]
    while queue:
        node = queue.pop(0)
        for child in sorted(graph.get(node, ())):
            if child not in members:
                continue
            if child == start:
                path = [node]
                while path[-1] != start:
                    path.append(previous[path[-1]])
                return path[::-1] + [start]
            if child not in previous:
                previous[child] = node
                queue.append(child)
    return component + [start]


# 每个校验函数返回 [(定位对象 URI, 涉及对象 URI 列表, 业务语言描述)]；判断取值来自规则的 scope 与 check.params。


def supersession_state(catalog, rule, params):
    types, relations = set(rule["scope"]["object_types"]), set(rule["scope"]["link_types"])
    in_force, void = set(params.get("in_force_statuses", [])), set(params.get("void_statuses", []))
    retired = set(params.get("retired_statuses", []))
    found = []
    for link in catalog.links:
        new, old = catalog.objects[link["source"]], catalog.objects.get(link["target"])
        if link["type"] not in relations or old is None or new["type"] not in types or old["type"] not in types:
            continue
        if new["status"] in void:
            found.append((new["uri"], [new["uri"], old["uri"]],
                          f"{label(catalog, new['uri'])}已是{state(new)}，却仍登记为完整替代{label(catalog, old['uri'])}；"
                          "没有生效的记录不能替代别的记录，两条记录的状态互相矛盾。"))
        elif new["status"] in in_force and old["status"] not in retired and not old.get("archived_at"):
            found.append((old["uri"], [old["uri"], new["uri"]],
                          f"{label(catalog, old['uri'])}已被{state(new)}的{label(catalog, new['uri'])}完整替代，"
                          f"却仍是{state(old)}且未归档；读取上下文时新旧两条会同时作为有效内容出现。"))
    return found


def has_outgoing(catalog, rule, params):
    types, relations = set(rule["scope"]["object_types"]), set(rule["scope"]["link_types"])
    exempt, names = set(params.get("exempt_statuses", [])), relation_names(catalog, rule["scope"]["link_types"])
    linked = {link["source"] for link in catalog.links if link["type"] in relations}
    return [(uri, [uri], f"{label(catalog, uri)}没有用{names}关系连到任何对象；除非主记录在关联资料里引用它，"
                         "读取项目或模块上下文时不会带上它，也看不出它针对谁。")
            for uri, obj in catalog.objects.items()
            if obj["type"] in types and obj["status"] not in exempt and not obj.get("archived_at") and uri not in linked]


def acyclic(catalog, rule, params):
    found = []
    for relation in rule["scope"]["link_types"]:
        graph = {}
        for link in catalog.links:
            if link["type"] == relation and link["target"] in catalog.objects:
                graph.setdefault(link["source"], set()).add(link["target"])
        name = catalog.registry["link_types"][relation]["name"]
        for component in components(graph):
            path = shortest_cycle(graph, component)
            text = f"「{name}」关系绕成了环：" + " → ".join(label(catalog, uri) for uri in path)
            rest = [uri for uri in component if uri not in path]
            if rest:
                text += "；同一组环路还牵涉" + "、".join(label(catalog, uri) for uri in rest)
            found.append((path[0], component, text + "。"))
    return found


def project_lists_modules(catalog, rule, params):
    exempt, relations = set(params.get("exempt_statuses", [])), set(rule["scope"]["link_types"])
    listed = {link["target"] for link in catalog.links if link["source"] == catalog.project and link["type"] in relations}
    return [(uri, [uri, catalog.project],
             f"模块{label(catalog, uri)}目前是{state(obj)}，却没有登记在项目主记录{label(catalog, catalog.project)}"
             "的关联资料里；从项目入口开始工作的人找不到它。")
            for uri, obj in catalog.objects.items()
            if obj["type"] == "module" and obj["status"] not in exempt and uri not in listed]


def dependency_status(catalog, rule, params):
    callers, callees = set(params.get("source_statuses", [])), set(params.get("target_statuses", []))
    types, relations = set(rule["scope"]["object_types"]), set(rule["scope"]["link_types"])
    found = []
    for link in catalog.links:
        source, target = catalog.objects[link["source"]], catalog.objects.get(link["target"])
        if (link["type"] in relations and target is not None and source["type"] in types and target["type"] in types
                and source["status"] in callers and target["status"] in callees):
            found.append((source["uri"], [source["uri"], target["uri"]],
                          f"{label(catalog, source['uri'])}目前是{state(source)}，却依赖{state(target)}的"
                          f"{label(catalog, target['uri'])}；标为可用的部分实际依赖一个不可用的部分。"))
    return found


def folder_ownership(catalog, rule, params):
    types, relations = set(rule["scope"]["object_types"]), set(rule["scope"]["link_types"])
    exempt, names = set(params.get("exempt_statuses", [])), relation_names(catalog, rule["scope"]["link_types"])
    record = params.get("module_record_file", "AGENTS.md")
    homes = {Path(o["path"]).parent: uri for uri, o in catalog.objects.items()
             if o["type"] == "module" and o["root"] == "docs" and Path(o["path"]).name == record
             and Path(o["path"]).parent != catalog.roots["docs"]}
    code = {}
    for link in catalog.links:
        if link["type"] == "implements":
            code.setdefault(link["target"], set()).add(link["source"])
    found = []
    for uri, obj in catalog.objects.items():
        if obj["type"] not in types or obj["status"] in exempt or obj.get("archived_at"):
            continue
        home = next((homes[folder] for folder in Path(obj["path"]).parents if folder in homes), None)
        if home is None:
            continue
        targets = {link["target"] for link in catalog.links if link["source"] == uri and link["type"] in relations}
        if not targets & ({home} | code.get(home, set())):
            found.append((uri, [uri, home], f"{label(catalog, uri)}放在模块{label(catalog, home)}的文档目录里，"
                                            f"却没有用{names}关系挂到该模块或它的代码；目录位置与登记的归属不一致。"))
    return found


def decision_referenced(catalog, rule, params):
    """已实施决策必须被至少一个现行对象引用，否则报告。

    引用来源三类：实例关系（links / related 生成的 references、affects 等）、
    正文中的 URI 文本、以及决策自身的 affects 目标反向关联。
    """
    types = set(rule["scope"]["object_types"])
    relations = set(rule["scope"]["link_types"])
    referenced_statuses = set(params.get("referenced_statuses", ["planned", "active"]))
    weak_types = set(params.get("weak_types", ["document"]))
    found = []
    for uri, obj in catalog.objects.items():
        if obj["type"] not in types or obj["status"] != "implemented" or obj.get("archived_at"):
            continue
        referrers = set()
        for link in catalog.links:
            if link["target"] == uri and link["type"] in relations and link["source"] != uri:
                source = catalog.objects.get(link["source"])
                if source and source["status"] in referenced_statuses:
                    referrers.add(link["source"])
        for other_uri, other in catalog.objects.items():
            if other_uri == uri or other_uri in referrers:
                continue
            if other["status"] not in referenced_statuses:
                continue
            if uri in other.get("body", ""):
                referrers.add(other_uri)
        if referrers:
            continue
        found.append((uri, [uri],
                      f"{label(catalog, uri)}已实施，但没有任何现行文档或模块引用它；"
                      f"写相关模块的人读不到这条决定，决定等于停在原地。"))
    return found


def proposed_stale(catalog, rule, params):
    """待定决策超过 N 天未推进，报告提醒。"""
    types = set(rule["scope"]["object_types"])
    days = int(params.get("max_age_days", 30))
    today = date.fromisoformat(str(params.get("as_of"))) if params.get("as_of") else date.today()
    found = []
    for uri, obj in catalog.objects.items():
        if obj["type"] not in types or obj["status"] != "proposed" or obj.get("archived_at"):
            continue
        try:
            created = date.fromisoformat(str(obj.get("created", "")))
        except ValueError:
            continue
        age = (today - created).days
        if age <= days:
            continue
        found.append((uri, [uri],
                      f"{label(catalog, uri)}自{obj.get('created')}起一直是待定，已 {age} 天没有推进；"
                      f"超过 {days} 天的待定决定会变成没人记得的悬案——要么落成已实施，要么明确拒绝。"))
    return found


CHECKS = {
    "supersession_state": supersession_state,
    "has_outgoing": has_outgoing,
    "acyclic": acyclic,
    "project_lists_modules": project_lists_modules,
    "dependency_status": dependency_status,
    "folder_ownership": folder_ownership,
    "decision_referenced": decision_referenced,
    "proposed_stale": proposed_stale,
}


def section(value, key):
    item = value.get(key) if isinstance(value, dict) else None
    return item if isinstance(item, dict) else {}


def blank(value):
    return value is None or value == [] or value == {} or (isinstance(value, str) and not value.strip())


def validate(catalog, layer):
    """校验规则对象本身：人能读（statement）且机器能跑（check）才算规则。

    返回 [(规则, 定义问题)]、规则层错误与告警。active 规则的定义问题是错误；
    candidate / deprecated 规则不执行，其定义问题只作告警。规则来源失效只告警，规则照常执行。
    """
    spec = section(section(layer, "object_types"), "rule")
    if not spec:
        return [], ["规则层缺少 rule 对象类型定义"], []
    entries = layer.get("rules")
    if not isinstance(entries, list):
        return [], ["规则层 rules 须为列表"], []
    try:
        pattern = re.compile(spec.get("id_pattern", ".+"))
    except (re.error, TypeError) as exc:
        return [], [f"规则层 id_pattern 无效：{exc}"], []
    derived = section(section(layer, "link_types"), "derived_from").get("to", [])
    result, errors, warnings, seen = [], [], [], set()
    for position, rule in enumerate(entries, 1):
        if not isinstance(rule, dict):
            errors.append(f"第 {position} 条规则不是对象")
            continue
        rid = rule.get("ruleId")
        name = rid if isinstance(rid, str) and rid.strip() else f"第 {position} 条规则"
        problems = [f"缺少 {field}" for field in spec.get("fields", {}) if blank(rule.get(field))]
        for field in ("ruleId", "name", "statement"):
            if not blank(rule.get(field)) and not isinstance(rule[field], str):
                problems.append(f"{field} 须为字符串")
        if isinstance(rid, str) and rid.strip():
            if not pattern.fullmatch(rid):
                problems.append("ruleId 格式不符")
            if rid in seen:
                problems.append("ruleId 重复")
            seen.add(rid)
        for field, allowed in (("severity", spec.get("severities", [])), ("status", spec.get("statuses", [])),
                               ("layer", spec.get("layers", []))):
            if not blank(rule.get(field)) and rule[field] not in allowed:
                problems.append(f"{field} 无效：{rule[field]}")
        scope = rule.get("scope")
        if isinstance(scope, dict):
            for key in ("object_types", "link_types"):
                values = scope.get(key)
                if not isinstance(values, list) or not values:
                    problems.append(f"scope.{key} 须为非空列表")
                    continue
                unknown = [str(v) for v in values if not isinstance(v, str) or v not in catalog.registry[key]]
                if unknown:
                    problems.append(f"scope.{key} 含未注册类型：" + "、".join(unknown))
        elif not blank(scope):
            problems.append("scope 须为对象")
        check = rule.get("check")
        if isinstance(check, dict):
            function = check.get("function")
            if not isinstance(function, str) or function not in CHECKS:
                problems.append(f"check.function 未由规则引擎实现：{function}")
            if not isinstance(check.get("params", {}), dict):
                problems.append("check.params 须为对象")
        elif not blank(check):
            problems.append("check 须为对象")
        feedback = rule.get("feedback")
        if isinstance(feedback, dict):
            missing = [key for key in FEEDBACK if not isinstance(feedback.get(key), str) or blank(feedback[key])]
            if missing:
                problems.append("feedback 缺少 " + "、".join(missing))
        elif not blank(feedback):
            problems.append("feedback 须为对象")
        sources = rule.get("source")
        if isinstance(sources, list):
            for uri in sources:
                if not isinstance(uri, str):
                    problems.append("source 中的值须为 URI 字符串")
                    continue
                target = catalog.objects.get(uri)
                if target is None and uri not in catalog.external:
                    warnings.append(f"{name}：规则来源未登记：{uri}")
                elif target is not None and target["type"] not in derived:
                    warnings.append(f"{name}：规则来源须为 {'/'.join(derived)}：{uri}")
        elif not blank(sources):
            problems.append("source 须为 URI 列表")
        if problems:
            target = warnings if rule.get("status") in ("candidate", "deprecated") else errors
            target.append(f"{name}：" + "；".join(problems))
        result.append((rule, problems))
    return result, errors, warnings


def violation(catalog, rule, uri, involved, text):
    obj = catalog.objects[uri]
    item = {"rule": rule["ruleId"], "name": rule["name"], "severity": rule["severity"], "object": uri,
            "root": obj["root"], "location": Path(obj["path"]).relative_to(catalog.roots[obj["root"]]).as_posix(),
            "involved": involved, "decision_point": text}
    item.update((key, rule["feedback"][key]) for key in FEEDBACK)
    return item


def report(run_state, reason, actions, results=(), violations=(), errors=(), warnings=()):
    counts = {s: sum(v["severity"] == s for v in violations) for s in SEVERITIES}
    if run_state in ("skipped", "failed"):
        verdict = "未执行"
    elif errors or counts["error"]:
        verdict = "有错误"
    elif counts["warning"]:
        verdict = "有警告"
    elif counts["reminder"]:
        verdict = "有提醒"
    else:
        verdict = "全过"
    executed = [r for r in results if r["result"] in ("通过", "违反")]
    return {
        "ok": run_state == "succeeded" and not counts["error"],
        "layer": "L3",
        "business_state": {
            "verdict": verdict,
            "summary": {"rules": len(results), "executed": len(executed),
                        "passed": sum(r["result"] == "通过" for r in executed),
                        "violated": sum(r["result"] == "违反" for r in executed),
                        "errors": counts["error"], "warnings": counts["warning"], "reminders": counts["reminder"]},
            "violations": list(violations),
            "rules": list(results),
        },
        "run_state": {"state": run_state, "reason": reason,
                      "rule_layer_errors": list(errors), "rule_layer_warnings": list(warnings)},
        "contract": {"allowed_next_actions": actions, "modifies_files": False, "limit": LIMIT},
    }


def run(catalog):
    if catalog.errors:
        return report("skipped", "结构检查未通过；逻辑检查建立在完整的对象与关系上，本次未执行。",
                      ["先按 errors 修复结构问题，再运行 check --logic"])
    layer = catalog.registry.get("rule_layer")
    if not isinstance(layer, dict):
        return report("skipped", "ontology.json 未登记规则层（rule_layer），没有可执行的规则。", [RERUN])
    entries, errors, warnings = validate(catalog, layer)
    results, violations = [], []
    for rule, problems in entries:
        item = {"rule": rule.get("ruleId"), "name": rule.get("name"), "severity": rule.get("severity"),
                "status": rule.get("status"), "statement": rule.get("statement")}
        if problems:
            item["result"] = "定义无效，未执行"
        else:
            item.update(governs=rule["scope"], derived_from=rule["source"])
            if rule["status"] != "active":
                item["result"] = "未启用" if rule["status"] == "candidate" else "已停用"
            else:
                check = rule["check"]
                try:
                    found = CHECKS[check["function"]](catalog, rule, check.get("params", {}))
                except (KeyError, TypeError, ValueError, AttributeError) as exc:
                    errors.append(f"{rule['ruleId']}：规则执行失败：{exc!r}")
                    item["result"] = "执行失败"
                else:
                    item.update(result="违反" if found else "通过", violations=len(found))
                    violations.extend(violation(catalog, rule, *entry) for entry in found)
        results.append(item)
    executed = any(r["result"] in ("通过", "违反") for r in results)
    if not executed:
        if errors:
            return report("failed", "规则层定义有错误，没有规则得以执行。",
                          ["修正 rule_layer_errors 中标出的规则定义，再运行 check --logic"],
                          results, errors=errors, warnings=warnings)
        return report("skipped", "规则层没有启用（active）的规则；没有执行任何规则不算逻辑检查通过。", [RERUN],
                      results, errors=errors, warnings=warnings)
    actions = []
    if errors:
        actions.append("修正 rule_layer_errors 中标出的规则定义，再运行 check --logic；其余规则的结果仍然有效")
    if any(v["severity"] == "error" for v in violations):
        actions.append("按 violations 中的决策点与方案 A/B 由人选择处理方式，修改来源文档或关系后重新运行 check --logic；"
                       "工具不自动修复")
    if any(v["severity"] != "error" for v in violations):
        actions.append("warning 与 reminder 不使检查失败；逐条确认是否补登关系或调整状态")
    if not actions:
        actions.append("逻辑规则全部通过；按作业流程继续 index、checkpoint 与 check --strict")
    return report("partial" if errors else "succeeded", None, actions, results, violations, errors, warnings)


def rebase_sources(registry, rebase):
    """init 复制项目时改写规则来源 URI 的项目命名空间；规则层其余内容属通用 schema，原样复制。"""
    registry = copy.deepcopy(registry)
    layer = registry.get("rule_layer")
    entries = layer.get("rules") if isinstance(layer, dict) else None
    for rule in entries if isinstance(entries, list) else []:
        if isinstance(rule, dict) and isinstance(rule.get("source"), list):
            rule["source"] = [rebase(uri) if isinstance(uri, str) else uri for uri in rule["source"]]
    return registry
