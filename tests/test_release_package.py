"""Deterministic release archive and extracted-package lifecycle checks.

Set COINRIG_UPSTREAM_RELEASE to build from Scratcher's checksum-pinned Linux
release, or COINRIG_PACKAGE_ARCHIVE to validate a prebuilt candidate. The
lifecycle uses a fake miner and a non-routable fixture endpoint; it never
submits work to a node.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

try:
    from test_integration import BASE, ENDPOINT, WALLET, posix_path, run_bash
except ImportError:
    from tests.test_integration import BASE, ENDPOINT, WALLET, posix_path, run_bash


PACKAGER_PATH = BASE / "scripts" / "package_release.py"
EXPECTED_VERSION = "1.1.0_beta5"
EXPECTED_BINARY_SHA = "5b18de5443bf11c6565a433ab470c503c4192f6d17a33d0f8ad62c1852bcd462"
EXPECTED_FILES = {
    "LICENSE",
    "PROVENANCE.md",
    "README.md",
    "SHA256SUMS",
    "h-config.sh",
    "h-manifest.conf",
    "h-run.sh",
    "h-stats.sh",
    "submission-gate.py",
    "xmrig",
}

spec = importlib.util.spec_from_file_location("coinrig_packager", PACKAGER_PATH)
packager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packager)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReleasePackageTests(unittest.TestCase):
    def test_extracted_beta5_archive_full_offline_24_thread_lifecycle(self):
        prebuilt_value = os.environ.get("COINRIG_PACKAGE_ARCHIVE")
        upstream_value = os.environ.get("COINRIG_UPSTREAM_RELEASE")
        if not prebuilt_value and not upstream_value:
            self.skipTest(
                "COINRIG_UPSTREAM_RELEASE or COINRIG_PACKAGE_ARCHIVE is required "
                "for release archive validation"
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            if prebuilt_value:
                archive = Path(prebuilt_value).resolve()
                checksum = Path(f"{archive}.sha256")
                self.assertTrue(archive.is_file(), archive)
            else:
                upstream = Path(upstream_value).resolve()
                self.assertTrue(upstream.is_file(), upstream)
                output = root / "dist"
                build = subprocess.run(
                    [
                        sys.executable,
                        str(PACKAGER_PATH),
                        "--upstream-release",
                        str(upstream),
                        "--out-dir",
                        str(output),
                    ],
                    cwd=BASE,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                self.assertEqual(build.returncode, 0, build.stderr)
                archive = output / f"coinrig-native-{EXPECTED_VERSION}.tar.gz"
                checksum = output / f"{archive.name}.sha256"
                self.assertTrue(archive.is_file(), build.stdout)
            self.assertEqual(archive.name, f"coinrig-native-{EXPECTED_VERSION}.tar.gz")
            self.assertTrue(checksum.is_file(), checksum)
            self.assertEqual(
                checksum.read_text(encoding="ascii"),
                f"{sha256(archive)}  {archive.name}\n",
            )

            custom_root = root / "hive" / "miners" / "custom"
            custom_root.mkdir(parents=True)
            with tarfile.open(archive, "r:gz") as package:
                members = package.getmembers()
                self.assertEqual(
                    {member.name for member in members},
                    {"coinrig-native"} | {f"coinrig-native/{name}" for name in EXPECTED_FILES},
                )
                for name in ("h-config.sh", "h-run.sh", "h-stats.sh", "xmrig"):
                    self.assertEqual(package.getmember(f"coinrig-native/{name}").mode, 0o755)
                package.extractall(custom_root, filter="data")

            installed = custom_root / "coinrig-native"
            self.assertIn(
                f'CUSTOM_VERSION="{EXPECTED_VERSION}"',
                (installed / "h-manifest.conf").read_text(encoding="utf-8"),
            )
            self.assertEqual(sha256(installed / "xmrig"), EXPECTED_BINARY_SHA)

            recorded = {}
            for line in (installed / "SHA256SUMS").read_text(encoding="ascii").splitlines():
                digest, name = line.split("  ", 1)
                recorded[name] = digest
            self.assertEqual(set(recorded), EXPECTED_FILES - {"SHA256SUMS"})
            for name, digest in recorded.items():
                self.assertEqual(sha256(installed / name), digest, name)

            fake_miner = installed / "xmrig"
            fake_miner.write_text(
                "#!/usr/bin/env bash\n"
                "if [[ -n \"${ARGS_FILE:-}\" ]]; then printf '%s\\n' \"$@\" > \"$ARGS_FILE\"; fi\n"
                "log_file=''\n"
                "for arg in \"$@\"; do\n"
                "  case \"$arg\" in --log-file=*) log_file=\"${arg#*=}\" ;; esac\n"
                "done\n"
                "[[ -n \"$log_file\" ]] || exit 97\n"
                "exec >>\"$log_file\" 2>&1\n"
                "echo 'randomx allocated 2336 MB (2080+256) huge pages 100% 1168/1168 +JIT'\n"
                "echo 'randomx dataset ready'\n"
                "sleep 2\n",
                encoding="utf-8",
                newline="\n",
            )
            fake_miner.chmod(0o755)

            unrelated_cwd = root / "tmp" / "coin-native-test" / "xmrig-6.26.0-coin"
            unrelated_cwd.mkdir(parents=True)
            log_dir = root / "logs"
            log_dir.mkdir()
            python_bin = "python3"
            if os.name == "nt":
                gate_shim = root / "python-gate-shim"
                gate_shim.write_text(
                    "#!/usr/bin/env bash\n"
                    "if [[ \"${2:-}\" == serve ]]; then exec sleep 600; fi\n"
                    f"exec {posix_path(Path(sys.executable))} \"$@\"\n",
                    encoding="utf-8",
                    newline="\n",
                )
                python_bin = posix_path(gate_shim)
            env = {
                "MINER_DIR": posix_path(custom_root),
                "MINER_LOG_DIR": posix_path(log_dir),
                "CUSTOM_URL": ENDPOINT,
                "CUSTOM_TEMPLATE": WALLET,
                "CUSTOM_ALGO": "rx2",
                "CUSTOM_USER_CONFIG": "threads=24",
                "FULL_DATASET_TIMEOUT": "5",
                "PYTHON_BIN": python_bin,
                "ARGS_FILE": posix_path(root / "xmrig-args.txt"),
            }

            configured = run_bash(
                f"source {posix_path(installed / 'h-config.sh')}",
                env=env,
                cwd=unrelated_cwd,
                timeout=8,
            )
            self.assertEqual(configured.returncode, 0, configured.stderr)
            self.assertTrue((installed / "config.json").is_file())
            self.assertEqual((installed / ".gateway").read_text().strip(), ENDPOINT)
            self.assertFalse((custom_root / "config.json").exists())
            config = json.loads(
                (installed / "config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["cpu"]["rx/2"], list(range(24)))

            launched = run_bash(
                f"bash {posix_path(installed / 'h-run.sh')}",
                env=env,
                cwd=unrelated_cwd,
                timeout=13,
            )
            log = (log_dir / "coinrig-native.log").read_text(encoding="utf-8")
            self.assertEqual(launched.returncode, 0, launched.stderr + "\n" + log)
            self.assertIn("submitblock gate opened", log)
            self.assertFalse((installed / ".full-dataset-ready").exists())
            args = (root / "xmrig-args.txt").read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                [arg for arg in args if arg.startswith("--threads=")],
                ["--threads=24"],
            )

            trace = root / "stats-helper-argv.txt"
            fake_python = root / "fake-python"
            fake_python.write_text(
                "#!/usr/bin/env bash\n"
                "printf '%s\\n' \"$1\" > \"$TRACE_FILE\"\n"
                "printf '0\\tnull\\n'\n",
                encoding="utf-8",
                newline="\n",
            )
            fake_python.chmod(0o755)
            stats_env = env | {
                "PYTHON_BIN": posix_path(fake_python),
                "TRACE_FILE": posix_path(trace),
            }
            stats = run_bash(
                f"source {posix_path(installed / 'h-stats.sh')}; "
                "printf 'KHS=%s STATS=%s\\n' \"$khs\" \"$stats\"",
                env=stats_env,
                cwd=unrelated_cwd,
            )
            self.assertEqual(stats.returncode, 0, stats.stderr)
            self.assertIn("KHS=0 STATS=null", stats.stdout)
            self.assertEqual(
                trace.read_text(encoding="utf-8").strip(),
                posix_path(installed / "submission-gate.py"),
            )


if __name__ == "__main__":
    unittest.main()
