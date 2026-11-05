"""Check three sources for Trafigura news and push new headlines to Telegram.

Sources: the Google News RSS search (news.google.com), the GDELT DOC API
(api.gdeltproject.org) and the press release page on trafigura.com. Standard library only. State lives in seen.json (committed back by the workflow).
Env vars required: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

KEYWORDS = [
    "Trafigura",
    "Trafigura Group",
    "TFG Marine",
    "Impala Terminals",
    "Nyrstar",
    "Puma Energy",
    "Volare Shipping",
]
LEGAL_TERMS = ["lawsuit", "sanctions", "fine", "penalty", "investigation", "court"]
SITES = [
    "reuters.com",
    "ft.com",
    "bloomberg.com",
    "spglobal.com",
    "argusmedia.com",
    "mining.com",
    "straitstimes.com",
    "shipandbunker.com",
    "splash247.com",
    "lloydslist.com",
    "trafigura.com",
]
PRESS_FEED_ENABLED = True  # Trafigura's own press release page
GDELT_FEED_ENABLED = True  # GDELT DOC API keyword search
PRESS_URL = "https://www.trafigura.com/news-and-insights/press-releases/"
SIMILARITY = 0.6  # word overlap (0-1) above which two headlines count as the same story
STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "has", "are", "its"}
SEEN_FILE = Path("seen.json")
MAX_SEEN = 600   # keys kept (two per article)
MAX_SEND = 10    # cap per run so a backlog cannot flood the chat


def feed_url():
    sites = " OR ".join(f"site:{s}" for s in SITES)
    legal = " OR ".join(LEGAL_TERMS)
    terms = " OR ".join(f'"{k}"' for k in KEYWORDS) + f" OR (Trafigura ({legal}))"
    params = urllib.parse.urlencode(
        {"q": f"({terms}) ({sites}) when:2d", "hl": "en-SG", "gl": "SG", "ceid": "SG:en"}
    )
    return "https://news.google.com/rss/search?" + params


def http(url, data=None):
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "Mozilla/5.0 (news-notifier)"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def is_relevant(title):
    """Google matches the whole page, including "related stories" links, so require a keyword in the headline."""
    t = title.lower()
    return any(k.lower() in t for k in KEYWORDS)


def fetch_news_items():
    """One request to news.google.com/rss/search with all keywords and sites in a single query."""
    root = ET.fromstring(http(feed_url()))
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link).strip()
        src = it.find("source")
        source = src.text.strip() if src is not None and src.text else ""
        if title and link and is_relevant(title):
            items.append({"title": title, "link": link, "guid": guid, "source": source})
    return items


PRESS_LINK = re.compile(
    r'<a\b[^>]*?href="([^"#?]*/press-releases/\d{4}/([a-z0-9-]+)/?)"[^>]*>(.*?)</a>',
    re.S | re.I,
)


def fetch_press_items():
    """Scrape press release links from trafigura.com (no RSS feed is known)."""
    page = http(PRESS_URL).decode("utf-8", "replace")
    found = {}
    for href, slug, inner in PRESS_LINK.findall(page):
        link = urllib.parse.urljoin(PRESS_URL, href)
        text = html.unescape(re.sub(r"<[^>]+>", " ", inner))
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 20:  # "Read more", a date, etc.: fall back to the URL slug
            text = slug.replace("-", " ").capitalize()
        if link not in found or len(text) > len(found[link]):
            found[link] = text
    if not found:
        raise RuntimeError("no press release links found (page layout changed?)")
    return [
        {"title": t, "link": l, "guid": "tf:" + l, "source": "trafigura.com"}
        for l, t in found.items()
    ]


def fetch_gdelt_items():
    """One request to the GDELT DOC 2.0 API: all keywords OR'd, English only, last 2 days, newest first."""
    query = "(" + " OR ".join(f'"{k}"' for k in KEYWORDS) + ") sourcelang:english"
    params = urllib.parse.urlencode(
        {"query": query, "mode": "ArtList", "format": "json", "timespan": "2d",
         "maxrecords": "75", "sort": "datedesc"}
    )
    body = http("https://api.gdeltproject.org/api/v2/doc/doc?" + params).decode("utf-8", "replace")
    if not body.strip():
        return []  # GDELT answers an empty body when nothing matches
    try:
        articles = json.loads(body).get("articles", [])
    except ValueError:
        raise RuntimeError(f"unexpected reply: {body.strip()[:120]!r}") from None
    items = []
    for a in articles:
        if a.get("language") and a["language"].lower() != "english":
            continue  # belt and braces: the query already asks for English only
        title = html.unescape(a.get("title") or "").strip()
        link = (a.get("url") or "").strip()
        source = (a.get("domain") or "").removeprefix("www.")
        if title and link and is_relevant(title):
            items.append({"title": title, "link": link, "guid": "gd:" + link, "source": source})
    return items


