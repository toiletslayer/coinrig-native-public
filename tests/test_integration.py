"""Offline integration checks for the public HiveOS source package.

No wallet, mining node, external network, or real XMRig process is used.
"""
from __future__ import annotations

import importlib.util
import http.client
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
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

    def start_recording_gate(self, ready_file: Path):
        recorded_bodies = []

        class RecordingUpstream(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                recorded_bodies.append(self.rfile.read(length))
                body = b'{"jsonrpc":"2.0","id":7,"result":{"status":"OK"}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format_string, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), RecordingUpstream)
        upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        upstream_thread.start()
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream.shutdown)

        gate_server = gate.GateServer(
            ("127.0.0.1", 0),
            gate.make_handler("127.0.0.1", upstream.server_address[1], ready_file),
        )
        gate_thread = threading.Thread(target=gate_server.serve_forever, daemon=True)
        gate_thread.start()
        self.addCleanup(gate_server.server_close)
        self.addCleanup(gate_server.shutdown)
        return gate_server, recorded_bodies

    def gate_rpc(self, gate_server, method: str, *, path="/json_rpc"):
        request = json.dumps(
            {"jsonrpc": "2.0", "id": 7, "method": method, "params": ["block"]},
            separators=(",", ":"),
        ).encode("utf-8")
        connection = http.client.HTTPConnection(*gate_server.server_address, timeout=5)
        connection.request(
            "POST", path, body=request,
            headers={"Content-Type": "application/json", "Content-Length": str(len(request))},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload, request

    def test_config_supports_blank_default_and_explicit_thread_counts(self):
        cases = (
            ("", 32),
            ("threads=1", 1),
            ("threads=24", 24),
            ("threads=32", 32),
            ("threads=256", 256),
        )
        for extra, expected_threads in cases:
            with self.subTest(extra=extra):
                result = self.configure(CUSTOM_USER_CONFIG=extra)
                self.assertEqual(result.returncode, 0, result.stderr)
                obj = json.loads((self.miner / "config.json").read_text())
                self.assertEqual((self.miner / ".gateway").read_text().strip(), ENDPOINT)
                self.assertEqual(obj["pools"][0]["user"], WALLET)
                self.assertEqual(obj["pools"][0]["url"], "127.0.0.1:18882")
                self.assertEqual(obj["cpu"]["rx/2"], list(range(expected_threads)))
                self.assertEqual(obj["randomx"]["mode"], "fast")
                self.assertFalse(obj["randomx"]["wrmsr"])
                self.assertFalse(obj["randomx"]["rdmsr"])
                self.assertEqual(obj["log-file"], posix_path(self.miner / "xmrig.log"))
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
                         {"CUSTOM_ALGO": "rx/0"}):
            with self.subTest(override=override):
                (self.miner / "config.json").unlink(missing_ok=True)
                result = self.configure(**override)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.miner / "config.json").exists())

    def test_invalid_thread_config_fails_closed_without_command_injection(self):
        injection_marker = self.directory / "extra-config-was-executed"
        invalid_values = (
            "threads=0",
            "threads=257",
            "threads=01",
            "threads=+24",
            "threads=-24",
            "threads=24 ",
            " threads=24",
            "threads=24\nthreads=32",
            "threads=24,donate-level=5",
            "threads=24 --randomx-mode=light",
            f"threads=24;touch {posix_path(injection_marker)}",
            "foo=24",
            "threads=２４",
        )
        for extra in invalid_values:
            with self.subTest(extra=extra):
                for stale in (self.miner / "config.json", self.miner / ".gateway"):
                    stale.unlink(missing_ok=True)
                result = self.configure(CUSTOM_USER_CONFIG=extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.miner / "config.json").exists())
                self.assertFalse((self.miner / ".gateway").exists())
                self.assertFalse(injection_marker.exists())

    def test_validate_generated_config(self):
        result = self.configure()
        self.assertEqual(result.returncode, 0, result.stderr)
        cmd = [sys.executable, str(self.miner / "submission-gate.py"),
               "validate-config", "--config", str(self.miner / "config.json"),
               "--expected-log-file", posix_path(self.miner / "xmrig.log")]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads((self.miner / "config.json").read_text())
        obj["log-file"] = None
        (self.miner / "config.json").write_text(json.dumps(obj))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)

    def test_gate_rejects_empty_readiness_marker(self):
        ready_file = self.directory / ".full-dataset-ready"
        ready_file.write_bytes(b"")
        gate_server, recorded_bodies = self.start_recording_gate(ready_file)
        status, payload, _ = self.gate_rpc(gate_server, "submitblock")

        self.assertEqual(status, 200)
        self.assertIn("error", payload, payload)
        self.assertEqual(payload["error"]["code"], -32099)
        self.assertEqual(recorded_bodies, [])

    def test_gate_forwards_templates_and_only_exact_ready_submissions(self):
        ready_file = self.directory / ".full-dataset-ready"
        gate_server, recorded_bodies = self.start_recording_gate(ready_file)

        status, payload, template_request = self.gate_rpc(gate_server, "getblocktemplate")
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["status"], "OK")
        self.assertEqual(recorded_bodies, [template_request])

        status, payload, _ = self.gate_rpc(gate_server, "submitblock")
        self.assertEqual(status, 200)
        self.assertEqual(payload["error"]["code"], -32099)
        self.assertEqual(recorded_bodies, [template_request])

        ready_file.write_bytes(b"full-dataset-ready")
        status, payload, _ = self.gate_rpc(gate_server, "submitblock")
        self.assertEqual(status, 200)
        self.assertEqual(payload["error"]["code"], -32099)
        self.assertEqual(recorded_bodies, [template_request])

        ready_file.write_bytes(b"full-dataset-ready\n")
        status, payload, submit_request = self.gate_rpc(gate_server, "submitblock")
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["status"], "OK")
        self.assertEqual(recorded_bodies, [template_request, submit_request])

    def test_hive_shell_callbacks_syntax(self):
        for name in ("h-config.sh", "h-run.sh", "h-stats.sh"):
            result = run_bash(f"bash -n {posix_path(self.miner / name)}")
            self.assertEqual(result.returncode, 0, name + ": " + result.stderr)

    def test_gate_only_forwards_known_rpc_methods(self):
        ready_file = self.directory / ".full-dataset-ready"
        ready_file.write_bytes(b"full-dataset-ready\n")
        gate_server, recorded_bodies = self.start_recording_gate(ready_file)

        status, payload, _ = self.gate_rpc(gate_server, "get_balance")
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], -32601)

        status, payload, _ = self.gate_rpc(
            gate_server, "getblocktemplate", path="/wrong-path"
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["code"], -32601)
        self.assertEqual(recorded_bodies, [])

if __name__ == "__main__":
    unittest.main()
