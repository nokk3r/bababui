"""Загрузка подписки и запись узлов в базу."""

from __future__ import annotations

import logging
import ssl
import threading
import urllib.error
import urllib.request
from collections.abc import Mapping
from urllib.parse import urlsplit

from app import db
from app.i18n import msg
from app.parser import b64decode_text, parse_subscription

logger = logging.getLogger("checker.subscription")
_lock = threading.Lock()
USER_AGENT = "v2rayN/6.49"


class SubscriptionError(Exception):
    pass


def source_label(source: dict) -> str:
    """Имя источника для логов и ошибок: своё имя, название из подписки, хост или «без названия»."""
    return source["name"] or source["title"] or urlsplit(source["url"]).netloc or msg("source_untitled")


def refresh_source(source_id: int) -> int:
    with _lock:
        source = db.get_source(source_id)
        if source is None:
            raise SubscriptionError(msg("source_not_found"))
        return _refresh(source)


def refresh_all() -> tuple[int, list[str]]:
    """Обновляет все источники по очереди. Битая подписка не мешает остальным: её ошибка остаётся
    у неё и возвращается списком. Исключение — только если не обновился ни один источник."""
    with _lock:
        sources = db.list_sources()
        if not sources:
            raise SubscriptionError(msg("no_sources"))
        errors: list[str] = []
        for source in sources:
            try:
                _refresh(source)
            except SubscriptionError as exc:
                errors.append(f"{source_label(source)}: {exc}")
        if len(errors) == len(sources):
            raise SubscriptionError("; ".join(errors))
        return db.count_active_nodes(), errors


def refresh_many(source_ids: list[int]) -> list[str]:
    """Обновляет выбранные источники и возвращает ошибки тех, что не обновились."""
    errors: list[str] = []
    with _lock:
        for source_id in source_ids:
            source = db.get_source(source_id)
            if source is None:
                continue
            try:
                _refresh(source)
            except SubscriptionError as exc:
                errors.append(f"{source_label(source)}: {exc}")
    return errors


def _refresh(source: dict) -> int:
    settings = db.get_raw_settings()
    insecure_sni = settings.get("tls_insecure_if_no_sni", "1") == "1"
    userinfo = title = ""
    try:
        if source["kind"] == "subscription":
            text, headers = fetch(source["url"], insecure=source["insecure"])
            userinfo = headers.get("Subscription-Userinfo", "") or ""
            title = profile_title(headers.get("Profile-Title", "") or "")
        else:
            # Группа ничего не скачивает: её узлы — ссылки, вписанные вручную.
            text = source["links"]
        nodes = parse_subscription(text, insecure_if_no_sni=insecure_sni)
    except SubscriptionError as exc:
        db.set_source_status(source["id"], error=str(exc))
        raise
    except Exception as exc:
        logger.exception("subscription parse failed")
        db.set_source_status(source["id"], error=f"{msg('subscription_parse_failed')}: {exc}")
        raise SubscriptionError(msg("subscription_parse_failed")) from exc
    if not nodes and source["kind"] == "subscription":
        db.set_source_status(source["id"], error=msg("no_nodes_in_subscription"))
        raise SubscriptionError(msg("no_nodes_in_subscription"))
    count = db.sync_nodes(source["id"], nodes)
    db.set_source_status(source["id"], error="", refreshed_at=db.utcnow(), userinfo=userinfo, title=title)
    logger.info("source %s refreshed: %s nodes", source["id"], count)
    return count


def profile_title(value: str) -> str:
    """Название подписки из заголовка Profile-Title: открытым текстом или как base64:…"""
    value = value.strip()
    if value.lower().startswith("base64:"):
        try:
            value = b64decode_text(value[7:])
        except Exception:
            return ""
    else:
        # urllib читает заголовки как latin-1, а панели шлют UTF-8.
        try:
            value = value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return " ".join(value.split())[:80]


def fetch(url: str, *, insecure: bool) -> tuple[str, Mapping[str, str]]:
    if not url.lower().startswith(("https://", "http://")):
        raise SubscriptionError(msg("invalid_url_scheme"))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    context = ssl._create_unverified_context() if insecure else ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
            return body, response.headers
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

