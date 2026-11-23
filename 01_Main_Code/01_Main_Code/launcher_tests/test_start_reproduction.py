"""Tests of the convenience launcher only; no statistical analysis is executed."""
from __future__ import annotations
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cose_easy_start", ROOT / "start_reproduction.py")
launcher = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(launcher)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / "source with spaces"
        self.source.mkdir()
        self.workspace = self.base / "fresh"
        self.archive = self.base / "raw data.zip"
        self.archive.write_bytes(b"test data, not a dataset")

    def tearDown(self):
        self.temp.cleanup()

    def comparison_fixture(self):
        run = self.base / "results"
        comp = run / "comparison"
        comp.mkdir(parents=True)
        (comp / "COMPARISON_STATUS.json").write_text(json.dumps({"status":"MATCH","differing_cells_or_keys":0}))
        (comp / "AUDIT_COMPARISON_STATUS.json").write_text(json.dumps({"status":"MATCH","differences":0}))
        (comp / "V48_TABLE_COMPARISON.csv").write_text(
            "table,field,checked,different\nFINAL_RESULTS.csv,ROW_KEYS,352,0\nRECOVERY_CURVES.csv,ROW_KEYS,6608,0\n")
        (comp / "V48_PROSE_CLAIM_COMPARISON.csv").write_text("claim,status\nold S1b number,documented discrepancy\n")
        return run, comp

    def test_windows_plan_uses_scripts_python(self):
        plan = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)
        self.assertEqual(plan[2][1][0], str(self.workspace / "env/Scripts/python.exe"))
        self.assertEqual(len(plan), 12)

    def test_original_stages_remain_ordered(self):
        plan = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)
        self.assertEqual([x[1][-1] for x in plan[5:8]], ["raw","analysis","final"])
        self.assertTrue(all(str(self.source / "reproduce.py") in x[1] for x in plan[5:8]))

    def test_no_expected_results_in_fitting_commands(self):
        plan = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)
        for _,command in plan[5:8]:
            self.assertNotIn(str(self.source / "expected_v48"),command)
            self.assertNotIn("--reference",command)

    def test_package_and_input_checked_before_setup(self):
        plan = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)
        self.assertEqual(plan[0][1][-2:],["--raw",str(self.archive)])
        self.assertIn("verify_release.py",plan[0][1][2])
        self.assertIn("venv",plan[1][1])

    def test_pinned_requirements_preserved(self):
        command = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)[2][1]
        self.assertIn("--only-binary=:all:",command)
        self.assertEqual(command[-2:],["-r",str(self.source / "requirements.txt")])
        self.assertNotIn("--upgrade",command)

    def test_existing_workspace_refused(self):
        self.workspace.mkdir()
        with self.assertRaises(FileExistsError):
            launcher.check_workspace(self.source,self.workspace,False)

    def test_workspace_inside_source_refused(self):
        with self.assertRaises(ValueError):
            launcher.check_workspace(self.source,self.source / "newrun",False)

    def test_missing_parent_refused(self):
        with self.assertRaises(FileNotFoundError):
            launcher.check_workspace(self.source,self.base / "missing" / "run",False)

    def test_planning_creates_no_run_or_environment(self):
        launcher.check_workspace(self.source,self.workspace,False)
        launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)
        self.assertFalse(self.workspace.exists())

    def test_spaces_preserved_as_single_arguments(self):
        command = launcher.command_plan(self.source,self.workspace,self.archive,"python312",True)[5][1]
        self.assertEqual(command[command.index("--archive")+1],str(self.archive))
        self.assertIn(str(self.source / "reproduce.py"),command)

    def test_matching_comparisons_and_prose_exception(self):
        run,_ = self.comparison_fixture()
        result = launcher.check_comparisons(run)
        self.assertEqual(result["matched_rows"]["RECOVERY_CURVES.csv"],6608)
        self.assertIn("does not certify",result["scope"])

    def test_zero_process_exit_does_not_hide_numerical_differences(self):
        run,comp = self.comparison_fixture()
        (comp / "COMPARISON_STATUS.json").write_text(json.dumps({"status":"DIFFERENCES_REPORTED","differing_cells_or_keys":1}))
        with self.assertRaises(RuntimeError):
            launcher.check_comparisons(run)

    def test_audit_differences_refused(self):
        run,comp = self.comparison_fixture()
        (comp / "AUDIT_COMPARISON_STATUS.json").write_text(json.dumps({"status":"DIFFERENCES_REPORTED","differences":1}))
        with self.assertRaises(RuntimeError):
            launcher.check_comparisons(run)

    def test_missing_history_comparison_refused(self):
        run,comp = self.comparison_fixture()
        (comp / "V48_PROSE_CLAIM_COMPARISON.csv").unlink()
        with self.assertRaises(FileNotFoundError):
            launcher.check_comparisons(run)

    def test_real_subprocess_success_log(self):
        (self.workspace / "launcher_logs").mkdir(parents=True)
        records=[]
        with contextlib.redirect_stdout(io.StringIO()):
            launcher.run_logged("smoke_success",[sys.executable,"-c","print('launcher smoke test')"],self.source,self.workspace,records)
        self.assertEqual(records[0]["exit_code"],0)
        self.assertIn("launcher smoke test",(self.workspace / "launcher_logs/smoke_success.log").read_text())
        self.assertFalse((self.workspace / "run").exists())

    def test_real_subprocess_failure_preserved(self):
        (self.workspace / "launcher_logs").mkdir(parents=True)
        records=[]
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                launcher.run_logged("smoke_failure",[sys.executable,"-c","raise SystemExit(7)"],self.source,self.workspace,records)
        self.assertEqual(records[0]["exit_code"],7)
        self.assertTrue((self.workspace / "LAUNCHER_COMMANDS.json").is_file())

    def test_dry_run_writes_nothing(self):
        with contextlib.redirect_stdout(io.StringIO()) as capture:
            code=launcher.main(["--archive",str(self.archive),"--workspace",str(self.workspace),"--dry-run"])
        self.assertEqual(code,0)
        self.assertIn("DRY RUN ONLY",capture.getvalue())
        self.assertFalse(self.workspace.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
