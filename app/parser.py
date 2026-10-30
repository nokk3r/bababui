"""Разбор подписок v2ray/xray и отдельных ссылок узлов."""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from urllib.parse import unquote

# parse_qs превращает «+» в пробел и ломает ключи WireGuard и пароли.
URI_RE = re.compile(
    r"(?:vless|vmess|trojan|ss|hysteria2|hy2|wireguard|wg)://[^\s]+",
    re.IGNORECASE,
)

# Xray убрал эти транспорты: такой конфиг не запустится.
REMOVED_NETWORKS = {"http": "HTTP/2", "quic": "QUIC"}

DEFAULT_PORTS = {
    "vless": 443,
    "vmess": 443,
    "trojan": 443,
    "ss": 8388,
    "hysteria2": 443,
    "hy2": 443,
    "wireguard": 51820,
    "wg": 51820,
}


@dataclass
class Transport:
    network: str = "tcp"
    security: str = "none"
    sni: str = ""
    fingerprint: str = ""
    alpn: str = ""
    allow_insecure: bool = False
    host: str = ""
    path: str = ""
    header_type: str = ""
    service_name: str = ""
    authority: str = ""
    mode: str = ""
    public_key: str = ""
    short_id: str = ""
    spider_x: str = ""
    flow: str = ""
    seed: str = ""
    quic_security: str = ""
    quic_key: str = ""


@dataclass
class ParsedNode:
    id: str
    name: str
    protocol: str
    address: str
    port: int
    network: str
    security: str
    badges: list[str]
    link: str = field(repr=False)
    supported: bool = True
    reason: str = ""
    engine: str = ""
    secrets: list[str] = field(default_factory=list, repr=False)
    xray_outbound: dict | None = field(default=None, repr=False)
    hysteria: dict | None = field(default=None, repr=False)
    legacy_id: str = ""


def parse_subscription(text: str, *, insecure_if_no_sni: bool = True) -> list[ParsedNode]:
    decoded = decode_subscription(text)
    seen: set[str] = set()
    nodes: list[ParsedNode] = []
    for match in URI_RE.finditer(decoded):
        uri = match.group(0).strip()
        try:
            node = parse_link(uri, insecure_if_no_sni=insecure_if_no_sni)
        except Exception as exc:  # noqa: BLE001 — одна битая ссылка не роняет подписку
            node = _unsupported_from_raw(uri, str(exc))
        if node.id in seen:
            continue
        seen.add(node.id)
        nodes.append(node)
        if len(nodes) >= 500:
            break
    return nodes


def parse_link(uri: str, *, insecure_if_no_sni: bool = True) -> ParsedNode:
    uri = uri.strip()
    if "://" not in uri:
        raise ValueError("нет схемы")
    scheme, rest = uri.split("://", 1)
    scheme = scheme.lower()
    name = ""
    if "#" in rest:
        rest, frag = rest.split("#", 1)
        name = unquote(frag).strip()
    if scheme == "vmess":
        return parse_vmess(rest, name, uri, insecure_if_no_sni=insecure_if_no_sni)
    if scheme in {"ss", "shadowsocks"} and "@" not in rest.split("?", 1)[0]:
        return parse_ss_legacy(rest, name, uri)
    query = ""
    if "?" in rest:
        rest, query = rest.split("?", 1)
    params = parse_query(query)
    userinfo = ""
    if "@" in rest:
        userinfo, hostport = rest.rsplit("@", 1)
        userinfo = unquote(userinfo)
    else:
        hostport = rest
    default_port = DEFAULT_PORTS.get(scheme, 443)
    host, port = split_hostport(hostport, default_port)
    if scheme == "vless":
        return parse_vless(userinfo, host, port, params, name, uri, insecure_if_no_sni)
    if scheme == "trojan":
        return parse_trojan(userinfo, host, port, params, name, uri, insecure_if_no_sni)
    if scheme in {"ss", "shadowsocks"}:
        return parse_ss(userinfo, host, port, params, name, uri)
    if scheme in {"hysteria2", "hy2"}:
        return parse_hysteria2(userinfo, host, port, params, name, uri, insecure_if_no_sni)
    if scheme in {"wireguard", "wg"}:
        return parse_wireguard(userinfo, host, port, params, name, uri)
    raise ValueError(f"протокол {scheme} не поддерживается")


