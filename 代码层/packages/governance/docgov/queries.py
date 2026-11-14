from __future__ import annotations


def neighbors(catalog, uri, direction="both"):
    catalog.get(uri)
    return [link for link in catalog.links if
            (direction in ("out", "both") and link["source"] == uri) or
            (direction in ("in", "both") and link["target"] == uri)]


def context(catalog, uri, history=False):
    obj = catalog.get(uri)
    if obj["type"] not in ("module", "project"):
        raise ValueError("context 接受项目或模块 URI")
    chosen = {uri, catalog.project}
    for link in catalog.links:
        if link["type"] == "governs" and link["target"] in {uri, catalog.project}:
            chosen.add(link["source"])
        if link["target"] == uri and link["type"] in {"describes", "affects", "implements", "verifies"}:
            chosen.add(link["source"])
        if link["target"] == catalog.project and link["type"] == "affects":
            chosen.add(link["source"])
        if link["source"] == uri and link["type"] in {"references", "depends_on"}:
            chosen.add(link["target"])
    result = {"entry": obj, "rules": [], "current": [], "decisions": [], "pending_or_rejected": [],
              "activities": [], "code": [], "history": [], "modules": []}
    for target in sorted(chosen - {uri}):
        if target not in catalog.objects:
            continue
        item = catalog.objects[target]
        if item.get("archived_at") or item["status"] in ("archived", "retired"):
            if history:
                result["history"].append(item)
        elif item["status"] in ("draft", "planned"):
            result["pending_or_rejected"].append(item)
        elif item["type"] == "decision":
            key = "decisions" if item["status"] == "implemented" else "pending_or_rejected"
            result[key].append(item)
        elif item["type"] == "activity":
            result["activities"].append(item)
        elif item["type"] == "code":
            result["code"].append(item)
        elif item.get("kind") == "rule":
            result["rules"].append(item)
        else:
            result["current"].append(item)
    if obj["type"] == "project":
        result["modules"] = [{k: item[k] for k in ("uri", "name", "status", "path")}
                             for item in catalog.objects.values() if item["type"] == "module"]
    result["sync"] = [s for s in catalog.sync_status() if s["module"] == uri or uri == catalog.project]
    result["reading_order"] = "全局规则 → 主记录 → 按任务阅读关联资料；历史不作为现行指令。"
    return result


def impact(catalog, uri):
    catalog.get(uri)
    reached, pending = {uri}, [uri]
    paths = []
    while pending:
        target = pending.pop(0)
        for link in catalog.links:
            if link["type"] == "depends_on" and link["target"] == target and link["source"] not in reached:
                reached.add(link["source"])
                pending.append(link["source"])
                paths.append(link)
    documents = sorted({link["source"] for link in catalog.links if link["target"] in reached
                        and link["type"] in {"describes", "affects", "governs", "verifies", "references"}})
    return {"target": uri, "dependents": sorted(reached - {uri}), "dependency_paths": paths,
            "related_records": documents, "limit": "仅根据已登记关系计算，不宣称覆盖未登记的代码调用。"}
