#!/usr/bin/env python3
"""Loopback COIN JSON-RPC submission gate and HiveOS stats helper."""

from __future__ import annotations

import argparse
import ipaddress
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sys
from urllib.request import urlopen


MAX_BODY = 8 * 1024 * 1024
READY_TOKEN = b"full-dataset-ready\n"
PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)


def parse_private_endpoint(endpoint: str) -> tuple[str, int]:
    if not isinstance(endpoint, str) or endpoint.count(":") != 1:
        raise ValueError("expected IPv4:port")
    host, port_string = endpoint.split(":", 1)
    addr = ipaddress.IPv4Address(host)
    if not any(addr in network for network in PRIVATE_NETWORKS):
        raise ValueError("only RFC1918 private IPv4 hosts permitted")
    if not port_string.isascii() or not port_string.isdecimal():
        raise ValueError("port must be decimal")
    port = int(port_string)
    if not 1 <= port <= 65535:
        raise ValueError("port out of range")
    return str(addr), port


def validate_endpoint(args: argparse.Namespace) -> int:
    try:
        host, port = parse_private_endpoint(args.endpoint)
    except ValueError as exc:
        sys.stderr.write(f"coinrig-native: invalid gateway: {exc}\n")
        return 1
    print(f"{host} {port}")
    return 0

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class GateServer(ThreadingHTTPServer):
    allow_reuse_address = True


def _rpc_method(body: bytes) -> tuple[str, object]:
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "", None
    if not isinstance(payload, dict):
        return "", None
    method = payload.get("method")
    return (method if isinstance(method, str) else ""), payload.get("id")


def _error_body(request_id: object, code: int, message: str) -> bytes:
    return json.dumps(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        separators=(",", ":"),
    ).encode("utf-8")


def readiness_marker_valid(ready_file: Path) -> bool:
    try:
        return ready_file.is_file() and ready_file.read_bytes() == READY_TOKEN
    except OSError:
        return False


