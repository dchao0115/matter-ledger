from __future__ import annotations

import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_cli as base
from catalog import Catalog, read_json, write_json
import logic

IMPLEMENTED = "## 问题\n测试。\n## 真实备选\n测试。\n## 决定与后果\n测试。"
PROPOSED = "## 问题\n测试。\n## 真实备选\n测试。\n## 提案与验收\n测试。"
MODULE = "## 职责\n测试。\n## 输入与输出\n测试。\n## 开发与验证\n测试。\n## 关联资料\n测试。"


def snapshot(root):
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class LogicTests(unittest.TestCase):
    """复用 test_cli 的夹具；夹具的规则层取自交付包治理层 ontology.json。"""

    config = base.GovernanceTests.config
    catalog = base.GovernanceTests.catalog
    document = base.GovernanceTests.document
    module = base.GovernanceTests.module
    cli = base.GovernanceTests.cli

    def setUp(self):
        base.GovernanceTests.setUp(self)
        self.document("project.md", "project://test", "project",
                      "## 目标与边界\n测试夹具。\n## 当前状态\n测试中。\n## 开始工作\n测试入口。",
                      related=["module://test/m"])

    def logic(self):
        code, output = self.cli("check", "--logic")
        return code, output["logic"]

    def found(self, report, rule):
        return [v for v in report["business_state"]["violations"] if v["rule"] == rule]

    def registry(self):
        return read_json(self.gov / "ontology.json")

    def save(self, registry):
        write_json(self.gov / "ontology.json", registry)

    def decision(self, name, status, body=IMPLEMENTED, links=(), **fields):
        return self.document(name + ".md", "decision://test/" + name, "decision", body, status=status,
                             links=[{"type": "affects", "target": "module://test/m"}, *links], **fields)

    def test_plain_check_output_is_unchanged(self):
        code, output = self.cli("check")
        self.assertEqual(code, 0)
        self.assertEqual(set(output), {"ok", "errors", "warnings", "sync", "objects", "links", "limit"})

    def test_clean_fixture_passes_every_rule(self):
        code, report = self.logic()
        self.assertEqual(code, 0, report)
        self.assertTrue(report["ok"])
        self.assertEqual(report["business_state"]["verdict"], "全过")
        summary = report["business_state"]["summary"]
        self.assertEqual(summary["executed"], len(self.registry()["rule_layer"]["rules"]))
        self.assertEqual(summary["violated"], 0)
        self.assertEqual(report["run_state"]["state"], "succeeded")
        self.assertFalse(report["contract"]["modifies_files"])
        for item in report["business_state"]["rules"]:
            self.assertEqual(item["result"], "通过")
            self.assertTrue(item["statement"] and item["governs"]["object_types"] and item["derived_from"])

    def test_superseded_decision_must_leave_current(self):
        self.decision("old", "implemented")
        self.decision("new", "implemented", links=[{"type": "supersedes", "target": "decision://test/old"}])
        self.assertEqual(self.catalog().errors, [])
        code, report = self.logic()
        self.assertEqual(code, 2)
        self.assertEqual(report["business_state"]["verdict"], "有错误")
        [item] = self.found(report, "RULE-DECISION-001")
        self.assertEqual((item["object"], item["severity"]), ("decision://test/old", "error"))
        self.decision("old", "implemented", archived_at="2026-10-05")
        self.assertEqual(self.logic()[0], 0)

    def test_superseded_proposal_must_be_rejected(self):
        self.decision("old", "proposed", PROPOSED)
        self.decision("new", "implemented", links=[{"type": "supersedes", "target": "decision://test/old"}])
        self.assertEqual(len(self.found(self.logic()[1], "RULE-DECISION-001")), 1)
        self.decision("old", "rejected", PROPOSED)
        self.assertEqual(self.found(self.logic()[1], "RULE-DECISION-001"), [])

    def test_rejected_decision_cannot_supersede(self):
        self.decision("old", "implemented")
        self.decision("new", "rejected", PROPOSED, links=[{"type": "supersedes", "target": "decision://test/old"}])
        [item] = self.found(self.logic()[1], "RULE-DECISION-001")
        self.assertEqual(item["object"], "decision://test/new")

    def test_decision_without_affects_warns(self):
        self.document("loose.md", "decision://test/loose", "decision", IMPLEMENTED, status="implemented")
        self.document("old.md", "decision://test/old", "decision", IMPLEMENTED, status="implemented",
                      archived_at="2026-10-05")
        code, report = self.logic()
        self.assertEqual(code, 0)
        self.assertEqual(report["business_state"]["verdict"], "有警告")
        [item] = self.found(report, "RULE-DECISION-002")
        self.assertEqual((item["object"], item["root"], item["location"]), ("decision://test/loose", "docs", "loose.md"))
        for key in ("decision_point", "option_a", "option_b", "recommend"):
            self.assertTrue(item[key].strip())
        self.assertNotIn("RULE-", item["decision_point"])

    def test_dependency_cycle_is_error(self):
        self.module("b", "planned", ["module://test/c"])
        self.module("c", "planned", ["module://test/d"])
        self.module("d", "planned", ["module://test/b"])
        self.assertEqual(self.catalog().errors, [])
        code, report = self.logic()
        self.assertEqual(code, 2)
        [item] = self.found(report, "RULE-LINK-001")
        self.assertEqual(sorted(item["involved"]), ["module://test/b", "module://test/c", "module://test/d"])
        self.assertIn("「依赖」关系绕成了环", item["decision_point"])
        self.module("d", "planned")
        self.assertEqual(self.found(self.logic()[1], "RULE-LINK-001"), [])

    def test_supersession_cycle_is_error(self):
        self.document("a.md", "doc://test/a", "document", "测试。", kind="reference",
                      links=[{"type": "describes", "target": "module://test/m"}, {"type": "supersedes", "target": "doc://test/b"}])
        self.document("b.md", "doc://test/b", "document", "测试。", kind="reference",
                      links=[{"type": "describes", "target": "module://test/m"}, {"type": "supersedes", "target": "doc://test/a"}])
        [item] = self.found(self.logic()[1], "RULE-LINK-001")
        self.assertIn("「完整替代」", item["decision_point"])

    def test_cycle_search_handles_long_chains(self):
        nodes = [f"n{i:05d}" for i in range(5000)]
        graph = {a: {b} for a, b in zip(nodes, nodes[1:])}
        self.assertEqual(logic.components(graph), [])
        graph[nodes[-1]] = {nodes[0]}
        [component] = logic.components(graph)
        self.assertEqual(len(component), 5000)
        self.assertEqual(logic.shortest_cycle(graph, component), [*nodes, nodes[0]])

    def test_active_module_depending_on_planned_warns(self):
        self.module("b", "planned")
        self.module("m", "active", ["module://test/b"])
        code, report = self.logic()
        self.assertEqual(code, 0)
        [item] = self.found(report, "RULE-LINK-002")
        self.assertEqual(item["involved"], ["module://test/m", "module://test/b"])

    def test_module_missing_from_project_entry_warns(self):
        self.module("b", "planned")
        [item] = self.found(self.logic()[1], "RULE-MODULE-001")
        self.assertEqual(item["object"], "module://test/b")
        self.module("b", "retired")
        self.assertEqual(self.found(self.logic()[1], "RULE-MODULE-001"), [])

    def test_document_without_owner_warns(self):
        self.document("orphan.md", "doc://test/orphan", "document", "测试。", kind="reference",
                      related=["module://test/m"])
        [item] = self.found(self.logic()[1], "RULE-DOC-001")
        self.assertEqual(item["object"], "doc://test/orphan")
        self.document("orphan.md", "doc://test/orphan", "document", "测试。", kind="reference", status="archived")
        self.assertEqual(self.found(self.logic()[1], "RULE-DOC-001"), [])

    def test_record_in_module_folder_must_attach_to_it(self):
        self.document("x/AGENTS.md", "module://test/x", "module", MODULE, status="planned")
        self.document("x/notes.md", "doc://test/x-notes", "document", "测试。", kind="reference",
                      links=[{"type": "describes", "target": "module://test/m"}])
        [item] = self.found(self.logic()[1], "RULE-DOC-002")
        self.assertEqual((item["location"], item["involved"]), ("x/notes.md", ["doc://test/x-notes", "module://test/x"]))
        self.document("x/notes.md", "doc://test/x-notes", "document", "测试。", kind="reference",
                      links=[{"type": "describes", "target": "module://test/x"}])
        self.assertEqual(self.found(self.logic()[1], "RULE-DOC-002"), [])

    def test_invalid_active_rule_is_reported_not_skipped(self):
        registry = self.registry()
        rules = registry["rule_layer"]["rules"]
        rules[0]["check"]["function"] = "missing"
        del rules[1]["statement"]
        self.save(registry)
        code, report = self.logic()
        self.assertEqual(code, 2)
        self.assertEqual(report["run_state"]["state"], "partial")
        errors = report["run_state"]["rule_layer_errors"]
        self.assertTrue(any(e.startswith(rules[0]["ruleId"]) and "check.function" in e for e in errors))
        self.assertTrue(any(e.startswith(rules[1]["ruleId"]) and "缺少 statement" in e for e in errors))
        self.assertEqual(report["business_state"]["summary"]["executed"], len(rules) - 2)

    def test_candidate_rule_is_registered_but_not_run(self):
        registry = self.registry()
        rule = copy.deepcopy(registry["rule_layer"]["rules"][0])
        rule.update(ruleId="RULE-TEST-001", status="candidate")
        registry["rule_layer"]["rules"].append(rule)
        registry["rule_layer"]["rules"].append({"ruleId": "RULE-TEST-002", "name": "待补全", "status": "candidate"})
        self.save(registry)
        code, report = self.logic()
        self.assertEqual(code, 0, report)
        results = {r["rule"]: r["result"] for r in report["business_state"]["rules"]}
        self.assertEqual((results["RULE-TEST-001"], results["RULE-TEST-002"]), ("未启用", "定义无效，未执行"))
        self.assertTrue(any(w.startswith("RULE-TEST-002") for w in report["run_state"]["rule_layer_warnings"]))

    def test_logic_without_active_rules_does_not_pass(self):
        registry = self.registry()
        for rule in registry["rule_layer"]["rules"]:
            rule["status"] = "deprecated"
        self.save(registry)
        code, report = self.logic()
        self.assertEqual((code, report["run_state"]["state"], report["business_state"]["verdict"]), (2, "skipped", "未执行"))
        del registry["rule_layer"]
        self.save(registry)
        code, report = self.logic()
        self.assertEqual((code, report["run_state"]["state"]), (2, "skipped"))
        self.assertEqual(self.cli("check")[0], 0)

    def test_structure_errors_skip_logic(self):
        (self.docs / "duplicate.md").write_bytes((self.docs / "m.md").read_bytes())
        code, output = self.cli("check", "--logic")
        self.assertEqual(code, 2)
        self.assertTrue(output["errors"])
        self.assertEqual(output["logic"]["run_state"]["state"], "skipped")

    def test_unregistered_rule_source_warns(self):
        registry = self.registry()
        registry["rule_layer"]["rules"][0]["source"] = ["doc://test/missing"]
        self.save(registry)
        code, report = self.logic()
        self.assertEqual(code, 0)
        self.assertTrue(any("doc://test/missing" in w for w in report["run_state"]["rule_layer_warnings"]))

    def test_logic_check_writes_nothing(self):
        self.decision("old", "implemented")
        self.decision("new", "implemented", links=[{"type": "supersedes", "target": "decision://test/old"}])
        before = snapshot(self.base)
        self.assertEqual(self.logic()[0], 2)
        self.assertEqual(snapshot(self.base), before)

    def test_init_rebases_rule_sources(self):
        registry = self.registry()
        registry["rule_layer"]["rules"][0]["source"] = ["doc://test/rules"]
        self.save(registry)
        code, result = self.cli("init", "--target", str(self.base / "copied"), "--project-id", "copied", "--name", "复制项目")
        self.assertEqual(code, 0, result)
        copied = read_json(Path(result["config"]).parent / "ontology.json")
        self.assertEqual(copied["rule_layer"]["rules"][0]["source"], ["doc://copied/rules"])
        self.assertEqual(copied["rule_layer"]["object_types"], registry["rule_layer"]["object_types"])
        self.assertEqual(copied["object_types"], registry["object_types"])
        report = logic.run(Catalog(result["config"]))
        self.assertTrue(report["ok"], report)
        self.assertFalse(any("doc://copied/rules" in w for w in report["run_state"]["rule_layer_warnings"]))

    def test_implemented_decision_must_be_referenced(self):
        self.decision("lonely", "implemented")
        [item] = self.found(self.logic()[1], "RULE-DECISION-003")
        self.assertEqual((item["object"], item["severity"]), ("decision://test/lonely", "warning"))
        for key in ("decision_point", "option_a", "option_b", "recommend"):
            self.assertTrue(item[key].strip())
        self.assertNotIn("RULE-", item["decision_point"])

    def test_decision_referenced_via_related_or_body(self):
        self.decision("via-related", "implemented")
        self.document("owner.md", "doc://test/owner", "document", "测试。", kind="reference",
                      related=["module://test/m", "decision://test/via-related"])
        self.decision("via-body", "implemented")
        self.document("cite.md", "doc://test/cite", "document",
                      "现行做法见 decision://test/via-body 。", kind="reference",
                      links=[{"type": "describes", "target": "module://test/m"}])
        rule = [v for v in self.logic()[1]["business_state"]["violations"] if v["rule"] == "RULE-DECISION-003"]
        self.assertEqual(rule, [])

    def test_reference_from_non_current_object_does_not_count(self):
        self.decision("lonely", "implemented")
        self.document("draft-owner.md", "doc://test/draft-owner", "document", "测试。", kind="reference",
                      status="draft", related=["module://test/m", "decision://test/lonely"])
        found = [v for v in self.logic()[1]["business_state"]["violations"] if v["rule"] == "RULE-DECISION-003"]
        self.assertEqual([item["object"] for item in found], ["decision://test/lonely"])

    def test_archived_decision_exempt_from_reference_rule(self):
        self.decision("old", "implemented", archived_at="2026-10-05")
        found = [v for v in self.logic()[1]["business_state"]["violations"] if v["rule"] == "RULE-DECISION-003"]
        self.assertEqual(found, [])

    def test_proposed_decision_stale_reminder(self):
        self.decision("stuck", "proposed", PROPOSED, created="2026-01-01", updated="2026-01-01")
        [item] = [v for v in self.logic()[1]["business_state"]["violations"] if v["rule"] == "RULE-DECISION-004"]
        self.assertEqual((item["object"], item["severity"]), ("decision://test/stuck", "reminder"))
        self.decision("stuck", "proposed", PROPOSED)
        found = [v for v in self.logic()[1]["business_state"]["violations"] if v["rule"] == "RULE-DECISION-004"]
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
