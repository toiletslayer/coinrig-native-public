"""Offline integration checks for the public HiveOS source package.

No wallet, mining node, external network, or real XMRig process is used.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
PACKAGE = BASE / "coinrig-native"
WALLET = "C" + "1" * 94
ENDPOINT = "10.12.34.56:38881"

spec = importlib.util.spec_from_file_location("coinrig_gate_public", PACKAGE / "submission-gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def posix_path(p: Path) -> str:
    p = p.resolve()
    if os.name == "nt":
        return "/" + p.drive[0].lower() + p.as_posix().split(":", 1)[1]
    return str(p)


def bash_exe() -> str:
    if os.name == "nt":
        return r"C:\Program Files\Git\bin\bash.exe"
    return shutil.which("bash") or "bash"


def run_bash(script: str, *, env: dict[str, str] | None = None, cwd: Path | None = None,
             timeout=12):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    command = script
    if os.name == "nt":
        # Git Bash resolves WindowsApps python3 stub; prepend a temporary shim.
        binary = posix_path(Path(sys.executable))
        command = f"python3() {{ {binary} \"$@\"; }}\nexport -f python3\n" + script
    return subprocess.run([bash_exe(), "-lc", command], capture_output=True, text=True,
                          cwd=cwd, env=merged, timeout=timeout)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.miner = self.directory / "hive" / "miners" / "custom" / "coinrig-native"
        self.miner.mkdir(parents=True)
        self.unrelated_cwd = self.directory / "tmp" / "coin-native-test" / "xmrig-6.26.0-coin"
        self.unrelated_cwd.mkdir(parents=True)
        for name in ("h-config.sh", "h-run.sh", "h-stats.sh", "h-manifest.conf",
                     "submission-gate.py"):
            shutil.copy2(PACKAGE / name, self.miner / name)

    def configure(self, *, cwd: Path | None = None, **overrides):
        options = {
            "MINER_DIR": posix_path(self.miner),
            "CUSTOM_URL": ENDPOINT,
            "CUSTOM_TEMPLATE": WALLET,
            "CUSTOM_ALGO": "rx/2",
            "CUSTOM_USER_CONFIG": "threads=32",
        }
        options.update(overrides)
        return run_bash(f"source {posix_path(self.miner / 'h-config.sh')}", env=options,
                        cwd=cwd)

    def test_config_valid(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads((self.miner / "config.json").read_text())
        self.assertEqual((self.miner / ".gateway").read_text().strip(), ENDPOINT)
        self.assertEqual(obj["pools"][0]["user"], WALLET)
        self.assertEqual(obj["pools"][0]["url"], "127.0.0.1:18882")
        self.assertEqual(obj["cpu"]["rx/2"], list(range(32)))
        self.assertEqual(obj["randomx"]["mode"], "fast")
        self.assertFalse(obj["randomx"]["wrmsr"])
        self.assertFalse(obj["randomx"]["rdmsr"])
        self.assertEqual(obj["pools"][0]["daemon"], True)
        self.assertTrue((self.miner / "config.json").stat().st_size > 100)

    def test_config_uses_installed_package_with_hiveos_parent_miner_dir(self):
        result = self.configure(
            cwd=self.unrelated_cwd,
            MINER_DIR=posix_path(self.miner.parent),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.miner / "config.json").is_file())
        self.assertEqual((self.miner / ".gateway").read_text().strip(), ENDPOINT)
        self.assertFalse((self.miner.parent / "config.json").exists())
        self.assertFalse((self.miner.parent / ".gateway").exists())

    def test_config_allows_explicit_package_dir_override_for_tests(self):
        callbacks = self.directory / "callbacks"
        callbacks.mkdir()
        shutil.copy2(PACKAGE / "h-config.sh", callbacks / "h-config.sh")
        options = {
            "MINER_DIR": posix_path(self.miner.parent),
            "COINRIG_PACKAGE_DIR": posix_path(self.miner),
            "CUSTOM_URL": ENDPOINT,
            "CUSTOM_TEMPLATE": WALLET,
            "CUSTOM_ALGO": "rx2",
            "CUSTOM_USER_CONFIG": "threads=32",
        }
        result = run_bash(
            f"source {posix_path(callbacks / 'h-config.sh')}",
            env=options,
            cwd=self.unrelated_cwd,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.miner / "config.json").is_file())
        self.assertEqual((self.miner / ".gateway").read_text().strip(), ENDPOINT)

    def test_stats_uses_installed_helper_with_hiveos_parent_miner_dir(self):
        trace = self.directory / "stats-helper-argv.txt"
        fake_python = self.directory / "fake-python"
        fake_python.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$1\" > \"$TRACE_FILE\"\n"
            "printf '12.5\\t{\"hashrate\":12500}\\n'\n",
            encoding="utf-8",
            newline="\n",
        )
        if os.name != "nt":
            fake_python.chmod(0o755)
        env = {
            "MINER_DIR": posix_path(self.miner.parent),
            "PYTHON_BIN": posix_path(fake_python),
            "TRACE_FILE": posix_path(trace),
        }
        script = (
            f"source {posix_path(self.miner / 'h-stats.sh')}\n"
            "printf 'KHS=%s\\nSTATS=%s\\n' \"$khs\" \"$stats\""
        )
        result = run_bash(script, env=env, cwd=self.unrelated_cwd)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("KHS=12.5", result.stdout)
        self.assertIn('STATS={"hashrate":12500}', result.stdout)
        self.assertEqual(
            trace.read_text(encoding="utf-8").strip(),
            posix_path(self.miner / "submission-gate.py"),
        )

    def test_accepts_all_three_rfc1918_ranges(self):
        for host in ("10.1.2.3", "172.19.2.5", "192.168.1.222"):
            with self.subTest(host=host):
                result = self.configure(CUSTOM_URL=f"{host}:38881")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((self.miner / ".gateway").read_text().strip(), f"{host}:38881")

    def test_hiveos_rx2_alias_is_normalized(self):
        result = self.configure(CUSTOM_ALGO="rx2")
        self.assertEqual(result.returncode, 0, result.stderr)
        config = json.loads((self.miner / "config.json").read_text())
        self.assertEqual(config["pools"][0]["algo"], "rx/2")
        self.assertEqual(config["cpu"]["rx/2"], list(range(32)))

    def test_invalid_gateway_fail_closed(self):
        for url in ("", "127.0.0.1:38881", "8.8.8.8:38881",
                    "localhost:38881", "192.168.0.1:0", "10.0.0.2:99999",
                    "http://10.0.0.2:38881", "172.32.0.1:38881"):
            with self.subTest(url=url):
                for stale in (self.miner / "config.json", self.miner / ".gateway"):
                    stale.unlink(missing_ok=True)
                result = self.configure(CUSTOM_URL=url)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.miner / "config.json").exists())

    def test_invalid_wallet_and_policy_fail_closed(self):
        for override in ({"CUSTOM_TEMPLATE": "D" + "1" * 94},
                         {"CUSTOM_TEMPLATE": "C" + "0" * 94},
                         {"CUSTOM_ALGO": "rx/0"},
                         {"CUSTOM_USER_CONFIG": "threads=8"}):
            with self.subTest(override=override):
                (self.miner / "config.json").unlink(missing_ok=True)
                result = self.configure(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.miner / "config.json").exists())

    def test_validate_generated_config(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        cmd = [sys.executable, str(self.miner / "submission-gate.py"),
               "validate-config", "--config", str(self.miner / "config.json")]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads((self.miner / "config.json").read_text())
        obj["randomx"]["mode"] = "light"
        (self.miner / "config.json").write_text(json.dumps(obj))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_hive_shell_callbacks_syntax(self):
        for name in ("h-config.sh", "h-run.sh", "h-stats.sh"):
            result = run_bash(f"bash -n {posix_path(self.miner / name)}")
            self.assertEqual(result.returncode, 0, name + ": " + result.stderr)

    def test_gate_only_forwards_known_rpc_methods(self):
        # Source-level gate check plus endpoint parsing: full daemon acceptance
        # remains an independent live-network test.
        import inspect
        handler_source = inspect.getsource(gate.make_handler)
        self.assertIn('method not in {"getblocktemplate", "submitblock"}', handler_source)
        self.assertIn('and not ready_file.is_file()', handler_source)
        self.assertIn('self._send(403', handler_source)

if __name__ == "__main__":
    unittest.main()
