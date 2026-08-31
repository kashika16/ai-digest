# AI Daily Digest: Instructor Demo Notes

## Public Repository

The project repository is available here:

`https://github.com/kashika16/ai-digest`

## What The Product Does

AI Daily Digest is a lightweight email briefing system that pulls high-signal AI updates from selected sources, filters the noise, and rewrites the output into readable key points with a short explanation of why each item matters.

The intended use is to review the digest in the morning before starting work, then use the most relevant updates in project decisions and discussions with teammates or peers.

## Fastest Way To Review The Project

1. Read `README.md` for the product overview and setup steps.
2. Read `sources.json` to see how the source strategy is curated.
3. Run a preview locally to see the digest output without sending an email.

## Local Demo

From the repository root:

```bash
make preview
```

Or:

```bash
python3 run_digest.py --preview --ignore-seen
```

To render the HTML preview:

```bash
make preview-html
```

## Notes

- The core product works locally and sends email successfully when SMTP credentials are configured.
- The cloud deployment path was explored separately, but the public repository and local demo are the recommended evaluation path for this submission.
