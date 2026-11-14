from __future__ import annotations

import json
import io
import tarfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_cli as base
from catalog import read_json, write_json
from bundle import export_bundle, import_bundle, MANIFEST


class BundleTests(unittest.TestCase):
    """交付单元导出/导入的回归测试（2026-10-20 补，v4 升级前置条件）。

    只借用 test_cli 的夹具方法，不继承其 TestCase——继承会把父类 21 个用例
    在本类重复收集一遍，也会把 strict 等无关断言带进来。
    """

    config = base.GovernanceTests.config
    catalog = base.GovernanceTests.catalog
    document = base.GovernanceTests.document
    module = base.GovernanceTests.module
    cli = base.GovernanceTests.cli
    checkpoint = base.GovernanceTests.checkpoint

    def setUp(self):
        base.GovernanceTests.setUp(self)
        self.checkpoint()
        self.out = self.base / "bundle-out"

    def export(self, **kwargs):
        return export_bundle(self.catalog(), self.out, **kwargs)

    def archive(self):
        files = list(self.out.glob("*.docgov.tar.gz"))
        self.assertEqual(len(files), 1, f"期望恰好一个归档，实际 {[f.name for f in files]}")
        return files[0]

    # ── 导出 ──────────────────────────────────────────────────────────

    def test_export_creates_archive_and_manifest(self):
        result = self.export()
        archive = Path(result["archive"])
        self.assertTrue(archive.is_file())
        self.assertGreater(archive.stat().st_size, 0)

        with tarfile.open(archive, "r:gz") as tar:
            names = set(tar.getnames())
            self.assertIn(MANIFEST, names)
            self.assertIn("objects.json", names)
            self.assertIn("checkpoints.jsonl", names)
            manifest = json.loads(tar.extractfile(MANIFEST).read().decode("utf-8"))

        self.assertEqual(manifest["format"], "docgov-bundle-1")
        self.assertEqual(manifest["project"], "project://test")
        self.assertEqual(manifest["objects"]["total"], result["manifest"]["objects"]["total"])
        self.assertTrue(manifest["bundle_id"])
        self.assertTrue(manifest["bundle_hash"])

    def test_manifest_records_checkpoint_evidence(self):
        manifest = self.export()["manifest"]
        evidence = {item["module"]: item for item in manifest["evidence"]}
        self.assertIn("module://test/m", evidence)
        record = evidence["module://test/m"]
        self.assertEqual(record["evidence"], "doc://test/evidence")
        self.assertEqual(record["actor"], "agent:test")
        self.assertTrue(record["evidence_hash"])

    def test_project_record_cannot_be_omitted(self):
        with self.assertRaises(ValueError) as ctx:
            self.export(omit=["project://test"])
        self.assertIn("项目主记录不可省略", str(ctx.exception))

    def test_omitting_unregistered_uri_fails(self):
        with self.assertRaises(ValueError) as ctx:
            self.export(omit=["doc://test/not-exist"])
        self.assertIn("省略项未登记", str(ctx.exception))

    def test_omitting_verification_doc_fails(self):
        """活动模块的验证记录是必需证据，不得省略。"""
        with self.assertRaises(ValueError) as ctx:
            self.export(omit=["doc://test/evidence"])
        self.assertIn("验证记录不可省略", str(ctx.exception))

    def test_optional_document_can_be_omitted_with_reason(self):
        result = self.export(omit=["doc://test/rules"], note="对外交付不含内部规则")
        omissions = result["manifest"]["omissions"]
        self.assertEqual(len(omissions), 1)
        self.assertEqual(omissions[0]["uri"], "doc://test/rules")
        self.assertEqual(omissions[0]["availability"], "declared-omitted")
        self.assertEqual(omissions[0]["reason"], "对外交付不含内部规则")

    def test_export_refuses_invalid_catalog(self):
        (self.docs / "duplicate.md").write_bytes((self.docs / "m.md").read_bytes())
        with self.assertRaises(ValueError):
            self.export()

    # ── 导入 ──────────────────────────────────────────────────────────

    def test_import_restores_files_and_writes_receipt(self):
        self.export()
        target = self.base / "restored"
        report = import_bundle(self.archive(), target)

        self.assertEqual(report["source_project"], "project://test")
        self.assertEqual(report["objects"], self.catalog().objects.__len__())
        self.assertTrue((target / "import-receipt.json").is_file())
        restored = read_json(target / "import-receipt.json")
        self.assertEqual(restored["bundle_id"], report["bundle_id"])
        self.assertGreater(restored["files_restored"], 0)

        # 文档被还原到 files/ 下，内容一致
        restored_md = list((target / "files").rglob("m.md"))
        self.assertTrue(restored_md, "导入后应还原模块文档")
        self.assertIn("## 职责", restored_md[0].read_text(encoding="utf-8"))

    def test_import_rejects_non_empty_target(self):
        self.export()
        target = self.base / "occupied"
        target.mkdir()
        (target / "keep.txt").write_text("已存在\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            import_bundle(self.archive(), target)
        self.assertIn("不覆盖既有项目", str(ctx.exception))

    def test_import_detects_tampered_manifest(self):
        """bundle_hash 覆盖 manifest 全部内容，改一个字节即失败。"""
        self.export()
        archive = self.archive()
        tampered = self.base / "tampered.tar.gz"
        with tarfile.open(archive, "r:gz") as src, tarfile.open(tampered, "w:gz") as dst:
            for member in src.getmembers():
                data = src.extractfile(member).read()
                if member.name == MANIFEST:
                    manifest = json.loads(data.decode("utf-8"))
                    manifest["bundle_name"] = "被篡改的名字"
                    data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
                info = tarfile.TarInfo(member.name)
                info.size = len(data)
                dst.addfile(info, io.BytesIO(data))

        with self.assertRaises(ValueError) as ctx:
            import_bundle(tampered, self.base / "restored-tampered")
        self.assertIn("bundle_hash 不匹配", str(ctx.exception))

    def test_import_detects_tampered_file(self):
        self.export()
        archive = self.archive()
        tampered = self.base / "tampered-file.tar.gz"
        with tarfile.open(archive, "r:gz") as src, tarfile.open(tampered, "w:gz") as dst:
            for member in src.getmembers():
                data = src.extractfile(member).read()
                if member.name.startswith("files/") and member.name.endswith(".md"):
                    data = b"---\ntampered: true\n---\n"
                info = tarfile.TarInfo(member.name)
                info.size = len(data)
                dst.addfile(info, io.BytesIO(data))

        with self.assertRaises(ValueError) as ctx:
            import_bundle(tampered, self.base / "restored-file")
        self.assertIn("文件校验失败", str(ctx.exception))

    # ── v4 新增：skip_dirs 与导出共存 ─────────────────────────────────

    def test_skip_dirs_excludes_machine_state_from_fingerprint(self):
        """skip_dirs 指定的目录不参与指纹，也不因缓存写入逼模块重新核对。"""
        cache = self.code / "cache"
        cache.mkdir()
        (cache / "local.db").write_bytes(b"binary-state")

        # 未配置 skip_dirs：缓存文件参与指纹
        before = self.catalog().footprint("module://test/m")

        config = read_json(self.config)
        config["skip_dirs"] = ["cache"]
        write_json(self.config, config)

        self.checkpoint()
        after = self.catalog().footprint("module://test/m")
        self.assertEqual(before, after, "cache 未被登记为代码资产时本就不应影响指纹")

        # 缓存再写入不应改变指纹
        (cache / "local.db").write_bytes(b"binary-state-changed")
        self.assertEqual(self.catalog().footprint("module://test/m"), after)

    def test_skip_dirs_permits_declared_machine_state_docs(self):
        """机器状态目录里的 .md 默认报错；显式声明 skip_dirs 后放行。

        声明 skip_dirs 等于承诺该目录不是作者手写的资产内容——这条是纪律，
        不是工具能自动判定的，故用测试固定「必须显式声明才放行」这个边界。
        """
        (self.code / "cache").mkdir()
        (self.code / "cache" / "SKILL.md").write_text("缓存产物\n", encoding="utf-8")

        # 未声明：按「代码层含独立文档」拦下
        self.assertTrue(any("代码层含独立文档" in e for e in self.catalog().errors),
                        "未声明 skip_dirs 时应报错")

        config = read_json(self.config)
        config["skip_dirs"] = ["cache"]
        write_json(self.config, config)

        self.assertFalse(any("代码层含独立文档" in e for e in self.catalog().errors),
                         "显式声明 skip_dirs 后应放行")

    def test_code_md_allow_permits_declared_prefix(self):
        """code_md_allow 放行机器消费的模板说明，其余仍拦。"""
        (self.code / "templates").mkdir()
        (self.code / "templates" / "prompt.md").write_text("模板说明\n", encoding="utf-8")

        config = read_json(self.config)
        config["code_md_allow"] = ["templates"]
        write_json(self.config, config)

        self.assertFalse(any("代码层含独立文档" in e for e in self.catalog().errors))

    def test_export_with_skip_dirs_and_code(self):
        """v4 合并点：skip_dirs 与 include_code 同时生效。

        include_code 只打包目录型代码资产；单文件代码资产一律走 files/。
        skip_dirs 指定的目录（缓存/本地库）不得进入交付包。
        """
        # 目录型代码资产
        pkg = self.code / "pkg"
        pkg.mkdir()
        (pkg / "impl.py").write_text("value = 2\n", encoding="utf-8")
        assets = read_json(self.gov / "assets.json")
        assets.append({"uri": "code://test/pkg", "name": "目录型代码资产", "status": "active",
                       "location": "pkg", "links": [{"type": "implements", "target": "module://test/m"}]})
        write_json(self.gov / "assets.json", assets)

        # 机器状态目录
        cache = self.code / "cache"
        cache.mkdir()
        (cache / "local.db").write_bytes(b"state")
        (cache / "skill.md").write_text("缓存产物\n", encoding="utf-8")

        config = read_json(self.config)
        config["skip_dirs"] = ["cache"]
        write_json(self.config, config)

        result = self.export(include_code=True)
        archive = Path(result["archive"])

        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()

        self.assertTrue(any(n.startswith("code/") for n in names),
                        f"include_code 应打包目录型代码资产，实际 {names}")
        self.assertIn("code/pkg/impl.py", names)
        self.assertFalse(any("/cache/" in n for n in names),
                         f"skip_dirs 目录不应进入交付包，实际 {names}")


if __name__ == "__main__":
    unittest.main()
