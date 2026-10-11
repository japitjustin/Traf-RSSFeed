"""Poll Google News RSS for Trafigura and push new headlines to Telegram.

Standard library only. State lives in seen.json (committed back by the workflow).
Env vars required: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
Optional: ALERT_FEED_URLS (Google Alerts RSS URLs, separated by commas or whitespace)
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

KEYWORDS = ["Trafigura", "TFG Marine"]
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
SEEN_FILE = Path("seen.json")
MAX_SEEN = 600   # keys kept (two per article)
MAX_SEND = 10    # cap per run so a backlog cannot flood the chat


def feed_url():
    sites = " OR ".join(f"site:{s}" for s in SITES)
    terms = " OR ".join(f'"{k}"' for k in KEYWORDS)
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


def fetch_news_items():
    root = ET.fromstring(http(feed_url()))
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link).strip()
        src = it.find("source")
        source = src.text.strip() if src is not None and src.text else ""
        if title and link:
            items.append({"title": title, "link": link, "guid": guid, "source": source})
    return items


ATOM = "{http://www.w3.org/2005/Atom}"


def unwrap_alert_link(href):
    """Google Alerts wraps links as google.com/url?...&url=<real>; return the real URL."""
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    return qs["url"][0] if qs.get("url") else href


def fetch_alert_items(feed):
    root = ET.fromstring(http(feed))
    items = []
    for entry in root.iter(ATOM + "entry"):
        raw_title = entry.findtext(ATOM + "title") or ""
        title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        link_el = entry.find(ATOM + "link")
        href = link_el.get("href", "") if link_el is not None else ""
        link = unwrap_alert_link(html.unescape(href))
        guid = (entry.findtext(ATOM + "id") or link).strip()
        source = urllib.parse.urlparse(link).netloc.removeprefix("www.")
        if title and link:
            items.append({"title": title, "link": link, "guid": guid, "source": source})
    return items


def fetch_items():
    """Google News search plus any Google Alerts feeds in ALERT_FEED_URLS (secret)."""
    items, failures, attempts = [], 0, 0
    jobs = [("news", fetch_news_items)]
    for feed in re.split(r"[\s,]+", os.environ.get("ALERT_FEED_URLS", "").strip()):
        if feed:
            jobs.append(("alert", lambda f=feed: fetch_alert_items(f)))
    for name, fn in jobs:
        attempts += 1
        try:
            items += fn()
        except Exception as exc:  # one bad feed must not block the others
            failures += 1
            print(f"{name} feed failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    if failures == attempts:
        sys.exit("All feeds failed")
    return items


def headline_key(title, source):
    """Normalised headline, used to collapse syndicated copies of one story."""
    t = title
    if source and t.endswith(" - " + source):
        t = t[: -(len(source) + 3)]
    return "h:" + re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


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

    pending = []
    batch = set()
    for it in reversed(items):  # feed is newest first; send oldest first
        keys = [it["guid"], headline_key(it["title"], it["source"])]
        if any(k in seen_set for k in keys):
            continue
        if keys[1] in batch:  # syndicated duplicate within this run
            remember(keys)
            continue
        batch.add(keys[1])
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
