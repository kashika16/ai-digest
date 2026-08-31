import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import types
import unittest

from ai_digest.briefing import build_briefing_items
from ai_digest.config import DigestConfig, require_send_config
from ai_digest.digest import run_scheduled_digest
from ai_digest.launchd import launch_agent_dict
from ai_digest.pipeline import build_digest_entries, dedupe_entries, entry_matches_source, filter_recent_entries
from ai_digest.render import build_html, build_plaintext, build_subject
from ai_digest.rss import parse_feed
from ai_digest.models import FeedEntry, Source
from ai_digest.state import load_last_sent_file, load_seen_links_file, read_blob_text, save_last_sent_file, save_seen_links_file


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Feed</title>
    <item>
      <title>Launches new model</title>
      <link>https://example.com/model</link>
      <description><![CDATA[<p>Faster inference and lower latency.</p>]]></description>
      <pubDate>Thu, 13 Aug 2026 06:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class DigestTests(unittest.TestCase):
    def test_parse_feed_extracts_item(self) -> None:
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        entries = parse_feed(source, SAMPLE_RSS)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Launches new model")
        self.assertEqual(entries[0].summary, "Faster inference and lower latency.")

    def test_recent_filter_keeps_newer_entries(self) -> None:
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        fresh_entry = FeedEntry(
            source=source,
            title="Fresh",
            link="https://example.com/fresh",
            summary="Fresh summary",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )
        old_entry = FeedEntry(
            source=source,
            title="Old",
            link="https://example.com/old",
            summary="Old summary",
            published_at=datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc),
        )

        entries = filter_recent_entries([fresh_entry, old_entry], datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc))
        self.assertEqual(entries, [fresh_entry])

    def test_dedupe_entries_keeps_first_link(self) -> None:
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        first = FeedEntry(source, "First", "https://example.com/item", "one", datetime.now(timezone.utc))
        second = FeedEntry(source, "Second", "https://example.com/item", "two", datetime.now(timezone.utc))

        entries = dedupe_entries([first, second])
        self.assertEqual(entries, [first])

    def test_seen_links_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            seen_path = Path(temp_dir) / "seen.json"
            save_seen_links_file(seen_path, {"https://example.com/a", "https://example.com/b"})
            self.assertEqual(load_seen_links_file(seen_path), {"https://example.com/a", "https://example.com/b"})

    def test_render_outputs_content(self) -> None:
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        entry = FeedEntry(
            source=source,
            title="Fresh",
            link="https://example.com/fresh",
            summary="Summary body",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )
        now_local = datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc)
        items = build_briefing_items([entry])

        subject = build_subject("AI Daily Digest", now_local)
        plain = build_plaintext(now_local, 24, items)
        html = build_html(now_local, 24, items)

        self.assertEqual(subject, "AI Daily Digest - 2026-08-13")
        self.assertIn("AI Daily Brief", plain)
        self.assertIn("Fresh", plain)
        self.assertIn("What happened", plain)
        self.assertIn("Why it matters", plain)
        self.assertIn("https://example.com/fresh", html)
        self.assertIn("AI company briefing", html)
        self.assertIn("Open source story", html)
        self.assertNotIn("items selected", html)

    def test_require_send_config_reports_missing_values(self) -> None:
        config = DigestConfig(
            project_root=Path("/tmp/project"),
            sources_file=Path("/tmp/project/sources.json"),
            state_file=Path("/tmp/project/state.json"),
            last_sent_file=Path("/tmp/project/last_sent.txt"),
            log_dir=Path("/tmp/project/logs"),
            to_email=None,
            from_email=None,
            subject_prefix="AI Daily Digest",
            hours_back=24,
            max_items=20,
            timezone_name="Europe/Berlin",
            smtp_host=None,
            smtp_port=None,
            smtp_username=None,
            smtp_password=None,
            smtp_use_tls=True,
            smtp_use_ssl=False,
        )

        with self.assertRaises(ValueError) as context:
            require_send_config(config)

        self.assertIn("DIGEST_TO_EMAIL", str(context.exception))
        self.assertIn("SMTP_PASSWORD", str(context.exception))

    def test_launch_agent_dict_uses_project_paths(self) -> None:
        config = DigestConfig(
            project_root=Path("/tmp/project"),
            sources_file=Path("/tmp/project/sources.json"),
            state_file=Path("/tmp/project/state.json"),
            last_sent_file=Path("/tmp/project/last_sent.txt"),
            log_dir=Path("/tmp/project/logs"),
            to_email="to@example.com",
            from_email="from@example.com",
            subject_prefix="AI Daily Digest",
            hours_back=24,
            max_items=20,
            timezone_name="Europe/Berlin",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="user",
            smtp_password="pass",
            smtp_use_tls=True,
            smtp_use_ssl=False,
        )

        agent = launch_agent_dict(config, 7, 0)
        self.assertEqual(agent["ProgramArguments"][1], "/tmp/project/run_digest.py")
        self.assertEqual(agent["StartCalendarInterval"]["Hour"], 7)

    def test_keyword_filter_matches_ai_entries(self) -> None:
        source = Source(
            "Hacker News",
            "https://news.ycombinator.com/rss",
            "Community",
            4,
            2,
            include_keywords=("ai", "openai"),
        )
        matching_entry = FeedEntry(
            source=source,
            title="Show HN: AI coding agent",
            link="https://example.com/ai",
            summary="Built with OpenAI models.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )
        non_matching_entry = FeedEntry(
            source=source,
            title="New database benchmark",
            link="https://example.com/db",
            summary="A storage engine story.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        self.assertTrue(entry_matches_source(matching_entry, source))
        self.assertFalse(entry_matches_source(non_matching_entry, source))

    def test_keyword_filter_uses_word_boundaries(self) -> None:
        source = Source(
            "Hacker News",
            "https://news.ycombinator.com/rss",
            "Community",
            4,
            2,
            include_keywords=("ai",),
        )
        entry = FeedEntry(
            source=source,
            title="Fairphone 6 camera update",
            link="https://example.com/fairphone",
            summary="A phone hardware post.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(entry_matches_source(entry, source))

    def test_keyword_filter_respects_exclusions(self) -> None:
        source = Source(
            "The Verge AI",
            "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
            "News",
            5,
            2,
            include_keywords=("google", "ai"),
            exclude_keywords=("cat", "litter"),
        )
        entry = FeedEntry(
            source=source,
            title="Google AI litter robot review",
            link="https://example.com/review",
            summary="A cat gadget story.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        self.assertFalse(entry_matches_source(entry, source))

    def test_briefing_items_include_section_and_key_points(self) -> None:
        source = Source("Lenny's Newsletter", "https://www.lennysnewsletter.com/feed", "Product", 4, 2)
        entry = FeedEntry(
            source=source,
            title="How to build AI product sense",
            link="https://example.com/product-sense",
            summary="A practical framework for product teams. It shows where AI changes product judgment.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        item = build_briefing_items([entry])[0]
        self.assertEqual(item.section, "Product and Strategy")
        self.assertEqual(len(item.key_points), 2)
        self.assertIn("product teams", item.key_points[0].lower())

    def test_build_digest_entries_can_ignore_seen(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            state_file = project_root / "seen.json"
            save_seen_links_file(state_file, {"https://example.com/item"})
            config = DigestConfig(
                project_root=project_root,
                sources_file=project_root / "sources.json",
                state_file=state_file,
                last_sent_file=project_root / "last_sent.txt",
                log_dir=project_root / "logs",
                to_email=None,
                from_email=None,
                subject_prefix="AI Daily Digest",
                hours_back=24,
                max_items=20,
                timezone_name="Europe/Berlin",
                smtp_host=None,
                smtp_port=None,
                smtp_username=None,
                smtp_password=None,
                smtp_use_tls=True,
                smtp_use_ssl=False,
            )
            source = Source("Example", "https://example.com/feed", "News", 1, 5)
            seen_entry = FeedEntry(
                source=source,
                title="Seen",
                link="https://example.com/item",
                summary="Summary",
                published_at=datetime.now(timezone.utc),
            )

            from unittest.mock import patch

            with patch("ai_digest.pipeline.fetch_all_entries", return_value=[seen_entry]):
                _, normal_entries, _ = build_digest_entries(
                    config,
                    [source],
                    ignore_seen=False,
                    seen_links=load_seen_links_file(state_file),
                )
                _, preview_entries, _ = build_digest_entries(
                    config,
                    [source],
                    ignore_seen=True,
                    seen_links=load_seen_links_file(state_file),
                )

            self.assertEqual(normal_entries, [])
            self.assertEqual(preview_entries, [seen_entry])

    def test_last_sent_file_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "last_sent.txt"
            save_last_sent_file(path, "2026-08-28")
            self.assertEqual(load_last_sent_file(path), "2026-08-28")

    def test_read_blob_text_returns_empty_for_missing_blob(self) -> None:
        class BlobNotFoundError(Exception):
            pass

        class FakeBlobClient:
            async def get(self, pathname: str, access: str):
                raise BlobNotFoundError()

        vercel_module = types.ModuleType("vercel")
        blob_module = types.ModuleType("vercel.blob")
        internal_module = types.ModuleType("vercel._internal")
        internal_blob_module = types.ModuleType("vercel._internal.blob")
        internal_errors_module = types.ModuleType("vercel._internal.blob.errors")

        blob_module.AsyncBlobClient = FakeBlobClient
        internal_errors_module.BlobNotFoundError = BlobNotFoundError

        from unittest.mock import patch

        with patch.dict(
            sys.modules,
            {
                "vercel": vercel_module,
                "vercel.blob": blob_module,
                "vercel._internal": internal_module,
                "vercel._internal.blob": internal_blob_module,
                "vercel._internal.blob.errors": internal_errors_module,
            },
        ):
            self.assertEqual(asyncio.run(read_blob_text("state/seen-links.json")), "")

    def test_run_scheduled_digest_sends_once_per_day(self) -> None:
        config = DigestConfig(
            project_root=Path("/tmp/project"),
            sources_file=Path("/tmp/project/sources.json"),
            state_file=Path("/tmp/project/state.json"),
            last_sent_file=Path("/tmp/project/last_sent.txt"),
            log_dir=Path("/tmp/project/logs"),
            to_email="to@example.com",
            from_email="from@example.com",
            subject_prefix="AI Daily Digest",
            hours_back=24,
            max_items=20,
            timezone_name="Europe/Berlin",
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="user",
            smtp_password="pass",
            smtp_use_tls=True,
            smtp_use_ssl=False,
        )

        from unittest.mock import patch

        fake_now = datetime(2026, 8, 28, 7, 10, tzinfo=timezone.utc)
        with patch("ai_digest.digest.local_now", return_value=fake_now), patch(
            "ai_digest.digest.load_last_sent_date",
            side_effect=[None, "2026-08-28"],
        ), patch("ai_digest.digest.run_digest") as run_mock, patch(
            "ai_digest.digest.save_last_sent_date"
        ) as save_mock:
            first = run_scheduled_digest(config)
            second = run_scheduled_digest(config)

        self.assertEqual(first, "sent: 2026-08-28")
        self.assertEqual(second, "skip: already sent on 2026-08-28")
        self.assertEqual(run_mock.call_count, 1)
        save_mock.assert_called_once_with(config, "2026-08-28")


if __name__ == "__main__":
    unittest.main()
