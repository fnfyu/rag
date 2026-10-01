"""Official Souls source discovery and bounded, explicit captures (no persistence).

Call sources_for, preview fetch_updates, then choose one fetch_article to import.
Default updates use Steam's publisher announcements only, not its partner news.
Failures raise SourceError with the affected URL; callers decide how to display them.
BeautifulSoup is already installed in the project environment; network uses urllib.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

__all__ = ["sources_for", "fetch_updates", "fetch_article", "SourceError"]
_TIMEOUT = 20
_MAX_BYTES = 4 * 1024 * 1024
_APPS = {
    "elden-ring": [(1245620, "standard", "ELDEN RING")],
    "nightreign": [(2622380, "standard", "ELDEN RING NIGHTREIGN")],
    "dark-souls-1": [(570940, "remastered", "DARK SOULS: REMASTERED")],
    "dark-souls-2": [(335300, "scholar", "DARK SOULS II: Scholar of the First Sin"),
                     (236430, "standard", "DARK SOULS II")],
    "dark-souls-3": [(374320, "standard", "DARK SOULS III")],
}
# Semantic gameplay DLC labels; purchase bundles/season passes are not separate areas.
_DLC = {
    "elden-ring": [("shadow-of-the-erdtree", "Shadow of the Erdtree", 2778580),
                   ("tarnished-pack", "Tarnished Pack", 3655690)],
    "nightreign": [("the-forsaken-hollows", "The Forsaken Hollows", 3531720)],
    "dark-souls-1": [("artorias-of-the-abyss", "Artorias of the Abyss", None)],
    "dark-souls-2": [("crown-of-the-sunken-king", "Crown of the Sunken King", 271942),
                     ("crown-of-the-old-iron-king", "Crown of the Old Iron King", 271943),
                     ("crown-of-the-ivory-king", "Crown of the Ivory King", 271944)],
    "dark-souls-3": [("ashes-of-ariandel", "Ashes of Ariandel", 506970),
                     ("the-ringed-city", "The Ringed City", 506971)],
}
_BANDAI_PATCH = "https://en.bandainamcoent.eu/elden-ring/news/elden-ring-nightreign-patch-notes-version-1031"


class SourceError(ValueError):
    """Unsupported identity, inaccessible source, or unusable primary content."""


def _game(game_id):
    if game_id not in _APPS:
        raise SourceError(f"Unknown game_id: {game_id}")
    return _APPS[game_id]


def _news_url(app_id, count):
    return "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?" + urlencode(
        {"appid": app_id, "count": count, "maxlength": 0,
         "feeds": "steam_community_announcements", "format": "json"})


def sources_for(game_id: str) -> list[dict]:
    """Return fresh source descriptors. DS1 original has no enabled current feed."""
    result = []
    for app_id, edition, title in _game(game_id):
        note = "Publisher-owned Steam announcements; excludes external partner feeds."
        if game_id == "dark-souls-2":
            note += " App identity determines edition; shared/cross-edition notices need manual review."
        result.extend([
            {"id": f"steam-news-{app_id}", "game_id": game_id, "title": title + " — official announcements",
             "url": _news_url(app_id, 10), "kind": "steam_news", "tier": "official",
             "app_id": app_id, "edition": edition, "notes": note},
            {"id": f"steam-product-{app_id}", "game_id": game_id, "title": title + " — product reference",
             "url": f"https://store.steampowered.com/app/{app_id}/?l=english",
             "kind": "publisher_page", "tier": "official", "app_id": app_id,
             "edition": edition, "notes": "Captures publisher-written detailed_description via Steam appdetails; not patch notes. Publication date unknown."},
        ])
    if game_id == "dark-souls-1":
        result.append({"id": "steam-product-211420", "game_id": game_id,
                       "title": "DARK SOULS: Prepare To Die Edition — historical product reference",
                       "url": "https://store.steampowered.com/app/211420/?l=english",
                       "kind": "publisher_page", "tier": "official", "app_id": 211420,
                       "edition": "original", "notes": "Original PC Prepare To Die edition; live appdetails historical text verified. No claim of active patch/support channel."})
    if game_id == "nightreign":
        result.append({"id": "bandai-nightreign-1031", "game_id": game_id,
                       "title": "NIGHTREIGN — historical patch 1.03.1 (not latest claim)",
                       "url": _BANDAI_PATCH, "kind": "publisher_page", "tier": "official",
                       "edition": "standard", "notes": "Verified game-specific publisher article; no wiki crawl."})
    return copy.deepcopy(result)


def _get(url):
    request = Request(url, headers={"User-Agent": "SoulsOfficialSources/3.0", "Accept-Language": "en"})
    try:
        with urlopen(request, timeout=_TIMEOUT) as response:
            final = response.geturl()
            # Never follow a trusted URL to an unrelated host without noticing.
            if urlsplit(final).hostname != urlsplit(url).hostname:
                raise SourceError(f"Unexpected redirect for {url}: {final}")
            body = response.read(_MAX_BYTES + 1)
            if len(body) > _MAX_BYTES:
                raise SourceError(f"Response exceeds {_MAX_BYTES} bytes: {url}")
            return body.decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    except HTTPError as exc:
        raise SourceError(f"Official source HTTP {exc.code}: {url}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise SourceError(f"Official source unavailable: {url}: {exc}") from exc


def _json(url):
    try:
        return json.loads(_get(url))
    except json.JSONDecodeError as exc:
        raise SourceError(f"Invalid source JSON: {url}") from exc


def _text(markup, base_url):
    soup = BeautifulSoup(markup, "html.parser")
    for node in soup.select("script,style,nav,header,footer,aside,form,video,iframe"):
        node.decompose()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor["href"])
        if urlsplit(href).scheme in ("http", "https"):
            anchor.replace_with(f"{anchor.get_text(' ', strip=True)} ({href})")
    for node in soup.find_all(["br", "p", "div", "li", "h1", "h2", "h3", "h4"]):
        node.insert_before("\n")
        if node.name != "br":
            node.insert_after("\n")
    return "\n".join(line.strip() for line in soup.get_text().splitlines() if line.strip())


def _bbcode(content, url):
    # Protect URLs first: do not destroy anchors when stripping BBCode syntax.
    content = re.sub(r'\[url=([^\]]+)\](.*?)\[/url\]',
                     lambda m: f"{m[2]} ({m[1].strip(chr(34))})", content, flags=re.S | re.I)
    content = re.sub(r'\[url\](.*?)\[/url\]', lambda m: m[1], content, flags=re.S | re.I)
    content = re.sub(r'\[img(?:\s[^\]]*)?\].*?\[/img\]', '', content, flags=re.S | re.I)
    content = re.sub(r'\[(?:previewyoutube|youtube)[^\]]*\].*?\[/(?:previewyoutube|youtube)\]', '', content, flags=re.S | re.I)
    content = re.sub(r'\[/?(?:p|h[1-6]|list|olist|\*)\]', '\n', content, flags=re.I)
    content = re.sub(r'\[(?:/?(?:b|i|u|s|quote|spoiler|table|tr|td|th)|/\*)\]', '', content, flags=re.I)
    # Unrecognised tags and escaped [Character] text remain; avoid swallowing real text.
    return _text(content, url)


def _identity(game_id, title):
    normalized = re.sub(r"[™®]", "", title).upper()
    if game_id == "elden-ring":
        return "ELDEN RING" in normalized and "NIGHTREIGN" not in normalized
    if game_id == "nightreign":
        return "NIGHTREIGN" in normalized
    if game_id == "dark-souls-1":
        return "DARK SOULS" in normalized and not re.search(r"DARK SOULS\s+(?:II|2|III|3)\b", normalized)
    if game_id == "dark-souls-2":
        return bool(re.search(r"DARK SOULS\s+(?:II|2)\b", normalized))
    return bool(re.search(r"DARK SOULS\s+(?:III|3)\b", normalized))


def _patch(title, content):
    # A previous version mentioned in the body is not this article's patch version.
    explicit = r"(?:patch(?:\s+notes)?|hotfix(?:\s+notes)?|update(?:\s+notes)?|app)\s*(?:version|ver\.?|v)?\s*[:：-]?\s*(\d+\.\d+(?:\.\d+){0,2})"
    match = re.search(explicit, title, re.I)
    if not match:
        match = re.search(r"\bApp\s+Ver\.?\s*(\d+\.\d+(?:\.\d+){0,2})", content, re.I)
    return match[1] if match else None


def _article(game_id, source, title, url, content, published=None, external_id=None,
             provenance="verified_capture", raw_content=None, source_url=None):
    if not content.strip():
        raise SourceError(f"No primary content: {url}")
    patch = _patch(title, content)
    edition = source.get("edition")
    notes = None
    if game_id == "dark-souls-2" and source["kind"] == "steam_news":
        # Publisher sometimes posts a shared announcement on both applications.
        if "scholar" in title.lower() and edition == "standard":
            edition = None
            notes = "Scholar title on standard app feed; applicability requires manual edition review."
        elif ("scholar" in title.lower() and re.search(r"(?:\band\b|&|/|\+)", title, re.I)):
            edition = None
            notes = "Cross-edition announcement; applicability requires manual review."
    return {"external_id": external_id or hashlib.sha256(url.encode()).hexdigest(),
            "game_id": game_id, "title": title, "url": url, "source_url": source_url or url,
            "published_at": published, "captured_at": datetime.now(timezone.utc).isoformat(),
            "patch": patch, "edition": edition, "content": content,
            "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "source_id": source["id"], "source_tier": "official",
            "source_kind": "patch_notes" if patch and re.search(r"patch|hotfix|update", title, re.I) else "reference",
            "provenance": provenance, "requires_dlc": [],
            "mentioned_dlc": [key for key, name, _ in _DLC[game_id] if name.lower() in content.lower()],
            "edition_notes": notes, "raw_content": raw_content}


def _feed(game_id, source, count):
    endpoint = _news_url(source["app_id"], count)
    appnews = _json(endpoint).get("appnews", {})
    if appnews.get("appid") != source["app_id"]:
        raise SourceError(f"Steam app identity mismatch: {endpoint}")
    result = []
    for item in appnews.get("newsitems", []):
        if (item.get("feedname") != "steam_community_announcements"
                or item.get("feed_type") != 1 or item.get("appid") != source["app_id"]):
            continue
        # An app's own publisher feed also advertises its OTHER games. Ownership
        # of the feed proves official authorship, not that every item belongs here.
        title = item.get("title", "")
        if not _identity(game_id, title) and any(
                _identity(other, title) for other in _APPS if other != game_id):
            continue
        url = item.get("url", "")
        parsed = urlsplit(url)
        trusted_url = (parsed.hostname in {"steamstore-a.akamaihd.net", "store.steampowered.com", "steamcommunity.com"}
                       and ("/steam_community_announcements/" in parsed.path
                            or re.search(r"/(?:news/app|app)/" + str(source["app_id"]) + r"/", parsed.path)))
        if not trusted_url:
            continue
        raw = item.get("contents", "")
        published = datetime.fromtimestamp(item["date"], timezone.utc).isoformat() if item.get("date") else None
        result.append(_article(game_id, source, item["title"], url, _bbcode(raw, url),
                               published, str(item["gid"]), "feed_capture", raw, endpoint))
    return result


def fetch_updates(game_id: str, source_id: str | None = None, limit: int = 10) -> list[dict]:
    """Newest bounded feed captures for preview, not exhaustive patch history.

    With an explicit publisher_page source returns its one reference capture.
    On source failure raises SourceError; never substitutes community content.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise SourceError("limit must be an integer between 1 and 100")
    sources = sources_for(game_id)
    chosen = [s for s in sources if s["id"] == source_id] if source_id else [s for s in sources if s["kind"] == "steam_news"]
    if not chosen:
        raise SourceError(f"Unknown source_id for {game_id}: {source_id}")
    result = []
    for source in chosen:
        result.extend(_feed(game_id, source, min(100, max(20, limit * 5))) if source["kind"] == "steam_news"
                      else [fetch_article(game_id, source["url"], edition=source.get("edition"))])
    return sorted(result, key=lambda x: x["published_at"] or "", reverse=True)[:limit]


