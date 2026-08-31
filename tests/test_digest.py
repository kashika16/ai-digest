import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import types
import unittest

from api.cron import authorized
from ai_digest.briefing import build_briefing_items
from ai_digest.config import DigestConfig, require_send_config
from ai_digest.digest import run_scheduled_digest
from ai_digest.launchd import launch_agent_dict
from ai_digest.pipeline import build_digest_entries, dedupe_entries, entry_matches_source, fetch_all_entries, filter_recent_entries
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
        plain = build_plaintext(now_local, 24, items, [])
        html = build_html(now_local, 24, items, [])

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
        self.assertEqual(agent["ProgramArguments"][0], sys.executable)
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

    def test_community_items_drop_comments_filler(self) -> None:
        source = Source("Hacker News", "https://news.ycombinator.com/rss", "Community", 4, 2)
        entry = FeedEntry(
            source=source,
            title="Show HN: A better digest",
            link="https://example.com/hn",
            summary="Comments",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        item = build_briefing_items([entry])[0]
        self.assertEqual(item.key_points, ("Show HN: A better digest",))

    def test_sentence_splitting_keeps_vs_together(self) -> None:
        source = Source("Lenny's Newsletter", "https://example.com/feed", "Product", 4, 2)
        entry = FeedEntry(
            source=source,
            title="AI product strategy",
            link="https://example.com/strategy",
            summary="Build for steering vs. rowing. Then revisit your roadmap.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )

        item = build_briefing_items([entry])[0]
        self.assertEqual(item.key_points[0], "Build for steering vs. rowing.")

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

            with patch("ai_digest.pipeline.fetch_all_entries", return_value=([seen_entry], [])):
                normal_result = build_digest_entries(
                    config,
                    [source],
                    ignore_seen=False,
                    seen_links=load_seen_links_file(state_file),
                )
                preview_result = build_digest_entries(
                    config,
                    [source],
                    ignore_seen=True,
                    seen_links=load_seen_links_file(state_file),
                )

            self.assertEqual(normal_result.entries, [])
            self.assertEqual(preview_result.entries, [seen_entry])

    def test_build_digest_entries_widens_quiet_window(self) -> None:
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
            min_digest_items=3,
            max_digest_hours_back=72,
        )
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        entries = [
            FeedEntry(source, "Fresh", "https://example.com/fresh", "Fresh summary", datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc)),
            FeedEntry(source, "Older 1", "https://example.com/older-1", "Older summary", datetime(2026, 8, 12, 12, 0, tzinfo=timezone.utc)),
            FeedEntry(source, "Older 2", "https://example.com/older-2", "Older summary", datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)),
        ]

        from unittest.mock import patch

        with patch("ai_digest.pipeline.utc_now", return_value=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)), patch(
            "ai_digest.pipeline.fetch_all_entries",
            return_value=(entries, []),
        ):
            result = build_digest_entries(config, [source], ignore_seen=False, seen_links=set())

        self.assertEqual(result.coverage_hours, 48)
        self.assertEqual(len(result.entries), 3)

    def test_build_digest_entries_caps_seen_links(self) -> None:
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
            max_seen_links=3,
        )
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        entries = [FeedEntry(source, "New", "https://example.com/new", "Summary", datetime(2026, 8, 13, 8, 0, tzinfo=timezone.utc))]

        from unittest.mock import patch

        with patch("ai_digest.pipeline.utc_now", return_value=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc)), patch(
            "ai_digest.pipeline.fetch_all_entries",
            return_value=(entries, []),
        ):
            result = build_digest_entries(
                config,
                [source],
                ignore_seen=False,
                seen_links={"https://example.com/a", "https://example.com/b", "https://example.com/c"},
            )

        self.assertEqual(len(result.new_seen_links), 3)
        self.assertIn("https://example.com/new", result.new_seen_links)

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

    def test_run_scheduled_digest_uses_configured_hour(self) -> None:
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
            scheduled_hour=8,
        )

        from unittest.mock import patch

        fake_now = datetime(2026, 8, 28, 7, 10, tzinfo=timezone.utc)
        with patch("ai_digest.digest.local_now", return_value=fake_now):
            result = run_scheduled_digest(config)

        self.assertEqual(result, "skip: local hour is 07, target is 08")

    def test_authorized_requires_secret(self) -> None:
        request = types.SimpleNamespace(headers={})

        from unittest.mock import patch

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(authorized(request, "send"))

    def test_authorized_accepts_matching_secret(self) -> None:
        request = types.SimpleNamespace(headers={"Authorization": "Bearer top-secret"})

        from unittest.mock import patch

        with patch.dict("os.environ", {"CRON_SECRET": "top-secret"}, clear=True):
            self.assertTrue(authorized(request, "send"))

    def test_fetch_all_entries_isolates_source_failures(self) -> None:
        first = Source("First", "https://example.com/1", "News", 1, 5)
        second = Source("Second", "https://example.com/2", "News", 1, 5)
        entry = FeedEntry(first, "Fresh", "https://example.com/fresh", "Summary", datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc))

        from unittest.mock import patch

        def fake_fetch(source: Source) -> list[FeedEntry]:
            if source.name == "Second":
                raise ValueError("bad xml")
            return [entry]

        with patch("ai_digest.pipeline.fetch_entries_for_source", side_effect=fake_fetch):
            entries, failures = fetch_all_entries([first, second])

        self.assertEqual(entries, [entry])
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].source_name, "Second")
        self.assertIn("ValueError", failures[0].detail)

    def test_render_includes_unavailable_sources_note(self) -> None:
        source = Source("Example", "https://example.com/feed", "News", 1, 5)
        entry = FeedEntry(
            source=source,
            title="Fresh",
            link="https://example.com/fresh",
            summary="Summary body. More detail.",
            published_at=datetime(2026, 8, 13, 9, 0, tzinfo=timezone.utc),
        )
        item = build_briefing_items([entry])[0]
        failure = types.SimpleNamespace(source_name="Hacker News", detail="TimeoutError")
        plain = build_plaintext(datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc), 48, [item], [failure])
        html = build_html(datetime(2026, 8, 13, 11, 0, tzinfo=timezone.utc), 48, [item], [failure])

        self.assertIn("Sources unavailable today: Hacker News (TimeoutError)", plain)
        self.assertIn("Sources unavailable today", html)


if __name__ == "__main__":
    unittest.main()
