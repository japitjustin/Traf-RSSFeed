# Traf-RSSFeed

Sends new news headlines about Trafigura to a Telegram chat. It runs on GitHub Actions every 30 minutes and uses only the Python standard library.

## How it works

1. `trafigura_news.py` queries the Google News RSS search for `"Trafigura"` or `"TFG Marine"` on a fixed list of sites, limited to the last 2 days.
2. Optionally, it also reads any Google Alerts feeds you supply.
3. Items not seen before are sent to Telegram as a linked headline, oldest first, up to 10 per run. Each message starts with a prefix showing which feed found it: `[News]` for the Google News search, `[Alert 1]`, `[Alert 2]` and so on for the Google Alerts feeds, numbered in the order the URLs appear in `ALERT_FEED_URLS`.
4. Seen items are recorded in `seen.json`, which the workflow commits back to the repo.

On the first run (no `seen.json`) the script records the current items without sending them, then posts a single "tracker live" message.

Syndicated copies of one story are collapsed by normalised headline, so the same headline from several outlets is sent once. When both Google News and an alert feed return the same story, the alert prefix is the one that appears.

## Sites scanned

Edit `SITES` in `trafigura_news.py` to change them.

- reuters.com
- ft.com
- bloomberg.com
- spglobal.com
- argusmedia.com
- mining.com
- straitstimes.com
- shipandbunker.com
- splash247.com
- lloydslist.com
- trafigura.com

Coverage depends on what Google News has indexed for each site.

## Setup

1. Create a Telegram bot with BotFather and note its token. Get the chat ID of the chat that should receive messages.
2. In the repo, go to Settings > Secrets and variables > Actions and add:

| Secret | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token |
| `TELEGRAM_CHAT_ID` | Yes | Destination chat |
| `ALERT_FEED_URLS` | No | Google Alerts RSS URLs, separated by commas or whitespace |

3. Enable Actions. The workflow in `.github/workflows/trafigura-news.yml` runs on a 30-minute schedule and can also be started manually with "Run workflow".

## Run locally

```sh
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
python3 trafigura_news.py
```

This reads and updates `seen.json` in the current directory.

## Configuration

Constants at the top of `trafigura_news.py`:

- `KEYWORDS`: search terms.
- `SITES`: domains to search.
- `MAX_SEND`: maximum messages per run (10).
- `MAX_SEEN`: number of dedupe keys kept in `seen.json` (600).

The 2-day window is the `when:2d` term in `feed_url()`.

## Behaviour to know

- If a Telegram send fails, the script stops for that run and retries the remaining items next run.
- If every feed fails, the run exits with an error. A single failing feed is logged and skipped.
- The workflow pushes a commit to `main` whenever `seen.json` changes, so expect frequent "Update seen items" commits.
