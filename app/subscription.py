"""Загрузка подписки и запись узлов в базу."""

from __future__ import annotations

import logging
import ssl
import threading
import urllib.error
import urllib.request

from app import db
from app.i18n import msg
from app.parser import decode_subscription, parse_subscription

logger = logging.getLogger("checker.subscription")
_lock = threading.Lock()
USER_AGENT = "v2rayN/6.49"


class SubscriptionError(Exception):
    pass


def refresh() -> int:
    with _lock:
        settings = db.get_raw_settings()
        urls = [line.strip() for line in settings.get("subscription_url", "").splitlines() if line.strip()]
        if not urls:
            db.set_meta("last_refresh_error", msg("no_subscription_url"))
            raise SubscriptionError(msg("no_subscription_url"))
        insecure = settings.get("subscription_insecure", "1") == "1"
        insecure_sni = settings.get("tls_insecure_if_no_sni", "1") == "1"
        chunks: list[str] = []
        userinfo = ""
        try:
            for url in urls:
                body, header = fetch(url, insecure=insecure)
                # Склеенный base64 не декодируется: у каждой подписки свой формат и паддинг.
                chunks.append(decode_subscription(body))
                if header:
                    userinfo = header
            nodes = parse_subscription("\n".join(chunks), insecure_if_no_sni=insecure_sni)
        except SubscriptionError as exc:
            db.set_meta("last_refresh_error", str(exc))
            raise
        except Exception as exc:
            logger.exception("subscription parse failed")
            db.set_meta("last_refresh_error", f"{msg('subscription_parse_failed')}: {exc}")
            raise SubscriptionError(msg("subscription_parse_failed")) from exc
        if not nodes:
            db.set_meta("last_refresh_error", msg("no_nodes_in_subscription"))
            raise SubscriptionError(msg("no_nodes_in_subscription"))
        count = db.sync_nodes(nodes)
        db.set_meta("subscription_userinfo", userinfo)
        db.set_meta("last_refresh_at", db.utcnow())
        db.set_meta("last_refresh_error", "")
        logger.info("subscription refreshed: %s nodes", count)
        return count


def fetch(url: str, *, insecure: bool) -> tuple[str, str]:
    if not url.lower().startswith(("https://", "http://")):
        raise SubscriptionError(msg("invalid_url_scheme"))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            header = response.headers.get("Subscription-Userinfo", "")
            return body, header
    except urllib.error.HTTPError as exc:
        raise SubscriptionError(msg("subscription_http", code=exc.code)) from exc
    except Exception as exc:
        raise SubscriptionError(f"{msg('subscription_fetch_failed')}: {exc}") from exc


def userinfo_view(header: str) -> dict | None:
    if not header:
        return None
    data: dict[str, int] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        try:
            data[key.strip()] = int(value.strip())
        except ValueError:
            continue
    if not data:
        return None
    if data.get("total", 0) <= 0 and data.get("expire", 0) <= 0:
        return None
    return data

