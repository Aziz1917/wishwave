import asyncio
import json
import re
from decimal import Decimal, InvalidOperation
from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - optional dependency in local env
    curl_requests = None

try:
    import browser_cookie3
except ImportError:  # pragma: no cover - optional dependency in local env
    browser_cookie3 = None

BLOCKED_STATUSES = {403, 429, 451, 498}
PRICE_PATTERN = re.compile(r"([0-9][0-9\s\u00a0]*(?:[.,][0-9]{1,2})?)")
JSON_STRING_RE = r"((?:\\.|[^\"\\]){3,400})"

REQUEST_HEADERS = [
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    },
    {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.7",
        "Upgrade-Insecure-Requests": "1",
    },
]

WB_BASKETS = [f"{index:02d}" for index in range(1, 31)]


class MetadataExtractionError(Exception):
    pass


@dataclass(slots=True)
class FetchedPage:
    status_code: int
    url: str
    text: str


def _host_family(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "ozon." in host:
        return "ozon"
    if "wildberries." in host or host.endswith("wb.ru") or "wbbasket.ru" in host:
        return "wb"
    if "market.yandex." in host or host.endswith(".market.yandex.ru"):
        return "yandex_market"
    if "megamarket." in host:
        return "megamarket"
    return "generic"


def _extract_numeric_id(url: str) -> str | None:
    parsed = urlparse(url)
    path_match = re.search(r"/(?:catalog|product|products|details|card)/([0-9]{6,12})", parsed.path)
    if path_match:
        return path_match.group(1)
    nm_match = re.search(r"(?:\?|&)(?:nm|id|sku)=([0-9]{6,12})", parsed.query)
    if nm_match:
        return nm_match.group(1)
    fallback_match = re.search(r"([0-9]{6,12})", parsed.path)
    if fallback_match:
        return fallback_match.group(1)
    return None


def _wb_vol_part(nm_id: str) -> tuple[str, str] | None:
    if len(nm_id) < 6:
        return None
    vol = nm_id[:-5]
    part = nm_id[:-3]
    if not vol or not part:
        return None
    return vol, part


def _extract_price_from_price_history(payload: Any) -> tuple[int | None, str | None]:
    if not isinstance(payload, list):
        return None, None
    best_dt = -1
    best_price_cents: int | None = None
    best_currency: str | None = None
    for row in payload:
        if not isinstance(row, dict):
            continue
        dt = row.get("dt")
        price_payload = row.get("price")
        if not isinstance(price_payload, dict):
            continue
        for currency_code, raw_value in price_payload.items():
            cents = _price_to_cents(raw_value, minor_units=True)
            if not _is_reasonable_price(cents):
                continue
            if isinstance(dt, int) and dt >= best_dt:
                best_dt = dt
                best_price_cents = cents
                best_currency = _normalize_currency(str(currency_code)) or "RUB"
    return best_price_cents, best_currency


async def _extract_wb_from_basket(url: str) -> dict[str, Any] | None:
    nm_id = _extract_numeric_id(url)
    if nm_id is None:
        return None
    vol_part = _wb_vol_part(nm_id)
    if vol_part is None:
        return None
    vol, part = vol_part

    async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
        found_card: dict[str, Any] | None = None
        basket_id: str | None = None

        semaphore = asyncio.Semaphore(8)

        async def _try_basket(current_basket: str) -> tuple[str, dict[str, Any]] | None:
            card_url = f"https://basket-{current_basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
            try:
                async with semaphore:
                    card_response = await client.get(card_url)
            except httpx.HTTPError:
                return None
            if card_response.status_code != 200:
                return None
            try:
                card_payload = card_response.json()
            except ValueError:
                return None
            return current_basket, card_payload

        tasks = [asyncio.create_task(_try_basket(current_basket)) for current_basket in WB_BASKETS]
        try:
            for completed in asyncio.as_completed(tasks):
                result = await completed
                if result is None:
                    continue
                basket_id, found_card = result
                break
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if found_card is None or basket_id is None:
            # One more pass can recover from transient TLS/connect timeouts.
            for current_basket in WB_BASKETS:
                card_url = f"https://basket-{current_basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"
                try:
                    card_response = await client.get(card_url)
                except httpx.HTTPError:
                    continue
                if card_response.status_code != 200:
                    continue
                try:
                    found_card = card_response.json()
                except ValueError:
                    continue
                basket_id = current_basket
                break

        if found_card is None or basket_id is None:
            return None

        title = found_card.get("imt_name") or found_card.get("name")
        if not isinstance(title, str) or not title.strip():
            return None

        media = found_card.get("media") if isinstance(found_card.get("media"), dict) else {}
        photo_count_raw = media.get("photo_count") if isinstance(media, dict) else 0
        photo_count = int(photo_count_raw) if isinstance(photo_count_raw, (int, float)) else 0
        image_url = (
            f"https://basket-{basket_id}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big/1.webp"
            if photo_count > 0
            else None
        )

        price_cents: int | None = None
        currency: str | None = None
        price_history_url = f"https://basket-{basket_id}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/price-history.json"
        try:
            price_history_response = await client.get(price_history_url)
            if price_history_response.status_code == 200:
                price_payload = price_history_response.json()
                price_cents, currency = _extract_price_from_price_history(price_payload)
        except (httpx.HTTPError, ValueError):
            pass

    if price_cents is None and image_url is None:
        return None

    return {
        "source_url": url,
        "title": title.strip(),
        "image_url": image_url,
        "price_cents": price_cents,
        "currency": currency or ("RUB" if price_cents is not None else None),
    }


def _to_yandex_integration_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.netloc.endswith("market.yandex.ru"):
        return url
    return parsed._replace(netloc="ngo.integration.market.yandex.ru").geturl()


def _cookie_domain_candidates(url: str) -> list[str]:
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":", 1)[0]
    if not host:
        return []

    candidates: list[str] = []

    def _add(domain: str):
        if domain and domain not in candidates:
            candidates.append(domain)

    _add(host)
    if host.startswith("www."):
        _add(host[4:])
    if host.endswith(".market.yandex.ru"):
        _add("market.yandex.ru")
        _add("yandex.ru")
    if host.endswith(".ozon.ru") or host == "ozon.ru":
        _add("ozon.ru")
    if host.endswith(".wildberries.ru") or host == "wildberries.ru":
        _add("wildberries.ru")
    return candidates


