"""Prove that the test wrapper excludes inherited Git config and preserves failures."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TestEnvironment(unittest.TestCase):
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
