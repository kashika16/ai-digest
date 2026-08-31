# AI Daily Digest

AI Daily Digest is a lightweight morning briefing product for people who want high-signal AI updates without reading dozens of feeds.

It pulls relevant stories from selected company, editorial, research, product, and community sources, rewrites them into short key points, and adds a brief `Why it matters` explanation so the reader can quickly decide what affects their work.

The intended habit is simple: read one email before starting the day, get caught up on the AI developments that matter, and carry that context into product decisions, project work, and team conversations.

The default source profile is tuned for signal over volume:

- Primary sources first: OpenAI, Google DeepMind, Google AI, and Google Research.
- Two editorial outlets for US and Europe company context: TechCrunch AI and The Verge AI.
- One product strategy source: Lenny's Newsletter.
- One filtered community signal layer: Hacker News front page.
- One evaluation and model-behavior source: METR.
- One small research layer: arXiv `cs.AI`.
- No broad Google News aggregation by default because it adds too many incidental mentions.

## What it does

- Pulls entries from official company feeds, AI news feeds, and research feeds.
- Filters broad feeds like Hacker News and Lenny's Newsletter by AI/product keywords.
- Pushes editorial sources toward US and Europe company news, enterprise adoption, funding, regulation, and deployment activity.
- Filters to the last 24 hours by default.
- Keeps a small memory of exact links that were already emailed.
- Renders both HTML and plain-text email bodies.
- Converts each story into a short briefing with key points and a `Why it matters` line.
- Sends the digest over SMTP.
- Can render an HTML preview locally before you connect email delivery.
- Can install a macOS `launchd` job for a morning run.

## Files

- `run_digest.py`: command-line entrypoint.
- `sources.json`: editable list of sources and source priorities.
- `ai_digest/`: digest pipeline code.
- `Makefile`: simple learner commands.

## Configure

1. Copy `.env.example` to `.env`.
2. Fill in the SMTP and email values.
3. Adjust `sources.json` if you want different coverage.

Required settings to send email:

- `DIGEST_TO_EMAIL`
- `DIGEST_FROM_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Common optional settings:

- `DIGEST_HOURS_BACK=24`
- `DIGEST_MAX_ITEMS=20`
- `DIGEST_TIMEZONE=Europe/Berlin`
- `DIGEST_SUBJECT_PREFIX=AI Daily Digest`
- `DIGEST_SEND_HOUR=7`
- `DIGEST_MIN_ITEMS=8`
- `DIGEST_MAX_HOURS_BACK=72`
- `DIGEST_MAX_SEEN_LINKS=2000`

## Preview without sending

```bash
python3 run_digest.py --preview
```

To preview the current feed set even if items were already sent:

```bash
python3 run_digest.py --preview --ignore-seen
```

## Render HTML preview

```bash
python3 run_digest.py --preview-html /tmp/ai-digest-preview.html
```

Shortcut commands:

```bash
make test
make preview
make preview-html
```

## Run once

```bash
python3 run_digest.py
```

## Schedule every morning on macOS

```bash
python3 run_digest.py --install-launchd --hour 7 --minute 0
```

That writes the launch agent into `~/Library/LaunchAgents/ai-digest.plist`.

For a dry run into a local file first:

```bash
python3 run_digest.py --install-launchd --launchd-path ./launchd/generated.plist
```

Then load it:

```bash
launchctl load ~/Library/LaunchAgents/ai-digest.plist
```

The job is set for `07:00` local time and writes logs into `logs/`.

## Deploy with Vercel

This project supports Vercel as the cloud runtime, but the local preview is still the fastest way to review the product.

Files used for Vercel:

- `api/cron.py`: the scheduled HTTP endpoint
- `vercel.json`: the cron definitions
- `requirements.txt`: Python dependency for Vercel Blob

How it works:

1. Vercel Cron calls `/api/cron`.
2. The endpoint checks the configured local send hour.
3. The digest sends only once per local date.
4. If a quiet day produces too few items, the digest automatically widens the recency window from 24 hours to 48 hours, then 72 hours.
5. Seen-link state and last-sent state are stored in Vercel Blob instead of local files.
6. Feed failures are isolated per source, and unavailable sources are listed in the digest footer instead of aborting the run.

Why there is one hourly cron entry:

- Vercel cron uses UTC.
- The endpoint checks the local timezone and `DIGEST_SEND_HOUR`.
- A single hourly cron avoids coupling the deployment to one timezone offset or daylight-saving transition.
- The endpoint sends only when the local hour matches the configured target and the digest has not already been sent that day.

What to configure in Vercel:

1. Create a Vercel project from this repository.
2. Add these environment variables:
   - `DIGEST_TO_EMAIL`
   - `DIGEST_FROM_EMAIL`
   - `SMTP_HOST`
   - `SMTP_PORT`
   - `SMTP_USERNAME`
   - `SMTP_PASSWORD`
   - `SMTP_USE_TLS=true`
   - `SMTP_USE_SSL=false`
   - `DIGEST_TIMEZONE=Europe/Berlin`
   - `DIGEST_SEND_HOUR=7`
   - `CRON_SECRET`
3. Create a Blob store in Vercel so the function can persist state.
4. Redeploy the project.

Manual test on Vercel:

- `GET /api/cron?mode=preview` returns the current plain-text preview.
- `GET /api/cron?mode=send` forces a send and ignores seen history.
- `GET /api/cron` follows the scheduled-send rules.

Send the header `Authorization: Bearer <your-secret>` when manually calling the endpoint. The endpoint stays closed until `CRON_SECRET` is configured.

## Optional GitHub Actions

The repo also contains a GitHub Actions workflow at `.github/workflows/ai-digest.yml`, but Vercel is the cleaner cloud deployment path for this project when you want a hosted schedule.

## Customizing sources

Each source entry supports:

- `name`
- `url`
- `category`
- `priority`
- `max_items`

Higher `priority` sources are ranked earlier in the email.

The current defaults intentionally exclude broad aggregators and community feeds. That keeps the daily email closer to a market briefing than a mention tracker.

Hacker News is the one exception because its front page is often an early signal for developer attention. It is intentionally capped at `2` items so it does not dominate the digest.

Lenny's Newsletter is included as a product lens on AI. It is keyword-filtered so general career or growth posts do not flood the digest.

METR is included as a source for model evaluation, agent behavior, safety incidents, and benchmark-style performance analysis. It is keyword-filtered so unrelated research notes do not dominate the digest.

TechCrunch AI and The Verge AI are now filtered more aggressively toward AI company moves in the US and Europe, rather than broad consumer gadget coverage.

Anthropic is not included by default because it does not publish an official RSS feed for its newsroom. If you want Anthropic in the digest, the next clean step is adding a small HTML source adapter for `https://www.anthropic.com/news`.

If you have a paid X pipeline or an X-to-RSS exporter, add its feed URL as another source entry in `sources.json`.