def decode_subscription(text: str) -> str:
    stripped = text.strip().lstrip("\ufeff")
    if "://" in stripped:
        return stripped
    try:
        decoded = b64decode_text(stripped)
    except Exception:
        return stripped
    if "://" in decoded:
        return decoded
    return stripped


def b64decode_text(value: str) -> str:
    compact = "".join(value.split())
    compact += "=" * ((4 - len(compact) % 4) % 4)
    try:
        raw = base64.b64decode(compact, validate=False)
    except Exception:
        raw = base64.urlsafe_b64decode(compact)
    return raw.decode("utf-8")


def parse_query(query: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not query:
        return out
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        out[unquote(key)] = unquote(value)
    return out


def split_hostport(hostport: str, default_port: int) -> tuple[str, int]:
    hostport = hostport.strip()
    if not hostport:
        raise ValueError("пустой адрес")
    if hostport.startswith("["):
        host, _, tail = hostport[1:].partition("]")
        port = int(tail[1:]) if tail.startswith(":") and tail[1:] else default_port
    elif hostport.count(":") == 1:
        host, port_text = hostport.rsplit(":", 1)
        port = int(port_text)
    elif ":" not in hostport:
        host, port = hostport, default_port
    else:
        raise ValueError("не удалось разобрать адрес")
    host = host.strip()
    if not host or any(ch.isspace() for ch in host):
        raise ValueError("некорректный адрес")
    if not 1 <= port <= 65535:
        raise ValueError("некорректный порт")
    return host, port


def parse_vless(userinfo, host, port, params, name, uri, insecure_if_no_sni) -> ParsedNode:
    uuid = userinfo.strip()
    if not uuid:
        raise ValueError("нет UUID")
    transport = transport_from_params(params, insecure_if_no_sni=insecure_if_no_sni)
    transport.flow = params.get("flow", "")
    if transport.security == "reality" and not transport.public_key:
        return _node(
            protocol="vless",
            name=name,
            host=host,
            port=port,
            transport=transport,
            uri=uri,
            secret=uuid,
            supported=False,
            reason="у REALITY нет public key",
            secrets=[uuid],
        )
    user = {"id": uuid, "encryption": (params.get("encryption") or "none").strip() or "none"}
    flow = transport.flow
    if flow and transport.network in {"tcp", "raw"} and transport.security in {"tls", "reality"}:
        user["flow"] = flow
    outbound = {
        "tag": "proxy",
        "protocol": "vless",
        "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
        "streamSettings": stream_settings(transport),
    }
    return _node(
        protocol="vless",
        name=name,
        host=host,
        port=port,
        transport=transport,
        uri=uri,
        secret=uuid,
        engine="xray",
        outbound=outbound,
        secrets=[uuid, transport.public_key, transport.short_id],
        badges=_transport_badges(transport),
    )


def parse_trojan(userinfo, host, port, params, name, uri, insecure_if_no_sni) -> ParsedNode:
    password = userinfo
    if not password:
        raise ValueError("нет пароля")
    transport = transport_from_params(params, insecure_if_no_sni=insecure_if_no_sni)
    if transport.security == "none":
        transport.security = "tls"
        transport.allow_insecure = transport.allow_insecure or (insecure_if_no_sni and not transport.sni)
    outbound = {
        "tag": "proxy",
        "protocol": "trojan",
        "settings": {"servers": [{"address": host, "port": port, "password": password}]},
        "streamSettings": stream_settings(transport),
    }
    return _node(
        protocol="trojan",
        name=name,
        host=host,
        port=port,
        transport=transport,
        uri=uri,
        secret=password,
        engine="xray",
        outbound=outbound,
        secrets=[password],
        badges=_transport_badges(transport),
    )


def parse_ss(userinfo, host, port, params, name, uri) -> ParsedNode:
    if params.get("plugin"):
        return _plain_unsupported("shadowsocks", name, host, port, "tcp", "none", uri, "плагин shadowsocks не поддерживается")
    method, password = split_ss_userinfo(userinfo)
    outbound = {
        "tag": "proxy",
        "protocol": "shadowsocks",
        "settings": {
            "servers": [
                {"address": host, "port": port, "method": method, "password": password}
            ]
        },
    }
    network = params.get("type") or "tcp"
    transport = transport_from_params(params, insecure_if_no_sni=True) if network != "tcp" or params.get("security") else None
    if transport is not None:
        outbound["streamSettings"] = stream_settings(transport)
        net, sec = transport.network, transport.security
        badges = _transport_badges(transport)
    else:
        net, sec, badges = "tcp", "none", []
    return _node(
        protocol="shadowsocks",
        name=name,
        host=host,
        port=port,
        transport=Transport(network=net, security=sec),
        uri=uri,
        secret=f"{method}:{password}",
        engine="xray",
        outbound=outbound,
        secrets=[password],
        badges=badges,
        extra=method,
    )


def parse_ss_legacy(rest: str, name: str, uri: str) -> ParsedNode:
    body = rest.split("?", 1)[0]
    decoded = b64decode_text(body)
    if "?" in decoded:
        decoded = decoded.split("?", 1)[0]
    if "@" not in decoded or ":" not in decoded.split("@", 1)[0]:
        raise ValueError("не удалось разобрать shadowsocks")
    userinfo, hostport = decoded.rsplit("@", 1)
    method, password = userinfo.split(":", 1)
    host, port = split_hostport(hostport, 8388)
    outbound = {
        "tag": "proxy",
        "protocol": "shadowsocks",
        "settings": {"servers": [{"address": host, "port": port, "method": method, "password": password}]},
    }
    return _node(
        protocol="shadowsocks",
        name=name,
        host=host,
        port=port,
        transport=Transport(),
        uri=uri,
        secret=f"{method}:{password}",
        engine="xray",
        outbound=outbound,
        secrets=[password],
        extra=method,
    )


def parse_vmess(rest: str, name: str, uri: str, *, insecure_if_no_sni: bool) -> ParsedNode:
    payload = b64decode_text(rest.split("?", 1)[0])
    data = json.loads(payload)
    host = str(data.get("add") or "").strip()
    port = int(data.get("port") or 443)
    uuid = str(data.get("id") or "").strip()
    if not host or not uuid:
        raise ValueError("неполный vmess")
    display = name or str(data.get("ps") or "")
    security = str(data.get("tls") or data.get("security") or "")
    if security in {"", "none", "0"}:
        security = "none"
    params = {
        "type": str(data.get("net") or "tcp"),
        "security": security,
        "sni": str(data.get("sni") or ""),
        "fp": str(data.get("fp") or ""),
        "alpn": str(data.get("alpn") or ""),
        "host": str(data.get("host") or ""),
        "path": str(data.get("path") or ""),
        "headerType": str(data.get("type") or ""),
        "serviceName": str(data.get("path") or "") if str(data.get("net")) == "grpc" else "",
        "pbk": str(data.get("pbk") or ""),
        "sid": str(data.get("sid") or ""),
        "spx": str(data.get("spx") or ""),
    }
    transport = transport_from_params(params, insecure_if_no_sni=insecure_if_no_sni)
    user = {
        "id": uuid,
        "security": str(data.get("scy") or "auto"),
        "alterId": int(data.get("aid") or 0),
    }
    outbound = {
        "tag": "proxy",
        "protocol": "vmess",
        "settings": {"vnext": [{"address": host, "port": port, "users": [user]}]},
        "streamSettings": stream_settings(transport),
    }
    return _node(
        protocol="vmess",
        name=display,
        host=host,
        port=port,
        transport=transport,
        uri=uri,
        secret=uuid,
        engine="xray",
        outbound=outbound,
        secrets=[uuid],
        badges=_transport_badges(transport),
    )


def parse_hysteria2(userinfo, host, port, params, name, uri, insecure_if_no_sni) -> ParsedNode:
    if ":" in userinfo and params.get("auth"):
        auth = unquote(params["auth"])
    else:
        auth = userinfo
    if not auth:
        raise ValueError("нет пароля hysteria2")
    sni = params.get("sni") or params.get("peer") or ""
    insecure_flag = _truthy(params.get("insecure") or params.get("allowInsecure"))
    allow_insecure = insecure_flag or (insecure_if_no_sni and not sni)
    mport = normalize_mport(params.get("mport") or "")
    server = f"{_host_literal(host)}:{port}"
    if mport:
        server = f"{server},{mport}"
    tls: dict = {"insecure": True} if allow_insecure else {}
    if sni:
        tls["sni"] = sni
        if not allow_insecure:
            tls["insecure"] = False
    if not tls:
        tls = {"insecure": False}
    pin = params.get("pinSHA256") or ""
    if pin:
        tls["pinSHA256"] = pin
    profile: dict = {"server": server, "auth": auth, "tls": tls}
    obfs = params.get("obfs") or ""
    obfs_password = params.get("obfs-password") or params.get("obfsPassword") or ""
    secrets = [auth]
    badges: list[str] = []
    if obfs:
        if not obfs_password:
            return _plain_unsupported(
                "hysteria2", name, host, port, "udp", "tls", uri, "у obfs нет пароля", [auth]
            )
        profile["obfs"] = {"type": obfs, obfs: {"password": obfs_password}}
        secrets.append(obfs_password)
        badges.append(obfs)
    if mport:
        badges.append("hop")
    transport = Transport(network="udp", security="tls", sni=sni, allow_insecure=allow_insecure)
    return _node(
        protocol="hysteria2",
        name=name,
        host=host,
        port=port,
        transport=transport,
        uri=uri,
        secret=auth + "|" + obfs_password,
        engine="hysteria",
        hysteria=profile,
        secrets=secrets,
        badges=badges,
        extra=f"{obfs}|{mport}",
    )


def parse_wireguard(userinfo, host, port, params, name, uri) -> ParsedNode:
    private_key = userinfo.strip()
    public_key = params.get("publickey") or params.get("publicKey") or ""
    address = params.get("address") or params.get("ip") or ""
    if not private_key or not public_key:
        raise ValueError("нет ключей WireGuard")
    if not address:
        return _plain_unsupported(
            "wireguard", name, host, port, "udp", "none", uri, "нет локального адреса", [private_key, public_key]
        )
    addresses = [item.strip() for item in address.split(",") if item.strip()]
    mtu = _int(params.get("mtu"), 1420)
    keepalive = _int(params.get("keepalive") or params.get("keepAlive"), 0)
    reserved = _reserved(params.get("reserved"))
    peer = {
        "endpoint": endpoint(host, port),
        "publicKey": public_key,
        "allowedIPs": ["0.0.0.0/0", "::/0"],
    }
    if keepalive > 0:
        peer["keepAlive"] = keepalive
    psk = params.get("psk") or params.get("preSharedKey") or ""
    if psk:
        peer["preSharedKey"] = psk
    settings: dict = {
        "secretKey": private_key,
        "address": addresses,
        "peers": [peer],
        "mtu": mtu,
        "noKernelTun": True,
        "domainStrategy": "ForceIPv4",
    }
    if reserved:
        settings["reserved"] = reserved
    outbound = {"tag": "proxy", "protocol": "wireguard", "settings": settings}
    secrets = [private_key, public_key]
    if psk:
        secrets.append(psk)
    local = addresses[0].split("/")[0]
    return _node(
        protocol="wireguard",
        name=name,
        host=host,
        port=port,
        transport=Transport(network="udp", security="none"),
        uri=uri,
        secret=private_key + "|" + public_key,
        engine="xray",
        outbound=outbound,
        secrets=secrets,
        badges=[local] if local else [],
        extra=address,
    )


def transport_from_params(params: dict[str, str], *, insecure_if_no_sni: bool) -> Transport:
    network = (params.get("type") or params.get("net") or "tcp").lower()
    if network == "h2":
        network = "http"
    if network == "splithttp":
        network = "xhttp"
    security = (params.get("security") or "none").lower()
    if security in {"", "0"}:
        security = "none"
    sni = params.get("sni") or params.get("servername") or params.get("peer") or ""
    allow = _truthy(params.get("allowInsecure") or params.get("insecure") or params.get("skip-cert-verify"))
    if insecure_if_no_sni and security == "tls" and not sni:
        allow = True
    header = params.get("headerType") or ""
    if header.lower() == "none":
        header = ""
    return Transport(
        network=network or "tcp",
        security=security,
        sni=sni,
        fingerprint=params.get("fp") or params.get("fingerprint") or "",
        alpn=params.get("alpn") or "",
        allow_insecure=allow,
        host=params.get("host") or "",
        path=unquote(params.get("path") or ""),
        header_type=header,
        service_name=params.get("serviceName") or "",
        authority=params.get("authority") or "",
        mode=params.get("mode") or "",
        public_key=params.get("pbk") or params.get("publicKey") or "",
        short_id=params.get("sid") or params.get("shortId") or "",
        spider_x=unquote(params.get("spx") or params.get("spiderX") or ""),
        seed=params.get("seed") or "",
        quic_security=params.get("quicSecurity") or "",
        quic_key=params.get("key") or "",
    )


def stream_settings(transport: Transport) -> dict:
    network = transport.network or "tcp"
    settings: dict = {"network": network}
    if transport.security == "tls":
        tls: dict = {}
        if transport.sni:
            tls["serverName"] = transport.sni
        if transport.fingerprint:
            tls["fingerprint"] = transport.fingerprint
        alpn = [item.strip() for item in transport.alpn.split(",") if item.strip()]
        if alpn:
            tls["alpn"] = alpn
        if transport.allow_insecure:
            tls["allowInsecure"] = True
        settings["security"] = "tls"
        settings["tlsSettings"] = tls
    elif transport.security == "reality":
        settings["security"] = "reality"
        settings["realitySettings"] = {
            "serverName": transport.sni,
            "fingerprint": transport.fingerprint or "chrome",
            "publicKey": transport.public_key,
            "shortId": transport.short_id,
            "spiderX": transport.spider_x or "/",
        }
    else:
        settings["security"] = "none"

    if network == "ws":
        ws = {"path": transport.path or "/"}
        if transport.host:
            ws["host"] = transport.host
            ws["headers"] = {"Host": transport.host}
        settings["wsSettings"] = ws
    elif network == "grpc":
        grpc: dict = {}
        service = transport.service_name or transport.path.lstrip("/")
        if service:
            grpc["serviceName"] = service
        authority = transport.authority or transport.host
        if authority:
            grpc["authority"] = authority
        if transport.mode == "multi":
            grpc["multiMode"] = True
        settings["grpcSettings"] = grpc
    elif network == "http":
        http: dict = {"path": transport.path or "/"}
        if transport.host:
            http["host"] = [item.strip() for item in transport.host.split(",") if item.strip()]
        settings["httpSettings"] = http
    elif network == "httpupgrade":
        upgrade = {"path": transport.path or "/"}
        if transport.host:
            upgrade["host"] = transport.host
        settings["httpupgradeSettings"] = upgrade
    elif network == "xhttp":
        xhttp = {"path": transport.path or "/", "mode": transport.mode or "auto"}
        if transport.host:
            xhttp["host"] = transport.host
        settings["xhttpSettings"] = xhttp
    elif network == "tcp" and transport.header_type == "http":
        request: dict = {"path": [transport.path or "/"]}
        if transport.host:
            request["headers"] = {"Host": [transport.host]}
        settings["tcpSettings"] = {"header": {"type": "http", "request": request}}
    elif network == "kcp":
        kcp: dict = {"header": {"type": transport.header_type or "none"}}
        if transport.seed:
            kcp["seed"] = transport.seed
        settings["kcpSettings"] = kcp
    elif network == "quic":
        settings["quicSettings"] = {
            "security": transport.quic_security or "none",
            "key": transport.quic_key,
            "header": {"type": transport.header_type or "none"},
        }
    return settings


def _node(
    *,
    protocol: str,
    name: str,
    host: str,
    port: int,
    transport: Transport,
    uri: str,
    secret: str,
    supported: bool = True,
    reason: str = "",
    engine: str = "",
    outbound: dict | None = None,
    hysteria: dict | None = None,
    secrets: list[str] | None = None,
    badges: list[str] | None = None,
    extra: str = "",
) -> ParsedNode:
    removed = REMOVED_NETWORKS.get(transport.network)
    if supported and removed:
        supported = False
        reason = f"транспорт {removed} удалён из Xray"
    extra_id = extra or "|".join(
        [
            transport.network,
            transport.security,
            transport.path,
            transport.service_name,
        ]
    )
    legacy_id = make_id(protocol, host, port, transport.network, secret, extra_id)
    identity = [transport.sni, transport.host, transport.public_key, transport.short_id, transport.flow]
    node_id = legacy_id
    if any(identity):
        node_id = make_id(protocol, host, port, transport.network, secret, "|".join([extra_id, *identity]))
    return ParsedNode(
        id=node_id,
        legacy_id=legacy_id,
        name=normalize_name(name, protocol, host, port),
        protocol=protocol,
        address=host,
        port=port,
        network=transport.network,
        security=transport.security,
        badges=[badge for badge in (badges or []) if badge],
        link=uri,
        supported=supported,
        reason=reason,
        engine=engine if supported else "",
        secrets=[item for item in (secrets or []) if item],
        xray_outbound=outbound,
        hysteria=hysteria,
    )


def _plain_unsupported(protocol, name, host, port, network, security, uri, reason, secrets=None) -> ParsedNode:
    transport = Transport(network=network, security=security)
    return _node(
        protocol=protocol,
        name=name,
        host=host,
        port=port,
        transport=transport,
        uri=uri,
        secret=reason,
        supported=False,
        reason=reason,
        secrets=secrets or [],
    )


def _unsupported_from_raw(uri: str, reason: str) -> ParsedNode:
    scheme = uri.split("://", 1)[0].lower()
    return ParsedNode(
        id=make_id(scheme or "bad", "invalid", 0, "", uri, reason),
        name=normalize_name("", scheme or "узел", "?", 0),
        protocol=scheme or "unknown",
        address="?",
        port=0,
        network="",
        security="",
        badges=[],
        link=uri,
        supported=False,
        reason=reason[:300],
    )


def _transport_badges(transport: Transport) -> list[str]:
    badges = []
    if transport.flow:
        badges.append("vision" if "vision" in transport.flow else transport.flow)
    if transport.security == "reality":
        badges.append("reality")
    return badges


def make_id(protocol: str, host: str, port: int, network: str, secret: str, extra: str) -> str:
    raw = "|".join([protocol, host.lower(), str(port), network, secret, extra])
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def normalize_name(name: str, protocol: str, host: str, port: int) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        name = f"{protocol} {host}:{port}"
    return name[:180]


def endpoint(host: str, port: int) -> str:
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _host_literal(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


def split_ss_userinfo(userinfo: str) -> tuple[str, str]:
    # В открытом виде метод отделён двоеточием. В SIP002 userinfo — base64 без «:».
    if ":" in userinfo:
        method, password = userinfo.split(":", 1)
        if _ss_method(method) and password:
            return method, password
    decoded = b64decode_text(userinfo)
    if ":" not in decoded:
        raise ValueError("не удалось разобрать shadowsocks")
    method, password = decoded.split(":", 1)
    if not _ss_method(method) or not password:
        raise ValueError("не удалось разобрать shadowsocks")
    return method, password


def _ss_method(method: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9._+-]{2,80}", method))


def normalize_mport(value: str) -> str:
    value = value.strip()
    if re.fullmatch(r"\d{1,5}:\d{1,5}", value):
        return value.replace(":", "-")
    return value


def _truthy(value: str | None) -> bool:
    return (value or "").lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    try:
        return int(value) if value else default
    except ValueError:
        return default


def _reserved(value: str | None) -> list[int] | None:
    if not value:
        return None
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 3:
        return None
    try:
        numbers = [int(item) for item in parts]
    except ValueError:
        return None
    if any(not 0 <= item <= 255 for item in numbers):
        return None
    return numbers
