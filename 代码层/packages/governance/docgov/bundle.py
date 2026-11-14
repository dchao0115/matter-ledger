"""交付单元：把项目连同证据打包成可交接的 bundle，并支持导入到新的项目位置。

设计口径（对照三条交付判据确定）：

1. 证据强度：manifest 记录每个对象的内容指纹，以及每个活动模块的核对记录；
   导入端据此判断"内容是否就是当时审查的那一版"。
2. 版本级审查：manifest 的 evidence 段绑定 module → verification 文档 → checkpoint 序号，
   不是绑定到文件名。
3. 省略声明：被排除的内容必须留下 `declared-omitted` 记录与理由；用于计算的必需证据
   （活动模块的 verification 文档、项目主记录）不允许省略，省略即导出失败。

取舍：不引入 RO-Crate，不承载会话记录；只做本包文档治理对象的标准化交付。
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path

from catalog import SKIP, canonical_bytes, digest, files, read_json, write_json

BUNDLE_FORMAT = "docgov-bundle-1"
BUNDLE_VERSION = "1.0.0"
MANIFEST = "manifest.json"
OBJECTS = "objects.json"
RECEIPTS = "checkpoints.jsonl"

# 不允许省略的对象类型/状态：省略即失败
REQUIRED_TYPES = {"project"}
REQUIRED_SKILL_STATUS = ("active",)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _bundle_id(catalog, manifest_core) -> str:
    return _sha(_canonical(manifest_core))[:24]


def _required_evidence(catalog):
    """活动模块必须随附其 verification 文档；缺了就是省略了必需证据。"""
    required = {}
    for uri, obj in catalog.objects.items():
        if obj["type"] != "module" or obj["status"] not in REQUIRED_SKILL_STATUS:
            continue
        verifiers = [l["source"] for l in catalog.links
                     if l["target"] == uri and l["type"] == "verifies"]
        required[uri] = verifiers
    return required


def _checkpoint_history(catalog):
    """读取核对历史；兼容旧 dict 格式与新的 jsonl 追加格式。"""
    jsonl = catalog.state / "checkpoints.jsonl"
    if jsonl.exists():
        records = []
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return records
    legacy = catalog.state / "checkpoints.json"
    if legacy.exists():
        data = read_json(legacy)
        if isinstance(data, dict):
            return [{**value, "module": module, "seq": 1} for module, value in data.items()]
    return []


def _latest_checkpoints(records):
    latest = {}
    for record in records:
        module = record.get("module")
        if module:
            latest[module] = record
    return latest


def export_bundle(catalog, target, *, name=None, version=BUNDLE_VERSION, omit=None,
                  include_code=False, note=None):
    """导出交付单元。target 为输出目录；返回 manifest。"""
    catalog.require_valid()
    omit = list(omit or [])
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    omissions = []
    missing = []
    for uri in omit:
        obj = catalog.objects.get(uri)
        if obj is None:
            missing.append(f"省略项未登记：{uri}")
            continue
        if obj["type"] in REQUIRED_TYPES:
            missing.append(f"项目主记录不可省略：{uri}")
            continue
        omissions.append({
            "uri": uri, "type": obj["type"], "name": obj.get("name"),
            "availability": "declared-omitted",
            "reason": note or "按导出范围声明省略",
        })
    if missing:
        raise ValueError("；".join(missing))

    omitted_uris = {item["uri"] for item in omissions}

    # 必需证据不能被省略
    for module, verifiers in _required_evidence(catalog).items():
        if module in omitted_uris:
            raise ValueError(f"活动模块不可省略（其验证记录是必需证据）：{module}")
        for verifier in verifiers:
            if verifier in omitted_uris:
                raise ValueError(f"活动模块的验证记录不可省略：{verifier}（属于 {module}）")

    # 收集文件
    payload_entries = []
    for uri, obj in sorted(catalog.objects.items()):
        if uri in omitted_uris:
            continue
        path = Path(obj["path"])
        if not path.exists():
            continue
        if obj["root"] == "code" and not include_code:
            payload_entries.append({
                "uri": uri, "kind": "code", "path": path.name,
                "location": obj.get("location"), "included": False,
                "path": f"{_safe(uri.replace('://', '_'))}/", "sha256": digest(path, getattr(catalog, "skip", SKIP)),
            })
            continue
        if path.is_file():
            # 包内路径以 URI 命名空间隔离：同名 AGENTS.md 不能互相覆盖。
            arcname = f"{_safe(uri.replace('://', '_'))}/{path.name}"
            payload_entries.append({"uri": uri, "kind": obj["type"], "path": arcname, "included": True,
                                    "sha256": _sha(canonical_bytes(path.read_bytes()))})
        # 目录型代码资产按 include_code 复制

    latest = _latest_checkpoints(_checkpoint_history(catalog))
    evidence = []
    for module, record in sorted(latest.items()):
        evidence.append({
            "module": module,
            "evidence": record.get("evidence"),
            "actor": record.get("actor"),
            "seq": record.get("seq"),
            "at": record.get("at"),
            "evidence_hash": record.get("evidence_hash"),
            "hashes": record.get("hashes", {}),
        })

    core = {
        "bundle_name": name or catalog.config.get("project_name") or catalog.project,
        "bundle_version": version,
        "format": BUNDLE_FORMAT,
        "project": catalog.project,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "docgov export",
        "objects": {"total": len(catalog.objects), "by_type": _count_by(catalog.objects)},
        "links": len(catalog.links),
        "omissions": omissions,
        "evidence": evidence,
        "files": payload_entries,
    }
    bundle_id = _bundle_id(catalog, core)
    manifest = dict(core, bundle_id=bundle_id)
    manifest["bundle_hash"] = _sha(_canonical(manifest))

    objects_doc = {
        "project": catalog.project,
        "objects": [{k: v for k, v in obj.items() if k not in ("body",)}
                    for obj in catalog.objects.values()],
        "links": catalog.links,
    }

    archive = target / f"{_safe(bundle_id)}.docgov.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        def add_bytes(name, data):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = int(datetime.now().timestamp())
            tar.addfile(info, io.BytesIO(data))

        add_bytes(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
        add_bytes(OBJECTS, json.dumps(objects_doc, ensure_ascii=False, indent=2).encode("utf-8"))
        history = _checkpoint_history(catalog)
        add_bytes(RECEIPTS, "\n".join(json.dumps(r, ensure_ascii=False) for r in history).encode("utf-8"))
        for entry in payload_entries:
            if not entry.get("included"):
                continue
            path = _locate(catalog, entry["uri"])
            if path is None or not path.is_file():
                continue
            arc = f"files/{entry['path']}"
            add_bytes(arc, canonical_bytes(path.read_bytes()))
        if include_code:
            for obj_uri, obj in sorted(catalog.objects.items()):
                if obj["root"] != "code" or obj_uri in omitted_uris:
                    continue
                root = Path(obj["path"])
                if not root.is_dir():
                    continue
                for child in files(root, getattr(catalog, "skip", SKIP)):
                    rel = child.relative_to(root).as_posix()
                    arc = f"code/{obj['location']}/{rel}"
                    add_bytes(arc, canonical_bytes(child.read_bytes()))

    return {"archive": str(archive), "manifest": manifest, "omissions": len(omissions)}


def import_bundle(archive, target, *, project_id=None, name=None):
    """导入交付单元。target 必须是不存在的新目录。"""
    archive = Path(archive).resolve()
    target = Path(target).resolve()
    if target.exists() and any(target.iterdir()):
        raise ValueError("目标必须是不存在或空的新目录，不覆盖既有项目")
    with tarfile.open(archive, "r:gz") as tar:
        manifest = json.loads(tar.extractfile(MANIFEST).read().decode("utf-8"))
        stored = manifest.pop("bundle_hash", None)
        actual = _sha(_canonical(manifest))
        if stored != actual:
            raise ValueError("manifest 校验失败：bundle_hash 不匹配，包可能在传输中损坏或被修改")
        manifest["bundle_hash"] = stored
        objects_doc = json.loads(tar.extractfile(OBJECTS).read().decode("utf-8"))
        receipts = []
        member = tar.getmember(RECEIPTS)
        for line in tar.extractfile(member).read().decode("utf-8").splitlines():
            if line.strip():
                receipts.append(json.loads(line))

        target.mkdir(parents=True, exist_ok=True)
        for entry in manifest.get("files", []):
            if not entry.get("included"):
                continue
            try:
                member = tar.getmember(f"files/{entry['path']}")
            except KeyError:
                continue
            data = tar.extractfile(member).read()
            if _sha(data) != entry["sha256"]:
                raise ValueError(f"文件校验失败：{entry['path']}")
            destination = target / "files" / entry["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        if any(item.get("kind") == "code" and item.get("included") for item in manifest.get("files", [])):
            for member in tar.getmembers():
                if member.name.startswith("code/") and member.isfile():
                    destination = target / member.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(tar.extractfile(member).read())

    report = {
        "bundle_id": manifest.get("bundle_id"),
        "bundle_name": manifest.get("bundle_name"),
        "bundle_version": manifest.get("bundle_version"),
        "source_project": manifest.get("project"),
        "objects": manifest.get("objects", {}).get("total"),
        "links": manifest.get("links"),
        "omissions": manifest.get("omissions", []),
        "evidence": manifest.get("evidence", []),
        "files_restored": sum(1 for e in manifest.get("files", []) if e.get("included")),
        "target": str(target),
        "note": "导入只恢复记录与文件，不执行代码、不恢复凭据。",
    }
    write_json(target / "import-receipt.json", report)
    return report


def _count_by(objects):
    counts = {}
    for obj in objects.values():
        counts[obj["type"]] = counts.get(obj["type"], 0) + 1
    return dict(sorted(counts.items()))


def _locate(catalog, uri):
    obj = catalog.objects.get(uri)
    return Path(obj["path"]) if obj else None


def _safe(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value)