def make_handler(upstream_host: str, upstream_port: int, ready_file: Path):
    class GateHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:  # noqa: N802
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(411, _error_body(None, -32600, "invalid Content-Length"))
                return
            if length < 1 or length > MAX_BODY:
                self._send(413, _error_body(None, -32600, "request body size rejected"))
                return
            body = self.rfile.read(length)
            method, request_id = _rpc_method(body)
            if not method:
                self._send(400, _error_body(request_id, -32600, "invalid JSON-RPC request"))
                return
            if self.path != "/json_rpc" or method not in {"getblocktemplate", "submitblock"}:
                self._send(403, _error_body(request_id, -32601, "unsupported method"))
                return
            if method == "submitblock" and not readiness_marker_valid(ready_file):
                self._send(
                    200,
                    _error_body(
                        request_id,
                        -32099,
                        "coinrig-native: full RandomX dataset not ready; submitblock blocked",
                    ),
                )
                return

            headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
            try:
                connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=20)
                connection.request("POST", self.path, body=body, headers=headers)
                response = connection.getresponse()
                response_body = response.read(MAX_BODY + 1)
                if len(response_body) > MAX_BODY:
                    raise ValueError("upstream response too large")
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in HOP_BY_HOP and key.lower() not in {"content-length", "content-type"}:
                        self.send_header(key, value)
                self.send_header("Content-Type", response.getheader("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(response_body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(response_body)
            except (OSError, http.client.HTTPException, ValueError) as exc:
                self._send(502, _error_body(request_id, -32098, f"approved gateway unavailable: {type(exc).__name__}"))
            finally:
                try:
                    connection.close()
                except (UnboundLocalError, OSError):
                    pass

        def do_GET(self) -> None:  # noqa: N802
            if self.path not in {"/getheight", "/get_height"}:
                self._send(404, _error_body(None, -32601, "unsupported endpoint"))
                return
            connection = None
            try:
                connection = http.client.HTTPConnection(upstream_host, upstream_port, timeout=8)
                connection.request("GET", self.path)
                response = connection.getresponse()
                body = response.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise ValueError("gateway reply too large")
                self._send(response.status, body)
            except (OSError, http.client.HTTPException, ValueError):
                self._send(502, _error_body(None, -32098, "gateway unavailable"))
            finally:
                if connection is not None:
                    connection.close()

        def log_message(self, format_string: str, *args: object) -> None:
            sys.stderr.write("coinrig-native gate: " + (format_string % args) + "\n")

    return GateHandler


def serve(args: argparse.Namespace) -> int:
    if args.listen_host != "127.0.0.1":
        raise SystemExit("submission gate must bind to 127.0.0.1")
    try:
        parse_private_endpoint(f"{args.upstream_host}:{args.upstream_port}")
    except ValueError as exc:
        raise SystemExit(f"submission gate upstream rejected: {exc}") from exc
    server = GateServer(
        (args.listen_host, args.listen_port),
        make_handler(args.upstream_host, args.upstream_port, Path(args.ready_file)),
    )
    server.daemon_threads = True
    sys.stderr.write(
        f"coinrig-native gate: listening on 127.0.0.1:{args.listen_port}; "
        f"upstream {args.upstream_host}:{args.upstream_port}; submissions closed\n"
    )
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _number(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value)):
        return float(value)
    return default


def stats(args: argparse.Namespace) -> int:
    try:
        with urlopen(args.url, timeout=args.timeout) as response:
            raw = response.read(MAX_BODY + 1)
        if len(raw) > MAX_BODY:
            raise ValueError("stats response too large")
        payload = json.loads(raw)
        totals = payload.get("hashrate", {}).get("total", [])
        hps = _number(totals[0] if totals else 0.0)
        uptime = int(_number(payload.get("uptime")))
        results = payload.get("results", {})
        accepted = int(_number(results.get("accepted")))
        rejected = int(_number(results.get("rejected")))
        version = payload.get("version", "unknown")
        if not isinstance(version, str):
            version = "unknown"
        result = {
            "hs": [hps],
            "hs_units": "hs",
            "uptime": uptime,
            "ver": version,
            "ar": [accepted, rejected],
            "algo": "rx/2",
        }
        print(f"{hps / 1000:.3f}\t{json.dumps(result, separators=(',', ':'))}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
        print("0\tnull")
    return 0


def validate_config(args: argparse.Namespace) -> int:
    try:
        config = json.loads(Path(args.config).read_text(encoding="utf-8"))
        wallet = config["pools"][0]["user"]
        thread_profile = config["cpu"]["rx/2"]
        if not isinstance(thread_profile, list) or not 1 <= len(thread_profile) <= 256:
            raise ValueError("thread profile length must be 1-256")
        if any(type(index) is not int for index in thread_profile):
            raise ValueError("thread profile entries must be integers")
        thread_count = len(thread_profile)
        checks = (
            config["http"] == {
                "enabled": True, "host": "127.0.0.1", "port": 18082,
                "access-token": None, "restricted": True,
            },
            config["randomx"]["mode"] == "fast",
            config["randomx"]["wrmsr"] is False,
            config["randomx"]["rdmsr"] is False,
            config["log-file"] == args.expected_log_file,
            thread_profile == list(range(thread_count)),
            config["donate-level"] == 0,
            len(config["pools"]) == 1,
            config["pools"][0]["algo"] == "rx/2",
            config["pools"][0]["url"] == "127.0.0.1:18882",
            config["pools"][0]["daemon"] is True,
            isinstance(wallet, str) and len(wallet) == 95 and wallet.startswith("C"),
            isinstance(wallet, str) and all(c in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz" for c in wallet),
        )
        if not all(checks):
            raise ValueError("locked configuration mismatch")
    except (OSError, ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"coinrig-native: config validation failed: {exc}\n")
        return 1
    print(thread_count)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    endpoint_parser = subparsers.add_parser("validate-endpoint")
    endpoint_parser.add_argument("--endpoint", required=True)
    endpoint_parser.set_defaults(function=validate_endpoint)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--listen-host", required=True)
    serve_parser.add_argument("--listen-port", required=True, type=int)
    serve_parser.add_argument("--upstream-host", required=True)
    serve_parser.add_argument("--upstream-port", required=True, type=int)
    serve_parser.add_argument("--ready-file", required=True)
    serve_parser.set_defaults(function=serve)

    stats_parser = subparsers.add_parser("stats")
    stats_parser.add_argument("--url", required=True)
    stats_parser.add_argument("--timeout", type=float, default=2.0)
    stats_parser.set_defaults(function=stats)

    validate_parser = subparsers.add_parser("validate-config")
    validate_parser.add_argument("--config", required=True)
    validate_parser.add_argument("--expected-log-file", required=True)
    validate_parser.set_defaults(function=validate_config)

    args = parser.parse_args()
    return int(args.function(args))


if __name__ == "__main__":
    raise SystemExit(main())
