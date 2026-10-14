# Traf-RSSFeed

Sends new news headlines about Trafigura to a Telegram chat. It runs on GitHub Actions every 30 minutes and uses only the Python standard library.

## How it works

1. `trafigura_news.py` reads the Google Alerts feeds you supply in `ALERT_FEED_URLS`, and scrapes the press release list on trafigura.com.
2. Optionally, it also queries the Google News RSS search for `"Trafigura"` or `"TFG Marine"` on a fixed list of sites, limited to the last 2 days. This is switched off by default (`NEWS_FEED_ENABLED = False`).
3. Items not seen before are sent to Telegram as a linked headline, oldest first, up to 10 per run.
4. Seen items are recorded in `seen.json`, which the workflow commits back to the repo.

On the first run (no `seen.json`) the script records the current items without sending them, then posts a single "tracker live" message.

Syndicated copies of one story are collapsed by normalised headline, so the same headline from several outlets is sent once.

## Trafigura press releases

Trafigura has no RSS feed that I could find, so the script reads the press release list at `PRESS_URL` and picks out links of the form `/press-releases/<year>/<slug>/`. Titles come from the link text, or from the URL slug when the link text is short. The first time the script sees this source, it records the existing releases without sending them. Turn it off with `PRESS_FEED_ENABLED = False`.

This is a scrape, so it breaks if the site changes its layout or loads the list with JavaScript. In that case the run logs `Press feed failed: no press release links found` and the other feeds carry on.

## Suggested Google Alerts

Each alert needs its own RSS feed URL, added to `ALERT_FEED_URLS`. In Google Alerts, set "Deliver to" to RSS feed, "How many" to All results, and "Sources" to Automatic.

- Entities: `"Trafigura"`, `"Trafigura Group"`, `"TFG Marine"`, `"Impala Terminals"`, `"Nyrstar"`, `"Puma Energy"`
- Legal and regulatory: `Trafigura lawsuit`, `Trafigura sanctions`, `Trafigura fine OR penalty OR investigation`, `Trafigura court`
- People: the names of senior executives you want to follow

## Sites scanned by the Google News search

Only used when `NEWS_FEED_ENABLED` is `True`. Edit `SITES` in `trafigura_news.py` to change them.

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

- `PRESS_FEED_ENABLED`: turns the trafigura.com press release scrape on or off (on).
- `NEWS_FEED_ENABLED`: turns the Google News search on or off (off).
- `PRESS_URL`: the press release list page.
- `KEYWORDS`: search terms.
- `SITES`: domains to search.
- `MAX_SEND`: maximum messages per run (10).
- `MAX_SEEN`: number of dedupe keys kept in `seen.json` (600).

The 2-day window is the `when:2d` term in `feed_url()`.

## Behaviour to know

- If a Telegram send fails, the script stops for that run and retries the remaining items next run.
- If no feed is enabled, or every feed fails, the run exits with an error. A single failing feed is logged and skipped.
- The workflow pushes a commit to `main` whenever `seen.json` changes, so expect frequent "Update seen items" commits.
