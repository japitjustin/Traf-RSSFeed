# Traf-RSSFeed

Sends new news headlines about Trafigura to a Telegram chat. It runs on GitHub Actions every 30 minutes and uses only the Python standard library.

## Where the news comes from

The script reads exactly three sources on every run. Nothing else is queried.

| Source | What the script does | Switch |
|---|---|---|
| Google News | One request to `news.google.com/rss/search`. The query combines every term in `KEYWORDS` and `LEGAL_TERMS` with every domain in `SITES`, limited to the last 2 days. It is one combined search, not one search per keyword. | Always on |
| GDELT | One request to the GDELT DOC 2.0 API (`api.gdeltproject.org`). The query is every term in `KEYWORDS` joined with OR, for the last 2 days, newest first, up to 75 articles. English only. It is not limited to `SITES`, so it can find outlets Google News does not. | `GDELT_FEED_ENABLED` |
| trafigura.com press releases | Reads the press release list at `PRESS_URL` and picks out the release links. | `PRESS_FEED_ENABLED` |

Each Telegram message is a linked headline, with the outlet name added when the headline does not already contain it.

If a source fails, the run logs `<source> failed: ...` and carries on with the others. If all of them fail, the run exits with an error.

## How it works

1. Fetch the sources.
2. Drop Google News and GDELT results whose headline contains none of the `KEYWORDS` (see below).
3. Drop headlines that match a story already sent or queued (see below).
4. Send what is left to Telegram, oldest first, up to 10 per run.
5. Record what was seen in `seen.json`, which the workflow commits back to the repo.

On the first run (no `seen.json`) the script records the current items without sending them, then posts a single "tracker live" message. The same quiet start applies the first time GDELT or the press page is seen: their existing items are recorded without being sent.

### Headline must contain a keyword

Google matches the whole page, so an article is returned when a "related stories" or "more from author" link mentions Trafigura, and GDELT matches article text too. To avoid that, a Google News or GDELT result is kept only if a `KEYWORDS` term appears in its headline. The cost is that a story naming Trafigura only in its body text is dropped. Press releases from trafigura.com are not filtered.

### Duplicates

Copies of one story are collapsed by headline. A headline is skipped if it shares at least 60% of its words (`SIMILARITY`) with one already sent or queued, so rewritten headlines on other outlets are caught too. Headlines with fewer than 4 significant words are only matched exactly. Lower `SIMILARITY` to catch more duplicates, at the risk of hiding distinct stories.

#### Checking what was skipped

Every skipped duplicate is printed in the workflow log. Open the repo's Actions tab, pick a "Trafigura news" run, and expand the "Check feed and notify" step. Each skip looks like this:

```
Skipped duplicate: 'Trafigura wins copper smelter deal in Peru, sources say' (Reuters) ~ 'trafigura wins 500m copper smelter deal in peru' [0.67]
```

That is the skipped headline and its source, then the earlier headline it matched (lower case, punctuation removed) and the word overlap score. A score just above `SIMILARITY` is the case to check for a wrongly merged story. Skips are not shown for stories already sent in an earlier run by exact link or exact headline, only for the fuzzy matches.

## Google News search

`KEYWORDS` are the company and entity names searched, and `LEGAL_TERMS` are added as `Trafigura (lawsuit OR sanctions OR ...)`. The search is limited to these sites, which you can change in `SITES`:

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

Coverage depends on what Google News has indexed for each site. The 2-day window is the `when:2d` term in `feed_url()`.

## GDELT

GDELT is a free news index with no key. The script asks for articles matching any `KEYWORDS` term. If GDELT returns an error message instead of results, the run logs `GDELT failed: RuntimeError: unexpected reply: ...` and the other sources carry on. The query asks for English-language articles only (`sourcelang:english`), and any article GDELT labels as another language is dropped as well. Google News is asked for the English edition (`hl=en-SG`, `ceid=SG:en`) but its feed has no per-article language label, so it is not filtered further.

## Trafigura press releases

Trafigura has no RSS feed that I could find, so the script reads the press release list at `PRESS_URL` and picks out links of the form `/press-releases/<year>/<slug>/`. Titles come from the link text, or from the URL slug when the link text is short. The first time the script sees this source, it records the existing releases without sending them.

This is a scrape, so it breaks if the site changes its layout or loads the list with JavaScript. In that case the run logs `Press failed: RuntimeError: no press release links found` and Google News carries on.

## Setup

1. Create a Telegram bot with BotFather and note its token. Get the chat ID of the chat that should receive messages.
2. In the repo, go to Settings > Secrets and variables > Actions and add:

| Secret | Purpose |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token |
| `TELEGRAM_CHAT_ID` | Destination chat |

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

- `KEYWORDS`: entity names searched on Google News, and the terms a headline must contain.
- `LEGAL_TERMS`: legal and regulatory words added to the Google News search.
- `SITES`: domains the Google News search is limited to. GDELT is not limited by it.
- `GDELT_FEED_ENABLED`: turns the GDELT search on or off (on).
- `PRESS_FEED_ENABLED`: turns the trafigura.com press release scrape on or off (on).
- `PRESS_URL`: the press release list page.
- `SIMILARITY`: word overlap above which two headlines count as the same story (0.6).
- `MAX_SEND`: maximum messages per run (10).
- `MAX_SEEN`: number of dedupe keys kept in `seen.json` (600).

## Behaviour to know

- If a Telegram send fails, the script stops for that run and retries the remaining items next run.
- The workflow pushes a commit to `main` whenever `seen.json` changes, so expect frequent "Update seen items" commits.
