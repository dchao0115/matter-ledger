from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import yaml


URI = re.compile(r"[a-z][a-z0-9+.-]*://[A-Za-z0-9._~%/\-\u4e00-\u9fff]+")
SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules"}
REQUIRED = {"name", "uri", "type", "created", "updated", "status", "related", "tags"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def within(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"资源位置必须是根目录内的相对位置：{relative}")
    result = (root / relative).resolve()
    if not result.is_relative_to(root):
        raise ValueError(f"资源位置越出绑定根目录：{relative}")
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink() or (hasattr(cursor, "is_junction") and cursor.is_junction()):
            raise ValueError(f"资源不接受符号链接或 junction：{cursor}")
    return result


def files(root, skip=SKIP):
    if root.is_file():
        yield root
        return
    for path in sorted(root.rglob("*")):
        if any(part in skip for part in path.relative_to(root).parts):
            continue
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError(f"绑定范围中存在链接，请绑定实际目录：{path}")
        if path.is_file():
            yield path


def canonical_bytes(data):
    """归一化文本内容的 BOM 与行尾（CRLF/CR → LF），让指纹不随平台换行差异变化；二进制内容原样返回。"""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    if text.startswith("\ufeff"):
        text = text[1:]
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def digest(path, skip=SKIP):
    if not path.exists():
        return None
    h = hashlib.sha256()
    for file in files(path, skip):
        name = file.name if path.is_file() else file.relative_to(path).as_posix()
        h.update(name.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(canonical_bytes(file.read_bytes())).digest())
    return h.hexdigest()


class Catalog:
    def __init__(self, config):
        self.config_path = Path(config).resolve()
        self.config = read_json(self.config_path)
        base = self.config_path.parent
        self.roots = {key: (base / self.config[key + "_root"]).resolve() for key in ("docs", "code")}
        if any(not root.is_dir() for root in self.roots.values()):
            raise ValueError("文档根或代码根不存在，请修改项目位置绑定。")
        a, b = self.roots.values()
        if a.is_relative_to(b) or b.is_relative_to(a):
            raise ValueError("文档根与代码根必须独立，不能互相包含。")
        self.registry = read_json(within(base, self.config.get("registry", "ontology.json")))
        self.assets_path = within(base, self.config.get("assets", "assets.json"))
        self.state = within(base, self.config.get("state", "state"))
        self.external = set(self.config.get("external_uris", []))
        # skip_dirs 用于机器状态目录（缓存、本地库）：该目录既不参与指纹，也不参与
        # 「代码层含独立文档」检查。声明即视为承诺该目录不是作者手写的资产内容。
        self.skip = SKIP | set(self.config.get("skip_dirs", []))
        self.objects = {}
        self.links = []
        self.errors = []
        self.warnings = []
        self.project = f"project://{self.config['project_id']}"
        self._load()

    def error(self, message):
        self.errors.append(message)

    def _add(self, obj):
        uri = obj.get("uri")
        if not isinstance(uri, str) or URI.fullmatch(uri) is None:
            self.error(f"无效 URI：{uri}")
            return
        if uri in self.objects:
            self.error(f"重复 URI：{uri}")
            return
        self.objects[uri] = obj

    def _load(self):
        excluded = self.config.get("template_dirs", ["模板"])
        exclusions = [within(self.roots["docs"], item) for item in excluded]
        for path in files(self.roots["docs"], self.skip):
            if path.suffix.lower() != ".md" or any(path.is_relative_to(item) for item in exclusions):
                continue
            try:
                text = path.read_text(encoding="utf-8-sig")
                match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.S)
                if not match:
                    raise ValueError("缺少 YAML front matter")
                meta = yaml.safe_load(match[1])
                if not isinstance(meta, dict):
                    raise ValueError("YAML 头部必须是映射")
                missing = REQUIRED - meta.keys()
                if missing:
                    raise ValueError("缺少字段：" + ", ".join(sorted(missing)))
                for key in ("name", "uri", "type", "status"):
                    if not isinstance(meta[key], str) or not meta[key].strip():
                        raise ValueError(f"{key} 必须是非空字符串")
                for key in ("related", "tags", "links"):
                    if not isinstance(meta.get(key, []), list):
                        raise ValueError(f"{key} 必须是列表")
                for key in ("created", "updated"):
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(meta[key])):
                        raise ValueError(f"{key} 必须为 YYYY-MM-DD")
                    meta[key] = str(meta[key])
                    date.fromisoformat(meta[key])
                if meta["updated"] < meta["created"]:
                    raise ValueError("更新时间早于创建时间")
                if "archived_at" in meta:
                    meta["archived_at"] = str(meta["archived_at"])
                    date.fromisoformat(meta["archived_at"])
                for key in ("related", "tags"):
                    if not all(isinstance(item, str) for item in meta[key]):
                        raise ValueError(f"{key} 中的值必须是字符串")
                if "{{" in match[2]:
                    raise ValueError("正式文档仍含未填写模板标记")
                meta.update(path=str(path), body=match[2].strip(), root="docs")
                self._add(meta)
            except (ValueError, yaml.YAMLError, UnicodeError) as exc:
                self.error(f"{path.name}：{exc}")
        for raw in read_json(self.assets_path):
            obj = dict(raw)
            try:
                # 保留 location：bundle 打包目录型代码资产时要用它作归档前缀。
                location = obj.pop("location")
                obj["path"] = str(within(self.roots["code"], location))
                obj["location"] = location
                obj.update(type="code", root="code", project=self.project)
                obj.setdefault("related", [])
                obj.setdefault("links", [])
                self._add(obj)
            except (ValueError, KeyError, TypeError) as exc:
                self.error(f"代码资产位置错误：{exc}")
        if self.project not in self.objects:
            self.error("缺少与 project_id 对应的项目主记录")
        for uri, obj in self.objects.items():
            spec = self.registry["object_types"].get(obj.get("type"))
            if not spec:
                self.error(f"未注册 Object Type：{uri}")
                continue
            if not uri.startswith(spec["prefix"] + "://"):
                self.error(f"URI 前缀与对象类型不符：{uri}")
            if obj.get("status") not in spec["statuses"]:
                self.error(f"无效状态：{uri}")
            if "kinds" in spec and obj.get("kind") not in spec["kinds"]:
                self.error(f"{obj['type']} kind 无效：{uri}")
            if obj["type"] != "project":
                if obj.get("project") != self.project:
                    self.error(f"对象必须属于本项目：{uri}")
                self.links.append(dict(source=uri, type="belongs_to", target=obj.get("project")))
            elif uri != self.project:
                self.error(f"不能混入另一个项目主记录：{uri}")
            if obj.get("archived_at") and (obj["type"] != "decision" or obj["status"] != "implemented"):
                self.error(f"只有 implemented 决策可以设置 archived_at：{uri}")
            for relation in obj.get("links", []):
                if not isinstance(relation, dict) or not {"type", "target"} <= relation.keys():
                    self.error(f"关系须包含 type 和 target：{uri}")
                    continue
                self.links.append(dict(source=uri, type=relation["type"], target=relation["target"]))
            for target in obj.get("related", []):
                self.links.append(dict(source=uri, type="references", target=target))
            headings = spec.get("headings", [])
            if isinstance(headings, dict):
                headings = headings.get(obj.get("kind"), [])
            for heading in ([] if obj.get("archived_at") else headings):
                if heading not in obj.get("body", "").splitlines():
                    self.error(f"缺少 {heading}：{uri}")
            if obj["type"] == "decision" and not obj.get("archived_at"):
                headings = ["## 问题", "## 真实备选", "## 决定与后果"]
                if obj["status"] in ("proposed", "rejected"):
                    headings = ["## 问题", "## 真实备选", "## 提案与验收"]
                for heading in headings:
                    if heading not in obj.get("body", "").splitlines():
                        self.error(f"决策缺少 {heading}：{uri}")
            if obj["type"] == "code" and not Path(obj["path"]).exists():
                if obj.get("status") == "planned":
                    self.warnings.append(f"计划中的代码资产尚未创建：{uri}")
                else:
                    self.error(f"代码资产不存在：{uri}")
            if not obj.get("archived_at"):
                for target in URI.findall(obj.get("body", "")):
                    if target not in self.objects and target not in self.external:
                        self.error(f"正文 URI 未登记：{uri} → {target}")
        unique = {}
        for link in self.links:
            if not all(isinstance(link.get(k), str) for k in ("source", "type", "target")):
                self.error("关系字段必须为字符串")
                continue
            unique[tuple(link[k] for k in ("source", "type", "target"))] = link
        self.links = list(unique.values())
        self._validate_links()
        # 代码层默认禁止独立文档；机器消费的模板/语料说明可由 code_md_allow 前缀白名单放行。
        allow = [str(item).strip("/") for item in self.config.get("code_md_allow", [])]
        for path in files(self.roots["code"], self.skip):
            if path.suffix.lower() not in {".md", ".rst", ".adoc"}:
                continue
            relative = path.relative_to(self.roots["code"]).as_posix()
            if any(relative == prefix or relative.startswith(prefix + "/") for prefix in allow):
                continue
            self.error(f"代码层含独立文档：{relative}")
        self.errors = list(dict.fromkeys(self.errors))

    def _validate_links(self):
        for link in self.links:
            source, target = self.objects[link["source"]], self.objects.get(link["target"])
            spec = self.registry["link_types"].get(link["type"])
            if not spec:
                self.error(f"未注册 Link Type：{link['type']}")
                continue
            if target is None:
                if link["type"] == "references" and link["target"] in self.external:
                    continue
                if source.get("archived_at"):
                    continue
                self.error(f"关系目标不存在：{link['source']} → {link['target']}")
                continue
            if source["type"] not in spec["from"] or target["type"] not in spec["to"]:
                self.error(f"关系端点类型不符：{link}")
            if link["type"] == "supersedes" and source["type"] != target["type"]:
                self.error(f"替代关系须同类：{link}")
            if link["source"] == link["target"]:
                self.error(f"不允许自指关系：{link}")
        for obj in self.objects.values():
            if obj["type"] == "code":
                owners = [l for l in self.links if l["source"] == obj["uri"] and l["type"] == "implements"]
                if len(owners) != 1:
                    self.error(f"代码资产必须实现且只实现一个模块：{obj['uri']}")
            if obj["type"] == "module" and obj["status"] == "active":
                owners = [l for l in self.links if l["target"] == obj["uri"] and l["type"] == "implements"
                          and self.objects[l["source"]].get("status") == "active"]
                if not owners:
                    self.error(f"活动模块没有活动代码资产：{obj['uri']}")

    def require_valid(self):
        if self.errors:
            raise ValueError("结构检查失败：" + "；".join(self.errors))

    def get(self, uri):
        if uri not in self.objects:
            if uri in self.external:
                raise ValueError(f"这是已声明但未绑定位置的外部参考：{uri}")
            raise ValueError(f"找不到 URI：{uri}")
        return self.objects[uri]

    def export(self):
        return {"project": self.project, "objects": [dict(o) for o in self.objects.values()], "links": self.links}

    def footprint(self, module):
        if self.get(module)["type"] != "module":
            raise ValueError("核对对象必须是模块")
        included = {module}
        dependencies = {l["target"] for l in self.links if l["source"] == module and l["type"] == "depends_on"}
        included |= dependencies
        for link in self.links:
            source = self.objects[link["source"]]
            if source.get("archived_at"):
                continue
            if link["target"] == module and link["type"] in {"implements", "describes", "governs"}:
                if source.get("kind") != "verification":
                    included.add(link["source"])
            if link["target"] == self.project and link["type"] == "governs":
                included.add(link["source"])
            if link["source"] == module and link["type"] == "references":
                target = self.objects.get(link["target"])
                if target and target["type"] == "document" and target.get("kind") != "verification":
                    included.add(link["target"])
        return {uri: digest(Path(self.objects[uri]["path"]), self.skip) for uri in sorted(included)}

    def sync_status(self):
        path = self.state / "checkpoints.json"
        checkpoints = read_json(path) if path.exists() else {}
        results = []
        for uri, obj in self.objects.items():
            if obj["type"] != "module" or obj["status"] != "active":
                continue
            current = self.footprint(uri)
            old = checkpoints.get(uri)
            status = "未登记核对"
            changed = []
            if old:
                changed = sorted(key for key in set(current) | set(old["hashes"]) if current.get(key) != old["hashes"].get(key))
                evidence = self.objects.get(old["evidence"])
                evidence_changed = not evidence or digest(Path(evidence["path"]), self.skip) != old.get("evidence_hash")
                if evidence_changed:
                    changed.append(old["evidence"])
                status = "发生变化，需重新核对" if changed else "核对后指纹未变"
            results.append({"module": uri, "status": status, "changed": changed,
                            "evidence": old["evidence"] if old else None})
        return results

    def checkpoint(self, module, evidence_uri, actor):
        self.require_valid()
        obj = self.get(module)
        evidence = self.get(evidence_uri)
        if obj["type"] != "module" or obj["status"] != "active":
            raise ValueError("只为活动模块登记核对")
        if evidence["type"] != "document" or evidence.get("kind") != "verification" or evidence["status"] != "active":
            raise ValueError("核对依据须为活动的 verification 文档")
        if not any(l == dict(source=evidence_uri, type="verifies", target=module) for l in self.links):
            raise ValueError("验证记录必须用 verifies 指向该模块")
        for heading in ("## 验证对象", "## 实际结果", "## 限制"):
            if heading not in evidence["body"].splitlines():
                raise ValueError(f"验证记录缺少 {heading}")
        if not actor.strip():
            raise ValueError("须记录实际核对者")
        path = self.state / "checkpoints.json"
        values = read_json(path) if path.exists() else {}
        values[module] = {"actor": actor, "evidence": evidence_uri,
                          "evidence_hash": digest(Path(evidence["path"]), self.skip), "hashes": self.footprint(module)}
        write_json(path, values)
        # 追加历史：版本级审查要求留住"哪条意见覆盖哪一版"，不能只留当前值。
        history = self.state / "checkpoints.jsonl"
        previous = 0
        if history.exists():
            for line in history.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    previous += 1
        record = {"module": module, "actor": actor, "evidence": evidence_uri,
                  "evidence_hash": values[module]["evidence_hash"],
                  "hashes": values[module]["hashes"], "seq": previous + 1,
                  "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with history.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return {"module": module, "evidence": evidence_uri, "seq": record["seq"],
                "message": "已登记核对依据与指纹并追加历史；不代表工具已验证内容语义。"}
