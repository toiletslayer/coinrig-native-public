import importlib.util
from pathlib import Path
import unittest

file = Path(__file__).resolve().parents[1] / "coinrig-native" / "submission-gate.py"
spec = importlib.util.spec_from_file_location("coinrig_gate", file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestEndpoints(unittest.TestCase):
    def test_allowed(self):
        for endpoint in ("192.168.1.10:38881", "10.0.0.1:1234", "172.31.5.4:65535"):
            with self.subTest(endpoint=endpoint):
                host, port = module.parse_private_endpoint(endpoint)
                self.assertEqual(endpoint, f"{host}:{port}")

    def test_rejected(self):
        for endpoint in ("", "127.0.0.1:38881", "8.8.8.8:38881",
                         "169.254.169.254:80", "localhost:38881",
                         "192.168.1.10:0", "192.168.1.10:65536",
                         "192.168.1.10:abc", "192.168.1.10:-1",
                         "192.168.1.10:30:40", "172.32.1.1:38881"):
            with self.subTest(endpoint=endpoint):
                with self.assertRaises(ValueError):
                    module.parse_private_endpoint(endpoint)


if __name__ == "__main__":
    unittest.main()