def _browser_cookie_loaders() -> list[Any]:
    if browser_cookie3 is None:
        return []
    loaders: list[Any] = []
    for attr in ("firefox", "chrome", "edge", "brave"):
        loader = getattr(browser_cookie3, attr, None)
        if callable(loader):
            loaders.append(loader)
    return loaders


@lru_cache(maxsize=32)
def _browser_cookie_items(domain: str) -> tuple[tuple[str, str], ...]:
    cookie_map: dict[str, str] = {}
    for loader in _browser_cookie_loaders():
        try:
            jar = loader(domain_name=domain)
        except Exception:
            continue
        for cookie in jar:
            name = str(getattr(cookie, "name", "")).strip()
            value = str(getattr(cookie, "value", "")).strip()
            if name and value and name not in cookie_map:
                cookie_map[name] = value
    return tuple(cookie_map.items())


def _browser_cookies_for_url(url: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for domain in _cookie_domain_candidates(url):
        for name, value in _browser_cookie_items(domain):
            cookies.setdefault(name, value)
    return cookies


def _normalize_currency(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip().upper()
    if not cleaned:
        return None
    if cleaned in {"RUR", "RUB", "RUBLE", "РУБ", "₽"}:
        return "RUB"
    if cleaned in {"USD", "$"}:
        return "USD"
    if cleaned in {"EUR", "€"}:
        return "EUR"
    return cleaned if len(cleaned) == 3 else None


def _detect_currency_from_text(raw_text: str) -> str | None:
    lowered = raw_text.lower()
    if "₽" in raw_text or " руб" in lowered or "rur" in lowered or "rub" in lowered:
        return "RUB"
    if "$" in raw_text or "usd" in lowered:
        return "USD"
    if "€" in raw_text or "eur" in lowered:
        return "EUR"
    return None


def _normalize_url(base_url: str, maybe_relative: str | None) -> str | None:
    if maybe_relative is None:
        return None
    trimmed = maybe_relative.strip()
    if not trimmed:
        return None
    return urljoin(base_url, trimmed)


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    segment = unquote(parsed.path.rstrip("/").split("/")[-1] if parsed.path else "").strip()
    cleaned = re.sub(r"[-_]+", " ", segment)
    cleaned = re.sub(r"\.[a-zA-Z0-9]{2,5}$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) >= 3:
        return cleaned[:160]
    return parsed.netloc


def _decode_json_string(raw: str) -> str | None:
    try:
        return json.loads(f"\"{raw}\"")
    except json.JSONDecodeError:
        return None


def _price_to_cents(raw_price: str | float | int | Decimal | None, *, minor_units: bool = False) -> int | None:
    if raw_price is None:
        return None

    if isinstance(raw_price, Decimal):
        value = raw_price
    elif isinstance(raw_price, (int, float)):
        value = Decimal(str(raw_price))
    else:
        text = str(raw_price).strip().replace("\u00a0", " ")
        if not text:
            return None
        match = PRICE_PATTERN.search(text)
        if not match:
            return None
        normalized = re.sub(r"\s+", "", match.group(1)).replace(",", ".")
        try:
            value = Decimal(normalized)
        except (InvalidOperation, ValueError):
            return None

    if value < 0:
        return None
    if minor_units:
        return int(value)
    return int(value * 100)


def _is_reasonable_price(cents: int | None) -> bool:
    return cents is not None and 50 <= cents <= 500_000_000


def _find_meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        for key in ("property", "name", "itemprop"):
            tag = soup.find("meta", attrs={key: name})
            if tag and tag.get("content"):
                value = str(tag.get("content")).strip()
                if value:
                    return value
    return None


def _parse_json_ld_payloads(soup: BeautifulSoup) -> list[Any]:
    payloads: list[Any] = []
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in scripts:
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payloads.append(json.loads(raw))
        except json.JSONDecodeError:
            continue
    return payloads


def _walk_json(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_json(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk_json(value)


def _extract_from_json_ld(soup: BeautifulSoup, base_url: str) -> tuple[str | None, str | None, int | None, str | None]:
    title: str | None = None
    image_url: str | None = None
    price_cents: int | None = None
    currency: str | None = None

    for payload in _parse_json_ld_payloads(soup):
        for node in _walk_json(payload):
            if not isinstance(node, dict):
                continue

            if title is None:
                for title_key in ("name", "title", "productName", "wareName"):
                    value = node.get(title_key)
                    if isinstance(value, str) and value.strip():
                        title = value.strip()
                        break

            if image_url is None:
                image_value = node.get("image") or node.get("picture")
                candidate_image: str | None = None
                if isinstance(image_value, str):
                    candidate_image = image_value
                elif isinstance(image_value, list):
                    first = next((item for item in image_value if isinstance(item, str) and item.strip()), None)
                    candidate_image = first
                elif isinstance(image_value, dict):
                    url_value = image_value.get("url")
                    if isinstance(url_value, str):
                        candidate_image = url_value
                image_url = _normalize_url(base_url, candidate_image) or image_url

            if price_cents is None:
                price_obj = node.get("price")
                if isinstance(price_obj, dict):
                    price_candidate = price_obj.get("value") or price_obj.get("amount") or price_obj.get("price")
                    cents = _price_to_cents(price_candidate)
                    if _is_reasonable_price(cents):
                        price_cents = cents
                        currency = _normalize_currency(price_obj.get("currency") or price_obj.get("currencyCode")) or currency
                else:
                    cents = _price_to_cents(price_obj)
                    if _is_reasonable_price(cents):
                        price_cents = cents

            if price_cents is None:
                offers = node.get("offers")
                offers_list = offers if isinstance(offers, list) else [offers]
                for offer in offers_list:
                    if not isinstance(offer, dict):
                        continue
                    cents = _price_to_cents(offer.get("price"))
                    if _is_reasonable_price(cents):
                        price_cents = cents
                        currency = _normalize_currency(offer.get("priceCurrency")) or currency
                        break

            if price_cents is None:
                sale_price_u = node.get("salePriceU") or node.get("priceU")
                cents = _price_to_cents(sale_price_u, minor_units=True)
                if _is_reasonable_price(cents):
                    price_cents = cents
                    currency = currency or "RUB"

            if title and image_url and price_cents is not None:
                return title, image_url, price_cents, currency

    return title, image_url, price_cents, currency


def _extract_from_raw_text(raw_text: str, host_family: str, base_url: str) -> tuple[str | None, str | None, int | None, str | None]:
    title: str | None = None
    image_url: str | None = None
    price_cents: int | None = None
    currency: str | None = None

    price_patterns: list[tuple[re.Pattern[str], bool, int, int | None]] = [
        (
            re.compile(r'"price"\s*:\s*\{\s*"value"\s*:\s*([0-9]+(?:[.,][0-9]{1,2})?)\s*,\s*"currency"\s*:\s*"([A-Za-z$€₽]{1,5})"', re.I),
            False,
            1,
            2,
        ),
        (re.compile(r'"(?:salePriceU|priceU)"\s*:\s*([0-9]{3,12})', re.I), True, 1, None),
        (re.compile(r'"(?:finalPrice|currentPrice|priceValue|salePrice|price)"\s*:\s*"([0-9]+(?:[.,][0-9]{1,2})?)"', re.I), False, 1, None),
        (re.compile(r'([0-9][0-9\s]{2,10}(?:[.,][0-9]{1,2})?)\s*(?:₽|руб\.?|RUB|RUR)', re.I), False, 1, None),
    ]

    for pattern, is_minor_units, price_group, currency_group in price_patterns:
        match = pattern.search(raw_text)
        if not match:
            continue
        cents = _price_to_cents(match.group(price_group), minor_units=is_minor_units)
        if not _is_reasonable_price(cents):
            continue
        price_cents = cents
        if currency_group and match.lastindex and match.lastindex >= currency_group:
            currency = _normalize_currency(match.group(currency_group))
        break

    if currency is None:
        currency_match = re.search(r'"(?:currency|currencyCode|priceCurrency)"\s*:\s*"([A-Za-z$€₽]{1,5})"', raw_text, re.I)
        if currency_match:
            currency = _normalize_currency(currency_match.group(1))

    image_pattern = re.compile(r'"(?:picture|image|imageUrl|photoUrl|previewPicture)"\s*:\s*"' + JSON_STRING_RE + r'"', re.I)
    image_candidates: list[str] = []
    for image_match in image_pattern.finditer(raw_text):
        decoded = _decode_json_string(image_match.group(1))
        normalized = _normalize_url(base_url, decoded)
        if normalized:
            image_candidates.append(normalized)

    unescaped_raw_text = raw_text.replace("\\/", "/")
    absolute_image_patterns = [
        re.compile(r'https://avatars\.mds\.yandex\.net/get-[^"\s<>]+', re.I),
        re.compile(r'https://[^"\s<>]+(?:\.jpe?g|\.png|\.webp)(?:\?[^"\s<>]*)?', re.I),
        re.compile(r'https://[^"\s<>]+/orig(?:\?[^"\s<>]*)?', re.I),
    ]
    for pattern in absolute_image_patterns:
        absolute_match = pattern.search(unescaped_raw_text)
        if absolute_match:
            image_candidates.append(absolute_match.group(0))
            break

    if image_candidates:
        def image_score(url: str) -> int:
            lowered = url.lower()
            score = 0
            if lowered.startswith("http"):
                score += 2
            if any(token in lowered for token in ("avatar", "cdn", "wbstatic", "ozone", "images", "market.yandex")):
                score += 2
            if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", lowered):
                score += 2
            if "/card/" in lowered and "/mi_" in lowered:
                score -= 1
            return score

        image_url = max(image_candidates, key=image_score)

    title_patterns = [
        re.compile(r'"wareName"\s*:\s*"' + JSON_STRING_RE + r'"', re.I),
        re.compile(r'"productName"\s*:\s*"' + JSON_STRING_RE + r'"', re.I),
        re.compile(r'"title"\s*:\s*"' + JSON_STRING_RE + r'"', re.I),
        re.compile(r'"name"\s*:\s*"' + JSON_STRING_RE + r'"', re.I),
    ]
    if host_family == "yandex_market":
        title_patterns = title_patterns
    elif host_family in {"ozon", "wb", "megamarket"}:
        title_patterns = title_patterns[1:]

    for pattern in title_patterns:
        title_match = pattern.search(raw_text)
        if not title_match:
            continue
        decoded_title = _decode_json_string(title_match.group(1))
        if decoded_title and 4 <= len(decoded_title.strip()) <= 220:
            title = decoded_title.strip()
            break

    return title, image_url, price_cents, currency


def _extract_from_yandex_dom(soup: BeautifulSoup, base_url: str) -> tuple[str | None, str | None, int | None, str | None]:
    title: str | None = None
    heading = soup.find("h1")
    if heading is not None:
        heading_text = heading.get_text(" ", strip=True)
        if heading_text and heading_text.lower() not in {"яндекс", "яндекс маркет"}:
            title = heading_text

    price_cents: int | None = None
    price_candidates: list[int] = []
    for node in soup.select('[data-auto="snippet-price-current"]'):
        text = node.get_text(" ", strip=True)
        candidate = _price_to_cents(text)
        if _is_reasonable_price(candidate):
            price_candidates.append(candidate)
    if price_candidates:
        price_cents = min(price_candidates)

    image_url: str | None = None
    image_candidates: list[tuple[int, str]] = []
    for img in soup.find_all("img"):
        raw_src = img.get("src") or img.get("data-src")
        if not isinstance(raw_src, str):
            continue
        if raw_src.startswith("//"):
            raw_src = f"https:{raw_src}"
        normalized = _normalize_url(base_url, raw_src)
        if normalized is None:
            continue

        lowered = normalized.lower()
        if any(
            blocked in lowered
            for blocked in ("marketcms", "qrcode", "barcode.yandex.net", ".svg", "favicon", "adfstat")
        ):
            continue

        alt = str(img.get("alt") or "").strip()
        score = 0
        if "avatars.mds.yandex.net/get-mpic/" in lowered:
            score += 3
        if "/orig" in lowered:
            score += 2
        if title and alt:
            title_tokens = {token for token in re.findall(r"[A-Za-zА-Яа-я0-9]+", title.lower()) if len(token) >= 3}
            alt_tokens = {token for token in re.findall(r"[A-Za-zА-Яа-я0-9]+", alt.lower()) if len(token) >= 3}
            score += min(len(title_tokens & alt_tokens), 5)
        elif alt:
            score += 1
        image_candidates.append((score, normalized))

    if image_candidates:
        image_url = max(image_candidates, key=lambda row: row[0])[1]
        image_url = re.sub(r"/[0-9]{2,4}x[0-9]{2,4}(?=$|[/?#])", "/orig", image_url)

    currency = "RUB" if price_cents is not None else None
    return title, image_url, price_cents, currency


def _cleanup_title(title: str, host_family: str) -> str:
    cleaned = title.strip()
    if host_family == "ozon":
        cleaned = re.sub(r"\s+купить\b.*\bozon\b.*$", "", cleaned, flags=re.I).strip()
        cleaned = re.sub(r"\s+\([0-9]{7,12}\)\s*$", "", cleaned).strip()
    return cleaned


def _looks_like_block_page(raw_text: str) -> bool:
    lowered = raw_text.lower()
    markers = [
        "antibot challenge",
        "доступ ограничен",
        "почти готово",
        "showcaptcha",
        "captcha",
        "servicepipe",
        "incident",
        "bot protection",
        "access denied",
    ]
    return any(marker in lowered for marker in markers)


def _looks_like_blocked_title(title: str | None) -> bool:
    if not title:
        return False
    lowered = title.lower().strip()
    if lowered in {"яндекс", "яндекс маркет"}:
        return True
    blocked_fragments = [
        "доступ ограничен",
        "antibot challenge",
        "почти готово",
        "access denied",
        "captcha",
    ]
    return any(fragment in lowered for fragment in blocked_fragments)


def _looks_like_blocked_image(image_url: str | None) -> bool:
    if not image_url:
        return False
    lowered = image_url.lower()
    blocked_fragments = [
        "abt-complaints",
        "warn.png",
        "captcha",
        "servicepipe",
        "default.gif",
    ]
    return any(fragment in lowered for fragment in blocked_fragments)


async def _fetch_best_response(url: str, *, cookies: dict[str, str] | None = None) -> FetchedPage:
    last_exc: httpx.HTTPError | None = None
    response: httpx.Response | None = None
    best_score = -1
    async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, cookies=cookies or None) as client:
        for headers in REQUEST_HEADERS:
            try:
                candidate = await client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                last_exc = exc
                continue
            score = 0
            if candidate.status_code < 400:
                score += 1
            if not _looks_like_block_page(candidate.text):
                score += 1
            if score > best_score:
                response = candidate
                best_score = score
            if score >= 2:
                break
    if response is None:
        if last_exc is not None:
            raise last_exc
        raise httpx.HTTPError("Unable to fetch URL")
    return FetchedPage(status_code=response.status_code, url=str(response.url), text=response.text)


async def _fetch_yandex_with_curl(url: str) -> FetchedPage | None:
    if curl_requests is None:
        return None

    def _run_sync() -> Any:
        return curl_requests.get(
            url,
            impersonate="chrome124",
            timeout=25,
            allow_redirects=True,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )

    try:
        raw_response = await asyncio.to_thread(_run_sync)
    except Exception:
        return None

    return FetchedPage(status_code=int(raw_response.status_code), url=str(raw_response.url), text=str(raw_response.text))


def _is_meaningful_result(title: str | None, image_url: str | None, price_cents: int | None, fallback_title: str) -> bool:
    if price_cents is not None:
        return True
    if image_url is not None and not _looks_like_blocked_image(image_url):
        return True
    if title and title.strip() and title.strip() != fallback_title and not _looks_like_blocked_title(title):
        return True
    return False


async def extract_product_metadata(url: str, *, _allow_yandex_mirror: bool = True) -> dict[str, Any]:
    host_family = _host_family(url)

    if host_family == "wb":
        wb_result = await _extract_wb_from_basket(url)
        if wb_result is not None:
            return wb_result

    request_url = url
    if host_family == "yandex_market" and _allow_yandex_mirror:
        request_url = _to_yandex_integration_url(url)

    browser_cookies: dict[str, str] = {}
    if host_family in {"ozon", "yandex_market"}:
        browser_cookies = _browser_cookies_for_url(request_url)

    response: FetchedPage | None = None
    if host_family == "yandex_market":
        curl_page = await _fetch_yandex_with_curl(request_url)
        if curl_page is not None and (curl_page.status_code == 200 or not _looks_like_block_page(curl_page.text)):
            response = curl_page

    if response is None and browser_cookies:
        cookie_response = await _fetch_best_response(request_url, cookies=browser_cookies)
        if cookie_response.status_code == 200 and not _looks_like_block_page(cookie_response.text):
            response = cookie_response

    if response is None:
        response = await _fetch_best_response(request_url)

    source_url = url if host_family in {"ozon", "yandex_market"} else response.url
    host_family = _host_family(source_url)

    raw_text = response.text
    soup = BeautifulSoup(raw_text, "lxml")

    fallback_title = _title_from_url(source_url)

    title = _find_meta_content(soup, "og:title", "twitter:title")
    if title is None:
        heading = soup.find("h1")
        if heading:
            heading_text = heading.get_text(strip=True)
            title = heading_text if heading_text else None
    if title is None:
        title_tag = soup.find("title")
        if title_tag:
            raw_title = title_tag.get_text(strip=True)
            if raw_title:
                title = re.sub(r"\s*[|\-]\s*.*$", "", raw_title).strip() or raw_title

    image_url = _normalize_url(source_url, _find_meta_content(soup, "og:image", "twitter:image", "image"))

    price_cents = _price_to_cents(_find_meta_content(soup, "product:price:amount", "price", "price:amount"))
    currency = _normalize_currency(_find_meta_content(soup, "product:price:currency", "priceCurrency"))

    if price_cents is None:
        itemprop_price = soup.find(attrs={"itemprop": "price"})
        if itemprop_price is not None:
            attr_content = itemprop_price.get("content") or itemprop_price.get_text(strip=True)
            candidate = _price_to_cents(attr_content)
            if _is_reasonable_price(candidate):
                price_cents = candidate

    if currency is None:
        itemprop_currency = soup.find(attrs={"itemprop": "priceCurrency"})
        if itemprop_currency is not None:
            attr_content = itemprop_currency.get("content") or itemprop_currency.get_text(strip=True)
            currency = _normalize_currency(str(attr_content)) if attr_content is not None else None

    json_ld_title, json_ld_image, json_ld_price, json_ld_currency = _extract_from_json_ld(soup, source_url)
    title = title or json_ld_title
    if json_ld_image and (image_url is None or not image_url.startswith("http")):
        image_url = json_ld_image
    if price_cents is None and _is_reasonable_price(json_ld_price):
        price_cents = json_ld_price
    currency = currency or _normalize_currency(json_ld_currency)

    text_title, text_image, text_price, text_currency = _extract_from_raw_text(raw_text, host_family, source_url)
    title = title or text_title
    if text_image and (image_url is None or not image_url.startswith("http")):
        image_url = text_image
    if price_cents is None and _is_reasonable_price(text_price):
        price_cents = text_price
    currency = currency or _normalize_currency(text_currency)

    if host_family == "yandex_market":
        y_title, y_image, y_price, y_currency = _extract_from_yandex_dom(soup, source_url)
        if y_title:
            title = y_title
        if y_image:
            image_url = y_image
        if _is_reasonable_price(y_price):
            price_cents = y_price
        currency = currency or y_currency

    if currency is None and price_cents is not None:
        currency = _detect_currency_from_text(raw_text)
    if currency is None and host_family in {"ozon", "wb", "yandex_market", "megamarket"} and price_cents is not None:
        currency = "RUB"

    if title is None:
        title = fallback_title
    else:
        title = _cleanup_title(title, host_family)

    lacks_rich_data = (price_cents is None and (image_url is None or _looks_like_blocked_image(image_url))) or _looks_like_blocked_title(title)
    if host_family == "yandex_market" and _allow_yandex_mirror and lacks_rich_data:
        mirror_url = _to_yandex_integration_url(url)
        if mirror_url != url:
            try:
                mirror_metadata = await extract_product_metadata(mirror_url, _allow_yandex_mirror=False)
                mirror_metadata["source_url"] = url
                return mirror_metadata
            except MetadataExtractionError:
                pass

    if _looks_like_block_page(raw_text) and price_cents is None and (image_url is None or _looks_like_blocked_image(image_url)):
        raise MetadataExtractionError(
            "Извините, сайт заблокировал автоматическое чтение карточки товара. Попробуйте другую ссылку или заполните поля вручную."
        )

    if not _is_meaningful_result(title, image_url, price_cents, fallback_title):
        if response.status_code in BLOCKED_STATUSES or _looks_like_block_page(raw_text):
            raise MetadataExtractionError(
                "Извините, сайт заблокировал автоматическое чтение карточки товара. Попробуйте другую ссылку или заполните поля вручную."
            )
        raise MetadataExtractionError(
            "Извините, не удалось автоматически извлечь название, фото и цену. Заполните поля вручную."
        )

    if response.status_code >= 400 and response.status_code not in BLOCKED_STATUSES:
        raise MetadataExtractionError(
            f"Извините, не удалось получить данные со страницы (код {response.status_code}). Попробуйте другую ссылку."
        )

    return {
        "source_url": source_url,
        "title": title,
        "image_url": image_url,
        "price_cents": price_cents,
        "currency": currency,
    }

