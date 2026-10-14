"""Prove that the test wrapper excludes inherited Git config and preserves failures."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest


def check_test_recipes(makefile):
    """Pin every test/test-* recipe, including future targets, to the wrapper."""
    targets = []
    checked = set()
    lines = iter(enumerate(makefile.splitlines(), 1))
    for number, line in lines:
        if line.startswith("\t"):
            if not targets:
                continue
            recipe = line[1:]
            while recipe.endswith("\\"):
                try:
                    _, continuation = next(lines)
                except StopIteration:
                    raise ValueError(f"line {number}: incomplete test recipe") from None
                recipe = recipe[:-1] + continuation.lstrip()
        elif not line.strip() or line.lstrip().startswith("#"):
            continue
        else:
            rule = re.match(r"^([^:#=\t]+):(?![=])([^;]*)(?:;(.*))?$", line)
            targets = ([name for name in rule[1].split()
                        if name == "test" or name.startswith("test-")]
                       if rule else [])
            if not targets or rule[3] is None:
                continue
            recipe = rule[3]
        lexer = shlex.shlex(recipe.lstrip().removeprefix("@"), posix=True,
                            punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
        if not tokens:
            continue
        if (tokens[:2] != ["bash", "scripts/test-env.sh"] or len(tokens) < 3
                or any(token and set(token) <= set(";&|") for token in tokens)):
            raise ValueError(f"line {number}: {', '.join(targets)} must run every "
                             "command through bash scripts/test-env.sh")
        checked.update(targets)
    if not checked:
        raise ValueError("no wrapped test recipes found")
    return checked


class TestEnvironment(unittest.TestCase):
    def test_makefile_wiring(self):
        makefile = Path(__file__).resolve().parents[1] / "Makefile"
        checked = check_test_recipes(makefile.read_text())
        self.assertIn("test-env", checked)

    def test_guard_rejects_each_unwrapped_recipe(self):
        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
        recipes = [line for line in makefile.splitlines()
                   if line.startswith("\tbash scripts/test-env.sh ")]
        self.assertTrue(recipes)
        for recipe in recipes:
            with self.subTest(recipe=recipe):
                changed = makefile.replace(
                    recipe, recipe.replace("bash scripts/test-env.sh ", "", 1), 1)
                self.assertNotEqual(changed, makefile)
                with self.assertRaisesRegex(ValueError, "must run every command"):
                    check_test_recipes(changed)

    def test_guard_covers_new_targets_and_compound_commands(self):
        good = "test-future: ; bash scripts/test-env.sh python3 fixture.py\n"
        self.assertEqual(check_test_recipes(good), {"test-future"})
        continued = "test-future:\n\tbash scripts/test-env.sh \\\n\tpython3 fixture.py\n"
        self.assertEqual(check_test_recipes(continued), {"test-future"})
        for bad in ("test-future:\n\tpython3 fixture.py\n",
                    good.replace("fixture.py", "fixture.py; python3 unwrapped.py")):
            with self.subTest(makefile=bad):
                with self.assertRaisesRegex(ValueError, "test-future must run"):
                    check_test_recipes(bad)

    def test_requires_command(self):
        wrapper = Path(__file__).with_name("test-env.sh")
        result = subprocess.run(["bash", str(wrapper)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage:", result.stderr)

    def test_hostile_config_and_cleanup(self):
        wrapper = Path(__file__).with_name("test-env.sh")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "git").mkdir()
            (root / "git" / "config").write_text("[fixture]\n poison = xdg\n")
            global_config = root / "global"
            global_config.write_text("[fixture]\n poison = global\n")
            env = {**os.environ, "GIT_CONFIG_GLOBAL": str(global_config),
                   "XDG_CONFIG_HOME": str(root)}
            control = subprocess.run(["git", "config", "--global", "fixture.poison"],
                                     env=env, capture_output=True, text=True)
            self.assertEqual(control.returncode, 0)
            self.assertEqual(control.stdout.strip(), "global")
            (root / "home").mkdir()
            xdg_env = {**env, "HOME": str(root / "home")}
            del xdg_env["GIT_CONFIG_GLOBAL"]
            xdg_control = subprocess.run(["git", "config", "--global", "fixture.poison"],
                                         env=xdg_env, capture_output=True, text=True)
            self.assertEqual(xdg_control.returncode, 0)
            self.assertEqual(xdg_control.stdout.strip(), "xdg")
            xdg_probe = subprocess.run(["bash", str(wrapper), "bash", "-c",
                                        'printf "%s\\n" "$XDG_CONFIG_HOME"; '
                                        'unset GIT_CONFIG_GLOBAL; '
                                        'git config --global fixture.poison'],
                                       env=xdg_env, capture_output=True, text=True)
            self.assertEqual(xdg_probe.returncode, 1, xdg_probe.stderr)
            self.assertNotEqual(Path(xdg_probe.stdout.strip()), root)
            self.assertFalse(Path(xdg_probe.stdout.strip()).exists())
            probe = subprocess.run(["bash", str(wrapper), "bash", "-c",
                                    'printf "%s\\n" "$XDG_CONFIG_HOME"; '
                                    'git config --global fixture.poison'],
                                   env=env, capture_output=True, text=True)
            self.assertEqual(probe.returncode, 1, probe.stderr)
            self.assertFalse(Path(probe.stdout.strip()).exists())
            failure = subprocess.run(["bash", str(wrapper), "bash", "-c", "exit 42"], env=env)
            self.assertEqual(failure.returncode, 42)


if __name__ == "__main__":
    unittest.main()
