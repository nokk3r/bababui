"""Запуск Xray или Hysteria2 и замер скорости через локальный SOCKS."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from app.config import CURL_BIN, DATA_DIR, HYSTERIA_BIN, XRAY_BIN
from app.parser import ParsedNode

SUCCESS_BYTES = 4096


@dataclass
class ProbeResult:
    latency_ms: float | None = None
    download_bps: float | None = None
    upload_bps: float | None = None
    download_bytes: int | None = None
    upload_bytes: int | None = None
    ok: bool = False
    error: str = ""


@dataclass
class CancelToken:
    _event: threading.Event = field(default_factory=threading.Event)
    _procs: set = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def track(self, proc: subprocess.Popen) -> bool:
        with self._lock:
            if self._event.is_set():
                proc.kill()
                return False
            self._procs.add(proc)
            return True

    def untrack(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.discard(proc)

    def cancel(self) -> None:
        self._event.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            try:
                proc.kill()
            except OSError:
                pass


class LogBuffer:
    def __init__(self) -> None:
        self.lines: deque[str] = deque(maxlen=80)
        self._thread: threading.Thread | None = None

    def attach(self, proc: subprocess.Popen) -> None:
        def drain() -> None:
            if proc.stdout is None:
                return
            for raw in proc.stdout:
                self.lines.append(raw.decode("utf-8", "replace").rstrip())

        self._thread = threading.Thread(target=drain, daemon=True)
        self._thread.start()

    def text(self) -> str:
        if self._thread is not None:
            self._thread.join(timeout=1)
        return "\n".join(self.lines)


def binary_status() -> dict:
    return {
        "xray": describe_binary(XRAY_BIN, ["version"]),
        "hysteria": describe_binary(HYSTERIA_BIN, ["version"]),
        "curl_socks": curl_has_socks(),
    }


def describe_binary(path: str, args: list[str]) -> dict:
    try:
        out = subprocess.check_output([path, *args], stderr=subprocess.STDOUT, timeout=4, text=True)
    except Exception:
        return {"ok": False, "text": f"не найден: {path}"}
    lines = [ANSI.sub("", item).strip() for item in out.splitlines()]
    lines = [item for item in lines if item]
    for line in lines:
        if line.startswith("Xray "):
            return {"ok": True, "text": line.split(" (", 1)[0]}
        if line.lower().startswith("version:"):
            return {"ok": True, "text": "Hysteria " + line.split(":", 1)[1].strip()}
    return {"ok": True, "text": lines[0] if lines else path}


def curl_has_socks() -> bool:
    try:
        proc = subprocess.run(
            [CURL_BIN, "-sS", "--max-time", "2", "--proxy", "socks5h://127.0.0.1:9", "http://127.0.0.1:9"],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except Exception:
        return False
    err = (proc.stderr or "").lower()
    return "not supported" not in err and "unsupported" not in err


def test_node(node: ParsedNode, settings: dict, cancel: CancelToken) -> ProbeResult:
    if cancel.cancelled:
        return ProbeResult(error="остановлено")
    if not node.supported or not node.engine:
        return ProbeResult(error=node.reason or "протокол не поддерживается")
    port = free_port()
    work = Path(tempfile.mkdtemp(prefix="xraychk-"))
    proc: subprocess.Popen | None = None
    logs = LogBuffer()
    try:
        if node.engine == "xray":
            outbound = copy.deepcopy(node.xray_outbound or {})
            try:
                relax_unverified_tls(outbound)
            except RuntimeError as exc:
                return ProbeResult(error=str(exc))
            config_path = work / "config.json"
            config_path.write_text(
                json.dumps(xray_config(outbound, port), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.chmod(config_path, 0o600)
            check = subprocess.run(
                [XRAY_BIN, "run", "-test", "-c", str(config_path)],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if check.returncode != 0:
                detail = useful_error(scrub((check.stderr or "") + "\n" + (check.stdout or ""), node.secrets))
                return ProbeResult(error=detail or "Xray отклонил конфиг")
            proc, logs = launch([XRAY_BIN, "run", "-c", str(config_path)], cancel)
        elif node.engine == "hysteria":
            config_path = work / "config.yaml"
            config_path.write_text(render_hysteria_config(node.hysteria or {}, port), encoding="utf-8")
            os.chmod(config_path, 0o600)
            proc, logs = launch([HYSTERIA_BIN, "client", "-c", str(config_path)], cancel)
        else:
            return ProbeResult(error="нет обработчика для протокола")
        if proc is None or cancel.cancelled:
            return ProbeResult(error="остановлено")
        try:
            wait_port(port, proc, timeout=6)
        except Exception as exc:
            detail = useful_error(scrub(logs.text(), node.secrets))
            return ProbeResult(error=detail or f"прокси не поднялся: {exc}")
        return measure(port, settings, cancel, node.secrets)
    except FileNotFoundError as exc:
        return ProbeResult(error=f"не найден исполняемый файл: {exc.filename}")
    except Exception as exc:
        detail = scrub(logs.text() or str(exc), node.secrets)
        return ProbeResult(error=detail or "сбой проверки")
    finally:
        if proc is not None:
            stop_process(proc, cancel)
        shutil.rmtree(work, ignore_errors=True)


def measure(port: int, settings: dict, cancel: CancelToken, secrets: list[str]) -> ProbeResult:
    result = ProbeResult()
    errors: list[str] = []
    latency, latency_error = probe_latency(port, settings, cancel, secrets)
    result.latency_ms = latency
    if latency is None:
        errors.append(latency_error or "нет отклика")
        result.error = "; ".join(errors)
        return result
    if settings.get("measure_download", True):
        if cancel.cancelled:
            result.error = "остановлено"
            return result
        speed, size, error = probe_transfer(
            port,
            download_target(settings),
            int(settings["download_seconds"]),
            upload_path=None,
            cancel=cancel,
            secrets=secrets,
        )
        result.download_bps = speed
        result.download_bytes = size
        if speed is None:
            errors.append("входящая: " + (error or "нет данных"))
    if settings.get("measure_upload", True):
        if cancel.cancelled:
            result.error = "остановлено"
            return result
        upload = ensure_upload_file(int(settings["upload_bytes"]))
        speed, size, error = probe_transfer(
            port,
            settings["upload_url"],
            int(settings["upload_seconds"]),
            upload_path=upload,
            cancel=cancel,
            secrets=secrets,
        )
        result.upload_bps = speed
        result.upload_bytes = size
        if speed is None:
            errors.append("исходящая: " + (error or "нет данных"))
    result.ok = not errors and not cancel.cancelled
    result.error = "остановлено" if cancel.cancelled else "; ".join(errors)
    return result


def probe_latency(port: int, settings: dict, cancel: CancelToken, secrets: list[str]) -> tuple[float | None, str]:
    last_error = "нет отклика"
    for attempt in range(2):
        if cancel.cancelled:
            return None, "остановлено"
        if attempt:
            time.sleep(0.4)
        code, metrics, error = curl(
            port,
            settings["latency_url"],
            seconds=12,
            upload_path=None,
            cancel=cancel,
            secrets=secrets,
        )
        if metrics and http_ok(metrics["code"]) and (metrics["start"] > 0 or metrics["total"] > 0):
            elapsed = metrics["start"] or metrics["total"]
            return round(elapsed * 1000, 1), ""
        last_error = humanize_curl(error) or f"код {code}"
    return None, last_error


def probe_transfer(
    port: int,
    url: str,
    seconds: int,
    upload_path: Path | None,
    cancel: CancelToken,
    secrets: list[str],
) -> tuple[float | None, int | None, str]:
    code, metrics, error = curl(port, url, seconds=seconds, upload_path=upload_path, cancel=cancel, secrets=secrets)
    if metrics is None:
        return None, None, error or "curl не вернул результат"
    if upload_path is None:
        size = int(metrics["down_size"])
        speed = metrics["down_speed"]
    else:
        size = int(metrics["up_size"])
        speed = metrics["up_speed"]
    timed_out = code == 28
    if size >= SUCCESS_BYTES and speed > 0 and (http_ok(metrics["code"]) or timed_out):
        return speed, size, ""
    return None, size or None, humanize_curl(error) or f"мало данных ({size} байт, HTTP {metrics['code']})"


def curl(
    port: int,
    url: str,
    seconds: int,
    upload_path: Path | None,
    cancel: CancelToken,
    secrets: list[str],
) -> tuple[int, dict | None, str]:
    if cancel.cancelled:
        return 1, None, "остановлено"
    cmd = [
        CURL_BIN,
        "-sS",
        "--proxy",
        f"socks5h://127.0.0.1:{port}",
        "--connect-timeout",
        "8",
        "--max-time",
        str(seconds),
        "-o",
        os.devnull,
        "-w",
        "%{http_code} %{time_starttransfer} %{time_total} %{size_download} %{speed_download} %{size_upload} %{speed_upload}",
    ]
    if upload_path is not None:
        cmd.extend(
            [
                "-X",
                "POST",
                "-H",
                "Content-Type: application/octet-stream",
                "-H",
                "Expect:",
                "--data-binary",
                f"@{upload_path}",
            ]
        )
    else:
        cmd.append("-L")
        cmd.extend(["--max-redirs", "3"])
    cmd.append(url)
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        env.pop(key, None)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        env=env,
    )
    if not cancel.track(proc):
        return 1, None, "остановлено"
    try:
        out, err = proc.communicate(timeout=seconds + 8)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
    finally:
        cancel.untrack(proc)
    metrics = parse_metrics((out or b"").decode("utf-8", "replace"))
    error = scrub((err or b"").decode("utf-8", "replace"), secrets)
    error = short_curl_error(error)
    return proc.returncode or 0, metrics, error


def parse_metrics(text: str) -> dict | None:
    parts = text.strip().split()
    if len(parts) < 7:
        return None
    code, start, total, down_size, down_speed, up_size, up_speed = parts[-7:]
    try:
        return {
            "code": code,
            "start": float(start),
            "total": float(total),
            "down_size": float(down_size),
            "down_speed": float(down_speed),
            "up_size": float(up_size),
            "up_speed": float(up_speed),
        }
    except ValueError:
        return None


def relax_unverified_tls(outbound: dict) -> None:
    """Xray 26 убрал allowInsecure. Для пустого SNI снимаем отпечаток листа и закрепляем его."""
    stream = outbound.get("streamSettings") or {}
    tls = stream.get("tlsSettings")
    if not isinstance(tls, dict) or not tls.get("allowInsecure"):
        return
    if tls.get("pinnedPeerCertSha256"):
        tls.pop("allowInsecure", None)
        return
    address, port = dial_target(outbound)
    server_name = str(tls.get("serverName") or address)
    alpn = list(tls.get("alpn") or [])
    try:
        digest = fetch_cert_sha256(address, port, server_name, alpn)
    except Exception as exc:
        raise RuntimeError(f"не удалось прочитать сертификат {address}:{port}: {exc}") from exc
    pin_tls_settings(outbound, digest)


def pin_tls_settings(outbound: dict, digest: str) -> None:
    tls = outbound["streamSettings"]["tlsSettings"]
    tls.pop("allowInsecure", None)
    tls["pinnedPeerCertSha256"] = digest


def dial_target(outbound: dict) -> tuple[str, int]:
    settings = outbound.get("settings") or {}
    if settings.get("vnext"):
        item = settings["vnext"][0]
        return str(item["address"]), int(item["port"])
    servers = settings.get("servers") or []
    if servers:
        item = servers[0]
        return str(item["address"]), int(item["port"])
    raise RuntimeError("в конфиге нет адреса сервера")


def fetch_cert_sha256(address: str, port: int, server_name: str, alpn: list[str]) -> str:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    if alpn:
        context.set_alpn_protocols(alpn)
    with socket.create_connection((address, port), timeout=8) as sock:
        sock.settimeout(8)
        with context.wrap_socket(sock, server_hostname=server_name or None) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise RuntimeError("сервер не прислал сертификат")
    return hashlib.sha256(der).hexdigest()


def xray_config(outbound: dict, port: int) -> dict:
    return {
        "log": {"loglevel": "warning"},
        "dns": {"queryStrategy": "UseIPv4", "servers": ["1.1.1.1"]},
        "inbounds": [
            {
                "listen": "127.0.0.1",
                "port": port,
                "protocol": "socks",
                "settings": {"auth": "noauth", "udp": True},
            }
        ],
        "outbounds": [outbound],
        "routing": {"domainStrategy": "AsIs"},
    }


def render_hysteria_config(profile: dict, port: int) -> str:
    document = {
        "server": profile.get("server", ""),
        "auth": profile.get("auth", ""),
        "tls": profile.get("tls") or {"insecure": True},
        "socks5": {"listen": f"127.0.0.1:{port}"},
        # Дольше окна замера, чтобы hop не сменил порт посередине проверки.
        "transport": {"type": "udp", "udp": {"hopInterval": "5m"}},
    }
    if profile.get("obfs"):
        document["obfs"] = profile["obfs"]
    return dump_yaml(document)


def dump_yaml(value: dict | list, indent: int = 0) -> str:
    return "\n".join(_yaml_lines(value, indent)) + "\n"


def _yaml_lines(value, indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{pad}{key}: {yaml_scalar(item)}")
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{pad}- {yaml_scalar(item)}")
    return lines


def yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def download_target(settings: dict) -> str:
    base = str(settings["download_url"]).strip()
    nbytes = int(settings["download_bytes"])
    if "{bytes}" in base:
        return base.format(bytes=nbytes)
    if "bytes=" in base:
        return base
    joiner = "&" if "?" in base else "?"
    return f"{base}{joiner}bytes={nbytes}"


def ensure_upload_file(size: int) -> Path:
    # Разреженный файл из нулей: место на диске почти не занимает.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "upload.bin"
    if not path.exists() or path.stat().st_size != size:
        with path.open("wb") as handle:
            handle.truncate(size)
        os.chmod(path, 0o600)
    return path


def launch(cmd: list[str], cancel: CancelToken) -> tuple[subprocess.Popen, LogBuffer]:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
    )
    logs = LogBuffer()
    logs.attach(proc)
    if not cancel.track(proc):
        raise RuntimeError("остановлено")
    return proc, logs


def stop_process(proc: subprocess.Popen, cancel: CancelToken) -> None:
    cancel.untrack(proc)
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def wait_port(port: int, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("процесс завершился")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return
        except OSError:
            time.sleep(0.15)
    raise TimeoutError("порт не открылся")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_ok(code: str) -> bool:
    try:
        number = int(code)
    except ValueError:
        return False
    return 200 <= number < 400


def short_curl_error(text: str) -> str:
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.lower().startswith("curl:"):
            line = line.split(")", 1)[-1].strip()
        return line[:240]
    return ""


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def humanize_curl(text: str) -> str:
    lowered = text.lower()
    mapping = (
        ("ssl connection timeout", "таймаут TLS через туннель"),
        ("operation timed out", "таймаут соединения"),
        ("connection timed out", "таймаут соединения"),
        ("connection refused", "соединение отклонено"),
        ("could not resolve host", "не удалось разрешить имя"),
        ("proxy connect", "прокси оборвал соединение"),
        ("empty reply", "пустой ответ сервера"),
    )
    for needle, label in mapping:
        if needle in lowered:
            return label
    return text


def useful_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chosen = ""
    for line in lines:
        if any(token in line for token in ("Failed to start", "FATAL", "failed to", "error")):
            chosen = line
    if not chosen and lines:
        chosen = lines[-1]
    match = re.search(r'"error":\s*"([^"]+)"', chosen)
    if match:
        chosen = match.group(1)
    chosen = re.sub(r"^\d{4}-\d{2}-\d{2}[T ].*?(FATAL|ERROR)\s*", "", chosen)
    return chosen.strip()[-500:]


def scrub(text: str, secrets: list[str]) -> str:
    cleaned = ANSI.sub("", text)
    for secret in secrets:
        if secret and len(secret) >= 3:
            cleaned = cleaned.replace(secret, "***")
    lines = []
    for line in cleaned.splitlines():
        if len(line) > 400:
            line = line[:400] + "…"
        lines.append(line)
    return "\n".join(lines).strip()[-700:]
