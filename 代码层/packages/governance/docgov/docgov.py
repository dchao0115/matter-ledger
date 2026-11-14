from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

from catalog import Catalog, SKIP, read_json, write_json
from queries import context, impact, neighbors
import logic
import view
import bundle


def initialize(catalog, target, project_id, name):
    catalog.require_valid()
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", project_id):
        raise ValueError("项目 ID 使用小写字母开头的小写字母、数字或连字符，最多 48 位")
    if not name.strip():
        raise ValueError("项目名称不能为空")
    target = Path(target).resolve()
    if target.exists():
        raise ValueError("目标必须是不存在的新目录，不覆盖既有项目")
    sources = [*catalog.roots.values(), catalog.config_path.parent]
    if any(target.is_relative_to(root) or root.is_relative_to(target) for root in sources):
        raise ValueError("新项目目录不得包含源项目或位于源目录内部")
    target.mkdir(parents=True)
    ignore = shutil.ignore_patterns(*SKIP)
    for key, folder in (("docs", "文档层"), ("code", "代码层")):
        shutil.copytree(catalog.roots[key], target / folder, ignore=ignore)
    governance = target / "治理层"
    governance.mkdir()
    cfg = dict(catalog.config)
    cfg.update(project_id=project_id, project_name=name, docs_root="../文档层", code_root="../代码层",
               registry="ontology.json", assets="assets.json", state="state")
    old = catalog.config["project_id"]

    def rebase(value):
        if isinstance(value, str):
            value = re.sub(r"://" + re.escape(old) + r"(?=/|$|[^A-Za-z0-9._~%\-\u4e00-\u9fff])", "://" + project_id, value)
            return value.replace(catalog.config.get("project_name", "示例项目"), name)
        if isinstance(value, list):
            return [rebase(item) for item in value]
        if isinstance(value, dict):
            return {key: rebase(item) for key, item in value.items()}
        return value

    write_json(governance / "ontology.json", logic.rebase_sources(catalog.registry, rebase))
    for path in (target / "文档层").rglob("*.md"):
        text = path.read_text(encoding="utf-8-sig")
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)(.*)\Z", text, re.S)
        if match:
            meta = rebase(yaml.safe_load(match[1]))
            text = "---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n" + rebase(match[2])
        else:
            text = rebase(text)
        path.write_text(text, encoding="utf-8")
    write_json(governance / "assets.json", rebase(read_json(catalog.assets_path)))
    write_json(governance / "project.json", cfg)
    copied = Catalog(governance / "project.json")
    copied.require_valid()
    return {"config": str(governance / "project.json"), "project": copied.project,
            "message": "已复制新项目；旧索引和核对指纹未复制。模板模块仍为 planned，需由 Agent 填写。"}


def parser():
    p = argparse.ArgumentParser(description="文档治理 CLI：定位、查询和检查文档与代码关系，不调用模型 API。")
    p.add_argument("--config", required=True, help="项目位置绑定 JSON")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("schema", help="读取 Object Type、Link Type 与规则层定义")
    sub.add_parser("list", help="列出对象")
    for cmd in ("resolve", "show", "impact"):
        sub.add_parser(cmd).add_argument("uri")
    q = sub.add_parser("links")
    q.add_argument("uri")
    q.add_argument("--direction", choices=("in", "out", "both"), default="both")
    q = sub.add_parser("context")
    q.add_argument("uri")
    q.add_argument("--history", action="store_true")
    q = sub.add_parser("check")
    q.add_argument("--strict", action="store_true", help="活动模块未核对或发生变化时也返回失败")
    q.add_argument("--logic", action="store_true", help="结构检查后执行规则层登记的 L3 业务规则；只报告，不修改")
    sub.add_parser("index", help="重建派生索引并生成注册表视图；查询始终直接读取当前来源")
    q = sub.add_parser("checkpoint", help="实际核对完成后登记依据和指纹，不替代验证")
    q.add_argument("module")
    q.add_argument("--evidence", required=True)
    q.add_argument("--actor", required=True)
    q = sub.add_parser("init", help="复制为新项目，不覆盖现有目录")
    q.add_argument("--target", required=True)
    q.add_argument("--project-id", required=True)
    q.add_argument("--name", required=True)
    q = sub.add_parser("export", help="导出交付单元（manifest + 对象 + 核对历史 + 文件），省略须声明")
    q.add_argument("--target", required=True, help="输出目录")
    q.add_argument("--bundle-name")
    q.add_argument("--bundle-version", default="1.0.0")
    q.add_argument("--omit", action="append", default=[], help="声明省略的对象 URI，可重复")
    q.add_argument("--omit-note", help="省略理由，写入 declared-omitted 记录")
    q.add_argument("--include-code", action="store_true", help="同时打包代码资产文件")
    q = sub.add_parser("import", help="导入交付单元到新的项目位置")
    q.add_argument("--archive", required=True)
    q.add_argument("--target", required=True)
    q.add_argument("--project-id")
    q.add_argument("--name")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        catalog = Catalog(args.config)
        command = args.command
        if command == "check":
            sync = catalog.sync_status() if not catalog.errors else []
            failed_sync = [s for s in sync if s["status"] != "核对后指纹未变"]
            report = logic.run(catalog) if args.logic else None
            ok = not catalog.errors and not (args.strict and failed_sync) and (report is None or report["ok"])
            result = {"ok": ok, "errors": catalog.errors, "warnings": catalog.warnings, "sync": sync,
                      "objects": len(catalog.objects), "links": len(catalog.links),
                      "limit": "结构检查和指纹比对不等于语义一致性或业务验收。"}
            if report is not None:
                result["logic"] = report
            code = 0 if ok else 2
        else:
            catalog.require_valid()
            code = 0
            if command == "schema":
                result = catalog.registry
            elif command == "list":
                result = [{k: o.get(k) for k in ("uri", "name", "type", "status", "path")}
                          for o in catalog.objects.values()]
            elif command in ("resolve", "show"):
                result = dict(catalog.get(args.uri))
                if command == "resolve":
                    result = {k: result[k] for k in ("uri", "type", "status", "path")}
                    result["exists"] = Path(result["path"]).exists()
            elif command == "links":
                result = neighbors(catalog, args.uri, args.direction)
            elif command == "context":
                result = context(catalog, args.uri, args.history)
            elif command == "impact":
                result = impact(catalog, args.uri)
            elif command == "index":
                index = catalog.export()
                for obj in index["objects"]:
                    obj["location"] = Path(obj.pop("path")).relative_to(catalog.roots[obj["root"]]).as_posix()
                write_json(catalog.state / "index.json", index)
                viewer = view.render(index, catalog.config, catalog.state / "viewer" / "registry.html")
                result = {"objects": len(index["objects"]), "links": len(index["links"]),
                          "index": str(catalog.state / "index.json"), "viewer": str(viewer)}
            elif command == "checkpoint":
                result = catalog.checkpoint(args.module, args.evidence, args.actor)
            elif command == "init":
                result = initialize(catalog, args.target, args.project_id, args.name)
            elif command == "export":
                result = bundle.export_bundle(catalog, args.target, name=args.bundle_name,
                                              version=args.bundle_version, omit=args.omit,
                                              include_code=args.include_code, note=args.omit_note)
            elif command == "import":
                result = bundle.import_bundle(args.archive, args.target,
                                              project_id=args.project_id, name=args.name)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return code
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