def fetch_items():
    """Google News search, GDELT search and the trafigura.com press page."""
    items, failures = [], 0
    jobs = [("Google News", fetch_news_items)]
    if GDELT_FEED_ENABLED:
        jobs.append(("GDELT", fetch_gdelt_items))
    if PRESS_FEED_ENABLED:
        jobs.append(("Press", fetch_press_items))
    for name, fn in jobs:
        try:
            items += fn()
        except Exception as exc:  # one bad source must not block the other
            failures += 1
            print(f"{name} failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    if failures == len(jobs):
        sys.exit("All sources failed")
    return items


def headline_key(title, source):
    """Normalised headline, used to collapse syndicated copies of one story."""
    t = title
    if source and t.endswith(" - " + source):
        t = t[: -(len(source) + 3)]
    return "h:" + re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def tokens(key):
    """Significant words of a normalised headline key."""
    return {w for w in key.removeprefix("h:").split() if len(w) > 2 and w not in STOPWORDS}


def find_similar(toks, pool):
    """Return (key, score) of the first earlier headline sharing most words with toks, else None."""
    if len(toks) < 4:
        return None
    for key, o in pool:
        if len(o) >= 4:
            score = len(toks & o) / len(toks | o)
            if score >= SIMILARITY:
                return key, score
    return None


def send(token, chat_id, text):
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    ).encode()
    http(f"https://api.telegram.org/bot{token}/sendMessage", data=data)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        sys.exit("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    items = fetch_items()
    first_run = not SEEN_FILE.exists()
    seen = json.loads(SEEN_FILE.read_text()) if not first_run else []
    seen_set = set(seen)

    def remember(keys):
        for k in keys:
            if k not in seen_set:
                seen_set.add(k)
                seen.append(k)

    # First run: record what exists now without sending a backlog.
    if first_run:
        for it in items:
            remember([it["guid"], headline_key(it["title"], it["source"])])
        SEEN_FILE.write_text(json.dumps(seen[-MAX_SEEN:]))
        send(token, chat_id, f"Trafigura tracker live. Seeded {len(items)} existing items.")
        print(f"Seeded {len(items)} items")
        return

    # First time a source is seen (guid prefix): record its existing items without sending.
    for prefix in ("tf:", "gd:"):
        if not any(k.startswith(prefix) for k in seen_set):
            old = [it for it in items if it["guid"].startswith(prefix)]
            for it in old:
                remember([it["guid"], headline_key(it["title"], it["source"])])
            items = [it for it in items if it not in old]

    seen_tokens = [(k, tokens(k)) for k in seen if k.startswith("h:")]
    pending = []
    batch = []
    for it in reversed(items):  # feed is newest first; send oldest first
        keys = [it["guid"], headline_key(it["title"], it["source"])]
        if any(k in seen_set for k in keys):
            continue
        toks = tokens(keys[1])
        match = find_similar(toks, seen_tokens + batch)
        if match:  # same story already sent or queued
            print(f"Skipped duplicate: {it['title']!r} ({it['source']}) ~ {match[0][2:]!r} [{match[1]:.2f}]")
            remember(keys)
            continue
        batch.append((keys[1], toks))
        pending.append((it, keys))

    sent = 0
    for it, keys in pending[:MAX_SEND]:
        label = f" ({it['source']})" if it["source"] else ""
        link = html.escape(it["link"], quote=True)
        text = f'<a href="{link}">{html.escape(it["title"])}</a>'
        if label:
            text += html.escape(label) if label not in it["title"] else ""
        try:
            send(token, chat_id, text)
        except urllib.error.URLError as exc:
            print(f"Send failed, will retry next run: {exc}", file=sys.stderr)
            break
        remember(keys)
        sent += 1

    SEEN_FILE.write_text(json.dumps(seen[-MAX_SEEN:]))
    print(f"Fetched {len(items)}, new {len(pending)}, sent {sent}")


if __name__ == "__main__":
    main()
