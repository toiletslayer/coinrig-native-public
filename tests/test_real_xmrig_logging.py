"""Opt-in offline integration checks using Scratcher's exact XMRig binary."""
from __future__ import annotations

import hashlib
import http.client
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

try:
    from test_integration import ENDPOINT, PACKAGE, WALLET, gate, posix_path, run_bash
except ImportError:
    from tests.test_integration import ENDPOINT, PACKAGE, WALLET, gate, posix_path, run_bash


EXPECTED_BINARY_SHA = "5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@unittest.skipUnless(os.name == "posix", "real XMRig integration requires Linux")
class RealXmrigLoggingTests(unittest.TestCase):
    def setUp(self):
        binary_value = os.environ.get("COINRIG_REAL_XMRIG")
        if not binary_value:
            self.skipTest("COINRIG_REAL_XMRIG is required for real-miner validation")

        self.real_xmrig = Path(binary_value).resolve()
        self.assertTrue(self.real_xmrig.is_file(), self.real_xmrig)
        self.assertEqual(sha256(self.real_xmrig), EXPECTED_BINARY_SHA)

        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.miner = self.root / "coinrig-native"
        self.miner.mkdir()
        for name in ("h-config.sh", "submission-gate.py"):
            shutil.copy2(PACKAGE / name, self.miner / name)
        shutil.copy2(self.real_xmrig, self.miner / "xmrig")
        (self.miner / "xmrig").chmod(0o755)

    def start_recording_gate(self, ready_file: Path):
        recorded_bodies = []

        class RecordingUpstream(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["Content-Length"])
                recorded_bodies.append(self.rfile.read(length))
                body = b'{"jsonrpc":"2.0","id":9,"result":{"status":"OK"}}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format_string, *args):
                pass

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), RecordingUpstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        self.addCleanup(upstream.server_close)
        self.addCleanup(upstream.shutdown)

        gate_server = gate.GateServer(
            ("127.0.0.1", 0),
            gate.make_handler("127.0.0.1", upstream.server_address[1], ready_file),
        )
        threading.Thread(target=gate_server.serve_forever, daemon=True).start()
        self.addCleanup(gate_server.server_close)
        self.addCleanup(gate_server.shutdown)
        return gate_server, recorded_bodies

    def submitblock(self, gate_server):
        body = b'{"jsonrpc":"2.0","id":9,"method":"submitblock","params":["block"]}'
        connection = http.client.HTTPConnection(*gate_server.server_address, timeout=5)
        connection.request(
            "POST", "/json_rpc", body=body,
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload, body

    def test_generated_config_native_log_captures_real_randomx_readiness(self):
        env = {
            "CUSTOM_URL": ENDPOINT,
            "CUSTOM_TEMPLATE": WALLET,
            "CUSTOM_ALGO": "rx2",
            "CUSTOM_USER_CONFIG": "threads=32",
        }
        configured = run_bash(
            f"source {posix_path(self.miner / 'h-config.sh')}",
            env=env,
            cwd=self.root,
            timeout=8,
        )
        self.assertEqual(configured.returncode, 0, configured.stderr)

        config_path = self.miner / "config.json"
        native_log = self.miner / "xmrig.log"
        console_log = self.root / "redirected-console.log"
        ready_file = self.miner / ".full-dataset-ready"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["log-file"], str(native_log))

        gate_server, recorded_bodies = self.start_recording_gate(ready_file)
        status, payload, _ = self.submitblock(gate_server)
        self.assertEqual(status, 200)
        self.assertEqual(payload["error"]["code"], -32099)
        self.assertEqual(recorded_bodies, [])

        command = [
            str(self.miner / "xmrig"),
            "--config", str(config_path),
            "--algo=rx/2",
            "--bench=1M",
            "--threads=1",
            "--randomx-init=4",
            "--randomx-mode=fast",
            "--randomx-wrmsr=-1",
            "--randomx-no-rdmsr",
            "--no-color",
            "--no-huge-pages",
        ]
        with console_log.open("wb") as redirected:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=redirected,
                stderr=subprocess.STDOUT,
            )
            try:
                deadline = time.monotonic() + 60
                native_text = ""
                while time.monotonic() < deadline and process.poll() is None:
                    if native_log.is_file():
                        native_text = native_log.read_text(encoding="utf-8", errors="replace")
                        if "allocated 2336 MB" in native_text and "dataset ready" in native_text:
                            break
                    time.sleep(0.1)
                else:
                    self.fail(
                        "real XMRig did not log full-dataset readiness within 60s; "
                        f"native log:\n{native_text}"
                    )
            finally:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=10)

        self.assertEqual(console_log.read_bytes(), b"")
        native_text = native_log.read_text(encoding="utf-8", errors="strict")
        self.assertIn("randomx  allocated 2336 MB", native_text)
        self.assertIn("randomx  dataset ready", native_text)

        ready_file.write_bytes(b"full-dataset-ready\n")
        status, payload, request = self.submitblock(gate_server)
        self.assertEqual(status, 200)
        self.assertEqual(payload["result"]["status"], "OK")
        self.assertEqual(recorded_bodies, [request])


if __name__ == "__main__":
    unittest.main()
