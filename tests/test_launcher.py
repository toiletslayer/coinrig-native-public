"""Offline wrapper lifecycle tests with fake XMRig and no actual node."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

try:
    from test_integration import BASE, PACKAGE, ENDPOINT, WALLET, bash_exe, posix_path, run_bash
except ImportError:
    from tests.test_integration import (
        BASE, PACKAGE, ENDPOINT, WALLET, bash_exe, posix_path, run_bash,
    )


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.miner = self.root / "hive" / "miners" / "custom" / "coinrig-native"
        self.miner.mkdir(parents=True)
        self.unrelated_cwd = self.root / "tmp" / "coin-native-test" / "xmrig-6.26.0-coin"
        self.unrelated_cwd.mkdir(parents=True)
        for name in ("h-config.sh", "h-run.sh", "h-stats.sh",
                     "h-manifest.conf", "submission-gate.py"):
            shutil.copy2(PACKAGE / name, self.miner / name)
        self.miner_log = self.root / "logs"
        self.miner_log.mkdir()
        python_bin = "python3"
        if os.name == "nt":
            # Git Bash cannot reliably signal a native Windows Python child.
            # Keep validation real, but make the long-running serve action a
            # POSIX child so the launcher's cleanup contract remains testable.
            gate_shim = self.root / "python-gate-shim"
            gate_shim.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ \"${2:-}\" == serve ]]; then exec sleep 600; fi\n"
                f"exec {posix_path(Path(sys.executable))} \"$@\"\n",
                encoding="utf-8",
                newline="\n",
            )
            python_bin = posix_path(gate_shim)
        self.env = {
            "MINER_DIR": posix_path(self.miner),
            "MINER_LOG_DIR": posix_path(self.miner_log),
            "CUSTOM_URL": ENDPOINT,
            "CUSTOM_TEMPLATE": WALLET,
            "CUSTOM_ALGO": "rx/2",
            "CUSTOM_USER_CONFIG": "threads=32",
            "FULL_DATASET_TIMEOUT": "5",
            "PYTHON_BIN": python_bin,
        }

    def init_config(self, *, cwd: Path | None = None):
        res = run_bash(f"source {posix_path(self.miner / 'h-config.sh')}",
                       env=self.env, cwd=cwd, timeout=8)
        self.assertEqual(res.returncode, 0, res.stderr)

    def fake_miner(self, text: str):
        path = self.miner / "xmrig"
        path.write_text(
            "#!/usr/bin/env bash\n"
            "log_file=''\n"
            "for arg in \"$@\"; do\n"
            "  case \"$arg\" in --log-file=*) log_file=\"${arg#*=}\" ;; esac\n"
            "done\n"
            "if [[ -z \"$log_file\" ]]; then\n"
            "  echo 'missing --log-file argument' >&2\n"
            "  exit 97\n"
            "fi\n"
            "exec >>\"$log_file\" 2>&1\n"
            + text,
            encoding="utf-8",
            newline="\n",
        )
        if os.name != "nt":
            path.chmod(0o755)

    def run_launcher(self, *, cwd: Path | None = None):
        return run_bash(f"bash {posix_path(self.miner / 'h-run.sh')}",
                        env=self.env, cwd=cwd, timeout=13)

    def log(self):
        return (self.miner_log / "coinrig-native.log").read_text(encoding="utf-8")

    def test_successful_start_gate_readiness_and_exit(self):
        self.init_config()
        self.fake_miner("""echo 'randomx allocated 2336 MB (2080+256) huge pages 100% 1168/1168 +JIT'
echo 'randomx dataset ready'
sleep 2
""")
        result = self.run_launcher()
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + self.log())
        self.assertIn("submitblock gate opened", self.log())
        self.assertFalse((self.miner / ".full-dataset-ready").exists())

    def test_hiveos_parent_miner_dir_runs_installed_package_from_unrelated_cwd(self):
        self.env["MINER_DIR"] = posix_path(self.miner.parent)
        self.init_config(cwd=self.unrelated_cwd)
        self.fake_miner("""echo 'randomx allocated 2336 MB (2080+256) huge pages 100% 1168/1168 +JIT'
