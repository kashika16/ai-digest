# AI Daily Digest

This project sends one email every morning with the latest AI updates from a curated list of feeds.

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
- `launchd/ai-digest.plist`: example macOS scheduler template.

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

This project now supports Vercel as the cloud runtime.

Files used for Vercel:

- `api/cron.py`: the scheduled HTTP endpoint
- `vercel.json`: the cron definitions
- `requirements.txt`: Python dependency for Vercel Blob

How it works:

1. Vercel Cron calls `/api/cron`.
2. The endpoint checks the Berlin local hour.
3. The digest sends only once per local date.
4. Seen-link state and last-sent state are stored in Vercel Blob instead of local files.

Why there are two cron entries:

- Vercel cron uses UTC.
- Berlin shifts between UTC+1 and UTC+2.
- `05:00 UTC` covers summer time.
- `06:00 UTC` covers winter time.
- The endpoint sends only when the Berlin local hour is actually `07`, so only one of the two runs sends on a given day.

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
   - `CRON_SECRET`
3. Create a Blob store in Vercel so the function can persist state.
4. Redeploy the project.

Manual test on Vercel:

- `GET /api/cron?mode=preview` returns the current plain-text preview.
- `GET /api/cron?mode=send` forces a send and ignores seen history.
- `GET /api/cron` follows the scheduled-send rules.

If you set `CRON_SECRET`, send the header `Authorization: Bearer <your-secret>` when manually calling the endpoint.

## Optional GitHub Actions

The repo also contains a GitHub Actions workflow at `.github/workflows/ai-digest.yml`, but Vercel is now the preferred cloud deployment path for this project.

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
