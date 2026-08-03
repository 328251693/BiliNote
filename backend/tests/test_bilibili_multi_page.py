import unittest
from unittest.mock import Mock, patch

from app.downloaders.bilibili_downloader import BilibiliDownloader
from app.downloaders.bilibili_subtitle import BilibiliSubtitleFetcher
from app.models.transcriber_model import TranscriptResult, TranscriptSegment


class TestBilibiliMultiPage(unittest.TestCase):
    def _fetcher(self, results):
        fetcher = object.__new__(BilibiliSubtitleFetcher)
        fetcher._fetch_page_transcript = Mock(side_effect=results)
        return fetcher

    def test_url_without_p_merges_all_pages_with_continuous_timestamps(self):
        fetcher = self._fetcher([
            ("zh-CN", [TranscriptSegment(0, 10, "第一章")]),
            ("zh-CN", [TranscriptSegment(0, 8, "第二章")]),
        ])
        pages = [
            {"page": 1, "cid": 101, "part": "第一章", "duration": 12},
            {"page": 2, "cid": 102, "part": "第二章", "duration": 9},
        ]

        result = fetcher._merge_pages("BVtest", pages)

        self.assertEqual([segment.text for segment in result.segments], ["第一章", "第二章"])
        self.assertEqual(result.segments[1].start, 12)
        self.assertEqual(result.raw["merged_pages"], 2)

    def test_url_with_p_only_merges_selected_page(self):
        fetcher = self._fetcher([
            ("zh-CN", [TranscriptSegment(0, 8, "第二章")]),
        ])
        pages = [
            {"page": 1, "cid": 101, "duration": 12},
            {"page": 2, "cid": 102, "duration": 9},
        ]

        result = fetcher._merge_pages("BVtest", pages, selected_p=2)

        self.assertEqual(len(result.segments), 1)
        self.assertEqual(result.segments[0].start, 0)
        self.assertEqual(result.raw["pages"][0]["p"], 2)

    def test_partial_subtitles_keep_page_coverage_metadata(self):
        fetcher = self._fetcher([
            ("zh-CN", [TranscriptSegment(0, 8, "第一章")]),
            None,
        ])
        pages = [
            {"page": 1, "cid": 101, "duration": 12},
            {"page": 2, "cid": 102, "duration": 9},
        ]

        result = fetcher._merge_pages("BVtest", pages)

        self.assertEqual(result.raw["page_count"], 2)
        self.assertEqual(result.raw["merged_pages"], 1)

    @patch("app.downloaders.bilibili_downloader.BilibiliSubtitleFetcher")
    def test_partial_subtitles_fall_back_to_full_audio_transcription(self, fetcher_cls):
        fetcher_cls.return_value.fetch_subtitles.return_value = TranscriptResult(
            language="zh-CN",
            full_text="只有第一章",
            segments=[TranscriptSegment(0, 8, "只有第一章")],
            raw={"page_count": 2, "merged_pages": 1},
        )
        downloader = object.__new__(BilibiliDownloader)

        result = downloader.download_subtitles("https://www.bilibili.com/video/BVtest")

        self.assertIsNone(result)
        fetcher_cls.return_value.get_pages.assert_not_called()


if __name__ == "__main__":
    unittest.main()