def fetch_article(game_id: str, url: str, *, edition: str | None = None) -> dict:
    """Capture a registered product/article or a genuine recent Steam announcement.

    Generic official-domain URLs are rejected. Steam announcement selection is
    verified by exact gid/URL membership in at most 100 app announcements.
    Unknown publication times remain None (product release dates are not article dates).
    """
    sources = sources_for(game_id)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SourceError(f"Only registered HTTPS official links are accepted: {url}")
    app_match = re.fullmatch(r"/app/(\d+)(?:/[^/]*)?/?", parsed.path)
    query = parse_qs(parsed.query)
    api_match = parsed.hostname == "store.steampowered.com" and parsed.path == "/api/appdetails"
    app_id = int(app_match[1]) if app_match and parsed.hostname == "store.steampowered.com" else None
    if api_match and len(query.get("appids", [])) == 1 and query["appids"][0].isdigit():
        app_id = int(query["appids"][0])
    if app_id is not None:
        source = next((s for s in sources if s["id"] == f"steam-product-{app_id}"), None)
        if not source:
            raise SourceError(f"Steam app {app_id} does not correspond to {game_id}")
        if edition is not None and edition != source["edition"]:
            raise SourceError(f"Edition {edition} does not match app {app_id} ({source['edition']})")
        endpoint = "https://store.steampowered.com/api/appdetails?" + urlencode({"appids": app_id, "l": "english"})
        entry = _json(endpoint).get(str(app_id), {})
        data = entry.get("data", {})
        if not entry.get("success") or data.get("steam_appid") != app_id or not _identity(game_id, data.get("name", "")):
            raise SourceError(f"Steam product identity not verified: {endpoint}")
        raw = data.get("detailed_description", "")
        return _article(game_id, source, data["name"], source["url"], _text(raw, source["url"]),
                        external_id=f"steam-product-{app_id}", raw_content=raw, source_url=endpoint)
    source = next((s for s in sources if s["kind"] == "publisher_page" and s["url"] == url), None)
    if source:
        if edition is not None and edition != source["edition"]:
            raise SourceError(f"Edition mismatch for {url}")
        raw = _get(url)
        soup = BeautifulSoup(raw, "html.parser")
        heading = soup.select_one("article h1")
        body = soup.select_one("article .article__edito-content")
        timestamp = soup.select_one("article time[datetime]")
        if not heading or not body or not _identity(game_id, heading.get_text(" ", strip=True)):
            raise SourceError(f"Official article game/body identity not verified: {url}")
        published = timestamp.get("datetime") if timestamp else None
        return _article(game_id, source, heading.get_text(" ", strip=True), url, _text(str(body), url),
                        published, raw_content=str(body))
    if parsed.hostname in {"steamstore-a.akamaihd.net", "store.steampowered.com", "steamcommunity.com"}:
        gid = re.search(r"/(?:detail|view|steam_community_announcements)/(\d+)/?$", parsed.path)
        if gid:
            for source in sources:
                if source["kind"] != "steam_news" or (edition is not None and source["edition"] != edition):
                    continue
                for item in _feed(game_id, source, 100):
                    if item["external_id"] == gid[1]:
                        # Exact feed URL, or app-scoped Steam news alias; never arbitrary shared-domain paths.
                        valid_alias = bool(re.fullmatch(r"/news/app/" + str(source["app_id"]) + r"/view/" + gid[1] + r"/?", parsed.path))
                        if url == item["url"] or valid_alias:
                            return item
    raise SourceError(f"Link is not a verified registered official source for {game_id}: {url}")
