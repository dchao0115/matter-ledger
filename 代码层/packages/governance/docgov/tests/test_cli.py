from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

TOOL = Path(__file__).resolve().parents[1]
KIT = TOOL.parents[3]
sys.path.insert(0, str(TOOL))
from catalog import Catalog, read_json, write_json
from queries import context, impact


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        work = Path(os.environ.get("DOCGOV_TEST_ROOT", str(KIT / "验证工作区"))).resolve()
        work.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="docgov-", dir=work)
        self.base = Path(self.temporary.name).resolve()
        assert self.base.is_relative_to(work)
        self.addCleanup(self.temporary.cleanup)
        self.docs, self.code, self.gov = [self.base / p for p in ("source/docs", "source/code", "source/gov")]
        for root in (self.docs, self.code, self.gov):
            root.mkdir(parents=True)
        write_json(self.gov / "ontology.json", read_json(KIT / "治理层/ontology.json"))
        write_json(self.gov / "project.json", {"project_id": "test", "project_name": "测试夹具",
                   "docs_root": "../docs", "code_root": "../code", "template_dirs": ["templates"]})
        (self.code / "m.py").write_text("value = 1\n", encoding="utf-8")
        write_json(self.gov / "assets.json", [{"uri": "code://test/m", "name": "测试源码", "status": "active",
                   "location": "m.py", "links": [{"type": "implements", "target": "module://test/m"}]}])
        self.document("project.md", "project://test", "project", "## 目标与边界\n测试夹具。\n## 当前状态\n测试中。\n## 开始工作\n测试入口。")
        self.module("m", "active")
        self.document("rules.md", "doc://test/rules", "document", "本文件仅是测试输入。",
                      kind="rule", links=[{"type": "governs", "target": "project://test"}])
        self.document("evidence.md", "doc://test/evidence", "document",
                      "## 验证对象\n测试夹具。\n## 实际结果\n测试输入，不代表真实业务证据。\n## 限制\n仅供单元测试。",
                      kind="verification", links=[{"type": "verifies", "target": "module://test/m"}])

    @property
    def config(self):
        return self.gov / "project.json"

    def catalog(self):
        return Catalog(self.config)

    def document(self, filename, uri, typ, body, **fields):
        meta = {"name": "测试夹具", "uri": uri, "type": typ, "created": "2026-10-04", "updated": "2026-10-04",
                "status": "active", "related": [], "tags": ["测试"]}
        if typ != "project":
            meta["project"] = "project://test"
        meta.update(fields)
        path = self.docs / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\n" + yaml.safe_dump(meta, allow_unicode=True, sort_keys=False) + "---\n\n" + body + "\n", encoding="utf-8")
        return path

    def module(self, name, status, dependencies=()):
        return self.document(name + ".md", "module://test/" + name, "module",
               "## 职责\n测试。\n## 输入与输出\n测试。\n## 开发与验证\n测试。\n## 关联资料\n测试。",
               status=status, links=[{"type": "depends_on", "target": uri} for uri in dependencies])

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-B", str(TOOL / "docgov.py"), "--config", str(self.config), *args],
                                capture_output=True, text=True, encoding="utf-8")
        return result.returncode, json.loads(result.stdout)

    def checkpoint(self):
        self.catalog().checkpoint("module://test/m", "doc://test/evidence", "agent:test")

    def test_real_cli_resolves_unicode_paths_and_context(self):
        code, output = self.cli("resolve", "module://test/m")
        self.assertEqual(code, 0)
        self.assertEqual(Path(output["path"]), self.docs / "m.md")
        code, output = self.cli("context", "module://test/m")
        self.assertEqual(code, 0)
        self.assertEqual(output["rules"][0]["uri"], "doc://test/rules")
        self.assertEqual(output["code"][0]["uri"], "code://test/m")

    def test_duplicate_uri_fails(self):
        (self.docs / "duplicate.md").write_bytes((self.docs / "m.md").read_bytes())
        code, output = self.cli("check")
        self.assertEqual(code, 2)
        self.assertTrue(any("重复 URI" in item for item in output["errors"]))

    def test_dangling_body_and_typed_links_fail(self):
        self.document("bad.md", "doc://test/bad", "document", "doc://test/missing", kind="reference",
                      links=[{"type": "describes", "target": "module://test/missing"}])
        errors = self.catalog().errors
        self.assertTrue(any("正文 URI 未登记" in e for e in errors))
        self.assertTrue(any("关系目标不存在" in e for e in errors))

    def test_invalid_relationship_endpoints_fail(self):
        self.document("bad.md", "doc://test/bad", "document", "测试。", kind="reference",
                      links=[{"type": "implements", "target": "module://test/m"}])
        self.assertTrue(any("关系端点类型不符" in e for e in self.catalog().errors))

    def test_path_escape_is_rejected(self):
        assets = read_json(self.gov / "assets.json")
        assets[0]["location"] = "../outside.py"
        write_json(self.gov / "assets.json", assets)
        code, output = self.cli("check")
        self.assertEqual(code, 2)
        self.assertTrue(any("相对位置" in e for e in output["errors"]))

    def test_no_readme_in_code(self):
        (self.code / "README.md").write_text("测试夹具\n", encoding="utf-8")
        self.assertTrue(any("代码层含独立文档" in e for e in self.catalog().errors))

    def test_unreviewed_module_fails_strict_check(self):
        self.assertEqual(self.cli("check")[0], 0)
        self.assertEqual(self.cli("check", "--strict")[0], 2)

    def test_code_change_requires_new_checkpoint(self):
        self.checkpoint()
        self.assertEqual(self.cli("check", "--strict")[0], 0)
        (self.code / "m.py").write_text("value = 2\n", encoding="utf-8")
        code, output = self.cli("check", "--strict")
        self.assertEqual(code, 2)
        self.assertIn("code://test/m", output["sync"][0]["changed"])

    def test_fingerprint_ignores_line_endings(self):
        """同一内容在不同换行环境下指纹一致：CRLF 检出后不应要求重新核对。"""
        self.checkpoint()
        self.assertEqual(self.cli("check", "--strict")[0], 0)
        for path in (self.docs / "m.md", self.code / "m.py", self.docs / "evidence.md"):
            text = path.read_text(encoding="utf-8")
            path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(self.catalog().sync_status()[0]["status"], "核对后指纹未变")
        self.assertEqual(self.cli("check", "--strict")[0], 0)

    def test_global_rule_and_evidence_changes_require_review(self):
        self.checkpoint()
        with (self.docs / "rules.md").open("a", encoding="utf-8") as f:
            f.write("规则变化。\n")
        self.assertIn("doc://test/rules", self.catalog().sync_status()[0]["changed"])
        self.checkpoint()
        with (self.docs / "evidence.md").open("a", encoding="utf-8") as f:
            f.write("证据变化。\n")
        self.assertIn("doc://test/evidence", self.catalog().sync_status()[0]["changed"])

    def test_module_document_change_requires_review(self):
        self.checkpoint()
        with (self.docs / "m.md").open("a", encoding="utf-8") as f:
            f.write("新的接口约定。\n")
        self.assertIn("module://test/m", self.catalog().sync_status()[0]["changed"])

    def test_moving_docs_and_code_preserves_uris_and_fingerprints(self):
        self.checkpoint()
        new_docs, new_code = self.base / "独立文档", self.base / "另一处代码"
        for source, target in ((self.docs, new_docs), (self.code, new_code)):
            self.assertTrue(source.resolve().is_relative_to(self.base))
            self.assertTrue(target.resolve().is_relative_to(self.base))
            source.rename(target)
        cfg = read_json(self.config)
        cfg.update(docs_root=str(new_docs), code_root=str(new_code))
        write_json(self.config, cfg)
        code, result = self.cli("resolve", "module://test/m")
        self.assertEqual(code, 0)
        self.assertEqual(Path(result["path"]), new_docs / "m.md")
        self.assertEqual(self.cli("check", "--strict")[0], 0)

    def test_impact_finds_transitive_dependents(self):
        self.module("b", "planned", ["module://test/m"])
        self.module("c", "planned", ["module://test/b"])
        result = impact(self.catalog(), "module://test/m")
        self.assertEqual(result["dependents"], ["module://test/b", "module://test/c"])

    def test_archived_notes_are_not_current_authority(self):
        self.document("archived.md", "decision://test/old", "decision", "## 问题\n测试。\n## 真实备选\n测试。\n## 决定与后果\n测试。",
                      status="implemented", archived_at="2026-10-04",
                      links=[{"type": "affects", "target": "module://test/m"}])
        result = context(self.catalog(), "module://test/m")
        self.assertEqual(result["decisions"], [])
        self.assertEqual(result["history"], [])
        result = context(self.catalog(), "module://test/m", True)
        self.assertEqual(result["history"][0]["uri"], "decision://test/old")
        self.assertEqual(self.cli("index")[0], 0)

    def test_invalid_evidence_cannot_checkpoint(self):
        with self.assertRaisesRegex(ValueError, "verification"):
            self.catalog().checkpoint("module://test/m", "doc://test/rules", "agent:test")

    def test_templates_are_not_assets(self):
        (self.docs / "templates").mkdir()
        (self.docs / "templates/sample.md").write_text("模板 {{待填写}}", encoding="utf-8")
        self.assertEqual(self.catalog().errors, [])

    def test_invalid_calendar_date_is_rejected(self):
        path = self.docs / "rules.md"
        path.write_text(path.read_text(encoding="utf-8").replace("2026-10-04", "2026-99-99"), encoding="utf-8")
        self.assertTrue(self.catalog().errors)

    def test_draft_reference_is_not_current(self):
        self.document("draft.md", "doc://test/draft", "document", "测试。", kind="reference", status="draft",
                      links=[{"type": "describes", "target": "module://test/m"}])
        result = context(self.catalog(), "module://test/m")
        self.assertNotIn("doc://test/draft", [item["uri"] for item in result["current"]])
        self.assertIn("doc://test/draft", [item["uri"] for item in result["pending_or_rejected"]])

    def test_init_escapes_project_name_in_metadata(self):
        name = '测试夹具的“新项目”与 "引号"'
        code, result = self.cli("init", "--target", str(self.base / "quoted"), "--project-id", "quoted", "--name", name)
        self.assertEqual(code, 0, result)
        copied = Catalog(result["config"])
        self.assertEqual(copied.get("project://quoted")["name"], name)
        self.assertEqual(copied.config["project_name"], name)

    def test_init_rebinds_and_refuses_overwrite(self):
        with (self.docs / "m.md").open("a", encoding="utf-8") as file:
            file.write("项目为 project://test；引用中文标点。\n")
        target = self.base / "新项目"
        code, result = self.cli("init", "--target", str(target), "--project-id", "new-project", "--name", "新的测试项目")
        self.assertEqual(code, 0, result)
        copied = Catalog(result["config"])
        self.assertEqual(copied.errors, [])
        self.assertEqual(copied.project, "project://new-project")
        self.assertIn("module://new-project/m", copied.objects)
        self.assertEqual(copied.sync_status()[0]["status"], "未登记核对")
        self.assertEqual(self.cli("init", "--target", str(target), "--project-id", "new-project", "--name", "测试")[0], 2)
        self.assertIn("module://test/m", self.catalog().objects)

    def test_index_stores_relative_locations_and_queries_use_live_source(self):
        self.assertEqual(self.cli("index")[0], 0)
        index = read_json(self.gov / "state/index.json")
        self.assertTrue(all("path" not in obj and not Path(obj["location"]).is_absolute() for obj in index["objects"]))
        (self.gov / "state/index.json").write_text("损坏的旧索引", encoding="utf-8")
        self.assertEqual(self.cli("resolve", "module://test/m")[0], 0)


if __name__ == "__main__":
    unittest.main()
