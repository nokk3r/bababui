import base64
import json
import unittest

from app.engines import download_target, pin_tls_settings, render_hysteria_config
from app.parser import parse_link, parse_subscription

UUID = "11111111-1111-1111-1111-111111111111"


class ParserTests(unittest.TestCase):
    def test_base64_subscription_and_stable_id(self):
        first = (
            f"vless://{UUID}@203.0.113.5:443?encryption=none&security=tls&type=tcp"
            "&fp=chrome&alpn=h2%2Chttp%2F1.1&sni=#Имя"
        )
        renamed = first.replace("#Имя", "#Другое")
        blob = base64.b64encode(f"{first}\n{first}\n".encode()).decode()
        nodes = parse_subscription(blob)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].name, "Имя")
        self.assertEqual(parse_link(renamed).id, nodes[0].id)
        other = first.replace(UUID, "22222222-2222-2222-2222-222222222222")
        self.assertNotEqual(parse_link(other).id, nodes[0].id)

    def test_vless_tls_without_sni_allows_insecure(self):
        link = (
            f"vless://{UUID}@203.0.113.5:443?encryption=none&security=tls&type=tcp"
            "&fp=chrome&alpn=h2%2Chttp%2F1.1&sni=#vls"
        )
        node = parse_link(link)
        tls = node.xray_outbound["streamSettings"]["tlsSettings"]
        self.assertTrue(tls["allowInsecure"])
        self.assertNotIn("serverName", tls)
        self.assertEqual(tls["alpn"], ["h2", "http/1.1"])
        self.assertEqual(tls["fingerprint"], "chrome")
        strict = parse_link(link, insecure_if_no_sni=False)
        self.assertNotIn("allowInsecure", strict.xray_outbound["streamSettings"]["tlsSettings"])

    def test_reality_keeps_plus_in_public_key(self):
        link = (
            f"vless://{UUID}@203.0.113.5:443?encryption=none&security=reality&type=tcp"
            "&fp=chrome&sni=www.example.com&pbk=abc+key&sid=abcd&flow=xtls-rprx-vision#real"
        )
        node = parse_link(link)
        reality = node.xray_outbound["streamSettings"]["realitySettings"]
        self.assertEqual(reality["publicKey"], "abc+key")
        user = node.xray_outbound["settings"]["vnext"][0]["users"][0]
        self.assertEqual(user["flow"], "xtls-rprx-vision")
        self.assertIn("reality", node.badges)

    def test_flow_dropped_for_websocket(self):
        link = (
            f"vless://{UUID}@203.0.113.5:443?encryption=none&security=tls&type=ws"
            "&path=%2Fray&host=ex.com&sni=ex.com&flow=xtls-rprx-vision#ws"
        )
        node = parse_link(link)
        user = node.xray_outbound["settings"]["vnext"][0]["users"][0]
        self.assertNotIn("flow", user)
        ws = node.xray_outbound["streamSettings"]["wsSettings"]
        self.assertEqual(ws["path"], "/ray")
        self.assertEqual(ws["host"], "ex.com")

    def test_hysteria_hop_and_obfs(self):
        link = (
            "hysteria2://p%40ss@203.0.113.5:2002?obfs=salamander&obfs-password=ob%2Bpass"
            "&mport=20000-30000&security=tls#hop"
        )
        node = parse_link(link)
        self.assertEqual(node.protocol, "hysteria2")
        self.assertEqual(node.engine, "hysteria")
        self.assertEqual(node.hysteria["auth"], "p@ss")
        self.assertEqual(node.hysteria["server"], "203.0.113.5:2002,20000-30000")
        self.assertEqual(node.hysteria["obfs"]["salamander"]["password"], "ob+pass")
        self.assertTrue(node.hysteria["tls"]["insecure"])
        self.assertIn("hop", node.badges)
        rendered = render_hysteria_config(node.hysteria, 18080)
        self.assertIn('listen: "127.0.0.1:18080"', rendered)
        self.assertIn('hopInterval: "5m"', rendered)
        self.assertIn('password: "ob+pass"', rendered)

    def test_wireguard_keys_and_userspace(self):
        link = (
            "wireguard://priv+key/abc=@203.0.113.8:51820?publickey=abc+def/ghi="
            "&address=10.0.0.2/32&mtu=1400&keepalive=25#wg"
        )
        node = parse_link(link)
        settings = node.xray_outbound["settings"]
        self.assertEqual(settings["secretKey"], "priv+key/abc=")
        self.assertEqual(settings["peers"][0]["publicKey"], "abc+def/ghi=")
        self.assertEqual(settings["peers"][0]["endpoint"], "203.0.113.8:51820")
        self.assertEqual(settings["address"], ["10.0.0.2/32"])
        self.assertTrue(settings["noKernelTun"])
        self.assertEqual(settings["mtu"], 1400)
        self.assertEqual(settings["peers"][0]["keepAlive"], 25)

    def test_vmess_and_shadowsocks(self):
        payload = {
            "v": "2",
            "ps": "vm",
            "add": "203.0.113.7",
            "port": "443",
            "id": UUID,
            "aid": "0",
            "net": "ws",
            "type": "none",
            "host": "ex.com",
            "path": "/ray",
            "tls": "tls",
            "sni": "ex.com",
        }
        vmess = "vmess://" + base64.b64encode(json.dumps(payload).encode()).decode()
        node = parse_link(vmess)
        self.assertEqual(node.protocol, "vmess")
        self.assertEqual(node.name, "vm")
        self.assertEqual(node.xray_outbound["streamSettings"]["network"], "ws")

        user = base64.b64encode(b"chacha20-ietf-poly1305:pass+word").decode()
        ss = parse_link(f"ss://{user}@203.0.113.6:8388#ss1")
        server = ss.xray_outbound["settings"]["servers"][0]
        self.assertEqual(server["method"], "chacha20-ietf-poly1305")
        self.assertEqual(server["password"], "pass+word")

        legacy = base64.b64encode(b"aes-256-gcm:secret@203.0.113.6:8388").decode()
        old = parse_link(f"ss://{legacy}#legacy")
        self.assertEqual(old.xray_outbound["settings"]["servers"][0]["method"], "aes-256-gcm")

        plugin = parse_link(f"ss://{user}@203.0.113.6:8388?plugin=obfs#nope")
        self.assertFalse(plugin.supported)

    def test_pin_replaces_allow_insecure(self):
        outbound = {
            "streamSettings": {
                "tlsSettings": {"allowInsecure": True, "fingerprint": "chrome"},
            }
        }
        pin_tls_settings(outbound, "abc")
        tls = outbound["streamSettings"]["tlsSettings"]
        self.assertNotIn("allowInsecure", tls)
        self.assertEqual(tls["pinnedPeerCertSha256"], "abc")
        self.assertEqual(tls["fingerprint"], "chrome")

    def test_download_target(self):
        url = download_target({"download_url": "https://speed.cloudflare.com/__down", "download_bytes": 8000000})
        self.assertEqual(url, "https://speed.cloudflare.com/__down?bytes=8000000")
        kept = download_target(
            {"download_url": "https://example.test/file?bytes=10", "download_bytes": 8000000}
        )
        self.assertEqual(kept, "https://example.test/file?bytes=10")


if __name__ == "__main__":
    unittest.main()
