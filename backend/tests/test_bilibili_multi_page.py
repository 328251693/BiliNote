import unittest
from unittest.mock import Mock

from app.downloaders.bilibili_subtitle import BilibiliSubtitleFetcher
from app.models.transcriber_model import TranscriptSegment


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


if __name__ == "__main__":
    unittest.main()