echo 'randomx dataset ready'
sleep 2
""")
        result = self.run_launcher(cwd=self.unrelated_cwd)
        self.assertEqual(result.returncode, 0, result.stderr + "\n" + self.log())
        self.assertIn("submitblock gate opened", self.log())
        self.assertFalse((self.miner / ".full-dataset-ready").exists())
        self.assertFalse((self.miner.parent / ".full-dataset-ready").exists())

    def test_fail_closed_on_light_memory_mode(self):
        self.init_config()
        self.fake_miner("""echo 'randomx failed to allocate RandomX dataset, switching to slow mode'
sleep 2
""")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("slow/light RandomX fallback detected", self.log())
        self.assertNotIn("submitblock gate opened", self.log())
        self.assertFalse((self.miner / ".full-dataset-ready").exists())

    def test_invalid_config_blocks_launch(self):
        self.init_config()
        self.fake_miner("""echo 'LAUNCHED_INCORRECTLY'
sleep 1
""")
        config = self.miner / "config.json"
        obj = json.loads(config.read_text())
        obj["randomx"]["mode"] = "light"
        config.write_text(json.dumps(obj), encoding="utf-8")
        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("locked startup configuration rejected", self.log())
        self.assertNotIn("LAUNCHED_INCORRECTLY", self.log())

    def test_stale_native_log_and_marker_do_not_open_gate(self):
        self.init_config()
        native_log = self.miner / "xmrig.log"
        native_log.write_text(
            "randomx allocated 2336 MB (2080+256)\nrandomx dataset ready\n",
            encoding="utf-8",
        )
        (self.miner / ".full-dataset-ready").write_text(
            "full-dataset-ready\n", encoding="ascii"
        )
        self.env["FULL_DATASET_TIMEOUT"] = "1"
        self.fake_miner("""echo 'fresh run without readiness'
sleep 3
""")

        result = self.run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full RandomX dataset was not confirmed within 1s", self.log())
        self.assertNotIn("submitblock gate opened", self.log())
        self.assertFalse((self.miner / ".full-dataset-ready").exists())
        self.assertNotIn("allocated 2336 MB", native_log.read_text(encoding="utf-8"))
        self.assertIn("fresh run without readiness", native_log.read_text(encoding="utf-8"))

    def test_second_run_cannot_reuse_first_run_readiness(self):
        self.init_config()
        self.fake_miner("""echo 'randomx allocated 2336 MB (2080+256) huge pages 100% 1168/1168 +JIT'
echo 'randomx dataset ready'
sleep 1
""")
        first = self.run_launcher()
        self.assertEqual(first.returncode, 0, first.stderr + "\n" + self.log())
        self.assertFalse((self.miner / ".full-dataset-ready").exists())

        self.env["FULL_DATASET_TIMEOUT"] = "1"
        self.fake_miner("""echo 'second run without readiness'
sleep 3
""")
        second = self.run_launcher()
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.log().count("submitblock gate opened"), 1)
        self.assertFalse((self.miner / ".full-dataset-ready").exists())
        native_text = (self.miner / "xmrig.log").read_text(encoding="utf-8")
        self.assertNotIn("dataset ready", native_text)
        self.assertIn("second run without readiness", native_text)

    @unittest.skipUnless(os.name == "posix", "signal lifecycle requires Linux")
    def test_signal_shutdown_removes_readiness_and_stops_children(self):
        self.init_config()
        self.fake_miner("""trap 'echo miner-terminated; exit 0' TERM
echo 'randomx allocated 2336 MB (2080+256) huge pages 100% 1168/1168 +JIT'
echo 'randomx dataset ready'
sleep 600 &
wait $!
""")
        merged = os.environ.copy()
        merged.update(self.env)
        process = subprocess.Popen(
            [bash_exe(), posix_path(self.miner / "h-run.sh")],
            cwd=self.unrelated_cwd,
            env=merged,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        ready_file = self.miner / ".full-dataset-ready"
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline and process.poll() is None:
            if ready_file.is_file():
                break
            time.sleep(0.05)
        else:
            process.kill()
            stdout, stderr = process.communicate(timeout=5)
            self.fail(f"launcher never became ready\nstdout={stdout}\nstderr={stderr}\n{self.log()}")

        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 143, stdout + stderr + "\n" + self.log())
        self.assertFalse(ready_file.exists())
        self.assertIn("stop requested; terminating miner and submission gate", self.log())
        self.assertIn(
            "miner-terminated",
            (self.miner / "xmrig.log").read_text(encoding="utf-8"),
        )
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", 18882), timeout=0.5)


if __name__ == "__main__":
    unittest.main()
