import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HAS_PYTEST = all(importlib.util.find_spec(name) for name in ("pytest", "pytest_django", "django"))


@unittest.skipUnless(HAS_PYTEST, "Install the pytest extra to run plugin integration tests")
class PytestPluginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (ROOT / "reports").mkdir(exist_ok=True)

    def invoke(self, output, *options):
        env = dict(os.environ)
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        env.pop("PYTEST_ADDOPTS", None)
        return subprocess.run([
            sys.executable, "-m", "pytest", "-p", "pytest_django.plugin", "-p", "saferevoke.pytest_plugin",
            "-c", str(ROOT / "pyproject.toml"), "--ds=examples.django_pytest.settings", "--tb=short", "-q", "--saferevoke-output", str(output), *options,
        ], cwd=ROOT, env=env, capture_output=True, text=True, timeout=90)

    def test_existing_tests_run_unchanged_when_plugin_disabled(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            result = self.invoke(Path(folder) / "output", "examples/django_pytest")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("4 passed", result.stdout)
            self.assertFalse((Path(folder) / "output" / "report.json").exists())

    def test_existing_assertions_detect_mutations_and_prelogged_client_still_works(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            result = self.invoke(folder, "examples/django_pytest", "--saferevoke",
                                 "--saferevoke-deny", "group:operators:auth.view_user",
                                 "--saferevoke-deny", "user:alice:auth.view_group",
                                 "--saferevoke-deny", "user:alice:auth.add_group")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("3 failed, 13 passed", result.stdout)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(report["baseline_failures"], [])
            self.assertEqual(len(report["runs"]), 16)
            self.assertEqual(len(report["findings"]), 12)
            failures = [item for item in report["findings"] if item["classification"] == "REQUIRED_ACCESS"]
            self.assertEqual(len(failures), 3)
            partial = [item for item in report["findings"] if "test_staff_can_list_groups" in item["test"]
                       and item["denied"] == "user:alice:auth.view_group"]
            self.assertEqual(partial[0]["classification"], "PARTIAL_REMOVAL")
            self.assertTrue(all(item.get("database_restored") for item in report["runs"]))
            self.assertTrue((Path(folder) / "report.html").exists())

    def test_absent_target_is_not_reported_safe(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            result = self.invoke(folder, "examples/django_pytest", "--saferevoke",
                                 "--saferevoke-deny", "group:missing:auth.view_user")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual({item["classification"] for item in report["findings"]}, {"NOT_APPLICABLE"})

    def test_requires_explicit_permission_selector(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            result = self.invoke(folder, "examples/django_pytest", "--saferevoke")
            self.assertEqual(result.returncode, 4)
            self.assertIn("Supply at least one", result.stderr)

    def test_test_body_exception_rolls_back_permission_and_write_before_fixture_teardown(self):
        from textwrap import dedent
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            fixture = Path(folder) / "test_cleanup.py"
            fixture.write_text(dedent('''
                import pytest
                @pytest.fixture
                def user(db):
                    from django.contrib.auth import get_user_model
                    from django.contrib.auth.models import Permission, Group
                    user = get_user_model().objects.create_user(username="alice")
                    permission = Permission.objects.get(content_type__app_label="auth", codename="view_user")
                    user.user_permissions.add(permission)
                    assert user.has_perm("auth.view_user")  # Deliberately populate the cache.
                    yield user
                    assert user.user_permissions.filter(pk=permission.pk).exists()
                    assert not Group.objects.filter(name="transient-write").exists()
                def test_permission(user):
                    from django.contrib.auth.models import Group
                    Group.objects.create(name="transient-write")
                    assert user.has_perm("auth.view_user")
            '''), encoding="utf-8")
            output = Path(folder) / "results"
            result = self.invoke(output, str(fixture), "--saferevoke",
                                 "--saferevoke-deny", "user:alice:auth.view_user")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((output / "report.json").read_text())
            self.assertTrue(all(item.get("database_restored") for item in report["runs"]))
            self.assertTrue(all(item["teardown"] == "passed" for item in report["runs"]))
            self.assertEqual(report["findings"][0]["classification"], "REQUIRED_ACCESS")

    def test_baseline_setup_failure_is_inconclusive(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            fixture = Path(folder) / "test_bad_setup.py"
            fixture.write_text("import pytest\n@pytest.fixture\ndef broken():\n    raise RuntimeError('bad setup')\ndef test_bad(broken):\n    pass\n", encoding="utf-8")
            result = self.invoke(folder, str(fixture), "--saferevoke",
                                 "--saferevoke-deny", "user:alice:auth.view_user")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            self.assertEqual(len(report["baseline_failures"]), 1)
            self.assertEqual(report["findings"][0]["classification"], "INCONCLUSIVE")

    def test_affected_selection_omits_fixture_setup_and_keeps_same_failures(self):
        from textwrap import dedent
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            fixture = Path(folder) / "test_selection.py"
            counter = Path(folder) / "setup_calls.txt"
            fixture.write_text(dedent('''
                import pytest
                from pathlib import Path
                @pytest.fixture
                def user(db):
                    from django.contrib.auth import get_user_model
                    from django.contrib.auth.models import Permission
                    counter = Path(__file__).with_name('setup_calls.txt')
                    with counter.open('a') as stream:
                        stream.write('setup\\n')
                    user = get_user_model().objects.create_user(username='alice')
                    user.user_permissions.add(*Permission.objects.filter(
                        content_type__app_label='auth', codename__in=['view_user', 'view_group']))
                    return user
                def test_affected(user):
                    assert user.has_perm('auth.view_user')
                def test_unrelated(user):
                    assert user.has_perm('auth.view_group')
            '''), encoding="utf-8")
            all_dir, affected_dir = Path(folder) / "all", Path(folder) / "affected"
            common = [str(fixture), "--saferevoke", "--saferevoke-deny", "user:alice:auth.view_user"]
            all_result = self.invoke(all_dir, *common)
            self.assertEqual(all_result.returncode, 1, all_result.stdout + all_result.stderr)
            all_setups = len(counter.read_text().splitlines())
            affected_result = self.invoke(affected_dir, *common, "--saferevoke-selection", "affected")
            self.assertEqual(affected_result.returncode, 1, affected_result.stdout + affected_result.stderr)
            affected_setups = len(counter.read_text().splitlines()) - all_setups
            self.assertEqual((all_setups, affected_setups), (4, 3))
            exhaustive = json.loads((all_dir / "report.json").read_text())
            selected = json.loads((affected_dir / "report.json").read_text())
            failed_all = {item["test"] for item in exhaustive["findings"] if item["classification"] == "REQUIRED_ACCESS"}
            failed_selected = {item["test"] for item in selected["findings"] if item["classification"] == "REQUIRED_ACCESS"}
            self.assertEqual(failed_all, failed_selected)
            self.assertEqual(selected["counts"]["mutation_variants_omitted"], 1)
            self.assertEqual(selected["counts"]["test_bodies_executed"], 3)
            self.assertTrue(any(item["classification"] == "NOT_SELECTED" for item in selected["findings"]))
            self.assertIn("dependencies", selected["selection"])
            self.assertEqual([item["denied"] for item in selected["runs"][:2]], [None, None])

    def test_empty_trace_and_explicit_full_marker_keep_tests_selected(self):
        from textwrap import dedent
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            fixture = Path(folder) / "test_conservative.py"
            fixture.write_text(dedent('''
                import pytest
                @pytest.fixture
                def user(db):
                    from django.contrib.auth import get_user_model
                    from django.contrib.auth.models import Permission
                    user = get_user_model().objects.create_user(username='alice')
                    user.user_permissions.add(*Permission.objects.filter(
                        content_type__app_label='auth', codename__in=['view_user', 'view_group']))
                    return user
                def test_no_permission_checks(user):
                    assert user.username == 'alice'
                @pytest.mark.saferevoke_full
                def test_force_every_mutation(user):
                    assert user.has_perm('auth.view_group')
                def test_permission_enumeration(user):
                    assert 'auth.view_user' in user.get_all_permissions()
                def test_direct_enumeration_with_unrelated_check(user):
                    assert user.has_perm('auth.view_group')
                    assert 'auth.view_user' in user.get_user_permissions()
                def test_negative_check(user):
                    user.is_active = False
                    assert not user.has_perm('auth.view_user')
                def test_uncertain_object_level_check(user):
                    assert user.has_perm('auth.view_group')
                    assert not user.has_perm('auth.view_group', obj=object())
            '''), encoding="utf-8")
            result = self.invoke(Path(folder) / "result", str(fixture), "--saferevoke",
                                 "--saferevoke-deny", "user:alice:auth.view_user",
                                 "--saferevoke-selection", "affected")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "result" / "report.json").read_text())
            self.assertEqual(report["counts"]["mutation_variants_omitted"], 0)
            self.assertEqual(report["counts"]["test_bodies_executed"], 12)
            uncertain = [item for item in report["runs"] if "test_uncertain_object_level_check" in item["test"]
                         and item["denied"] is None]
            self.assertTrue(uncertain[0]["trace_uncertainties"])
            self.assertTrue(any(item["classification"] == "REQUIRED_ACCESS" for item in report["findings"]
                                if "test_permission_enumeration" in item["test"]))

    def test_admin_selection_keeps_all_detected_failures(self):
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            result = self.invoke(folder, "examples/django_pytest", "--saferevoke",
                                 "--saferevoke-deny", "group:operators:auth.view_user",
                                 "--saferevoke-deny", "user:alice:auth.view_group",
                                 "--saferevoke-deny", "user:alice:auth.add_group",
                                 "--saferevoke-selection", "affected")
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "report.json").read_text())
            failures = [item for item in report["findings"] if item["classification"] == "REQUIRED_ACCESS"]
            self.assertEqual(len(failures), 3)
            self.assertGreater(report["counts"]["mutation_variants_omitted"], 0)
            self.assertLess(report["counts"]["test_bodies_executed"], 16)

    def test_affected_selection_keeps_a_denial_triggered_privileged_fallback(self):
        from textwrap import dedent
        with tempfile.TemporaryDirectory(dir=ROOT / "reports") as folder:
            fixture = Path(folder) / "test_runtime_fallback.py"
            fixture.write_text(dedent('''
                import pytest
                @pytest.fixture
                def identities(db):
                    from django.contrib.auth import get_user_model
                    from django.contrib.auth.models import Permission
                    User = get_user_model()
                    reader = User.objects.create_user(username='reader')
                    fallback = User.objects.create_user(username='fallback')
                    view = Permission.objects.get(content_type__app_label='auth', codename='view_user')
                    delete = Permission.objects.get(content_type__app_label='auth', codename='delete_user')
                    reader.user_permissions.add(view)
                    fallback.user_permissions.add(view, delete)
                    return reader, fallback
                def test_still_succeeds(identities):
                    reader, fallback = identities
                    assert reader.has_perm('auth.view_user') or fallback.has_perm('auth.view_user')
            '''), encoding="utf-8")
            result = self.invoke(Path(folder) / "result", str(fixture), "--saferevoke",
                                 "--saferevoke-deny", "user:reader:auth.view_user",
                                 "--saferevoke-selection", "affected")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((Path(folder) / "result" / "report.json").read_text())
            self.assertEqual(report["counts"]["mutation_variants_omitted"], 0)
            self.assertEqual(report["findings"][0]["classification"], "UNSAFE_FALLBACK")
            self.assertTrue(report["findings"][0]["risk_evidence"])
