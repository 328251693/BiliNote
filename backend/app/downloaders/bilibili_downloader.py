import os
import json
import logging
import shutil
import subprocess
import tempfile
from abc import ABC
from typing import Union, Optional, List

import yt_dlp

from app.downloaders.base import Downloader, DownloadQuality, QUALITY_MAP
from app.downloaders.bilibili_dm_patch import apply_bilibili_dm_img_patch
from app.downloaders.bilibili_subtitle import BilibiliSubtitleFetcher
from app.models.notes_model import AudioDownloadResult
from app.models.transcriber_model import TranscriptResult, TranscriptSegment
from app.utils.path_helper import get_data_dir
from app.utils.url_parser import extract_video_id, extract_bilibili_p_number
from app.services.cookie_manager import CookieConfigManager

logger = logging.getLogger(__name__)

# Inject the dm_img_* / web_location risk-control params Bilibili's wbi/playurl
# gateway now requires; without them the API path returns HTTP 412. See
# app/downloaders/bilibili_dm_patch.py for details.
apply_bilibili_dm_img_patch()


class BilibiliDownloader(Downloader, ABC):
    def __init__(self):
        super().__init__()
        self._cookie_mgr = CookieConfigManager()
        self._cookie = self._cookie_mgr.get('bilibili')
        self._cookiefile = self._write_netscape_cookie_file()

    def _write_netscape_cookie_file(self) -> Optional[str]:
        """将 Cookie 写入 Netscape 格式临时文件，返回文件路径（供 yt-dlp cookiefile 使用）"""
        if not self._cookie:
            logger.warning("B站 Cookie 未配置，下载可能失败")
            return None
        lines = ["# Netscape HTTP Cookie File\n"]
        for pair in self._cookie.split("; "):
            if "=" in pair:
                key, value = pair.split("=", 1)
                lines.append(f".bilibili.com\tTRUE\t/\tFALSE\t0\t{key}\t{value}\n")
        tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
        tmp.writelines(lines)
        tmp.close()
        logger.info("已生成 B站 Netscape Cookie 文件: %s (条目: %d)", tmp.name, len(lines) - 1)
        return tmp.name

    def download(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
        quality: DownloadQuality = "fast",
        need_video: Optional[bool] = False,
        skip_download: bool = False,
    ) -> AudioDownloadResult:
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir=self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        # 不带 p 参数的多 P B 站视频，在没有字幕时也要把全部章节的音频合并后再转写。
        # 需要视频截图/视频理解时仍沿用原流程，因为视频帧的章节时间轴还需要单独处理。
        bvid = extract_video_id(video_url, "bilibili")
        p = extract_bilibili_p_number(video_url)
        if bvid and p is None and not need_video:
            pages = BilibiliSubtitleFetcher().get_pages(bvid)
            if len(pages) > 1:
                return self._download_multi_page_audio(
                    video_url=video_url,
                    bvid=bvid,
                    pages=pages,
                    output_dir=output_dir,
                    quality=quality,
                    skip_download=skip_download,
                )

        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '64',
                }
            ],
            'noplaylist': True,
            'quiet': False,
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=not skip_download)
            video_id = info.get("id")
            title = info.get("title")
            duration = info.get("duration", 0)
            cover_url = info.get("thumbnail")
            audio_path = os.path.join(output_dir, f"{video_id}.mp3")

        return AudioDownloadResult(
            file_path=audio_path,
            title=title,
            duration=duration,
            cover_url=cover_url,
            platform="bilibili",
            video_id=video_id,
            raw_info=info,
            video_path=None  # ❗音频下载不包含视频路径
        )

    def _download_multi_page_audio(
        self,
        video_url: str,
        bvid: str,
        pages: List[dict],
        output_dir: str,
        quality: DownloadQuality,
        skip_download: bool,
    ) -> AudioDownloadResult:
        """下载并拼接多 P 音频；字幕已存在时只提取总视频元数据。"""
        first_url = f"https://www.bilibili.com/video/{bvid}?p=1"
        page_meta = []
        offset = 0.0
        for index, page in enumerate(pages, start=1):
            duration = float(page.get("duration") or 0)
            page_meta.append({
                **page,
                "p": int(page.get("page") or index),
                "start_offset": offset,
                "end_offset": offset + duration,
            })
            offset += duration
        if skip_download:
            ydl_opts = {
                "skip_download": True,
                "noplaylist": True,
                "quiet": True,
                "http_headers": {"Referer": "https://www.bilibili.com"},
            }
            if self._cookiefile:
                ydl_opts["cookiefile"] = self._cookiefile
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(first_url, download=False)
            return AudioDownloadResult(
                file_path="",
                title=info.get("title") or bvid,
                duration=sum(float(page.get("duration") or 0) for page in pages),
                cover_url=info.get("thumbnail"),
                platform="bilibili",
                video_id=bvid,
                raw_info={**info, "bili_pages": page_meta},
                video_path=None,
            )

        temp_dir = tempfile.mkdtemp(prefix=f"{bvid}_pages_", dir=output_dir)
        audio_files = []
        try:
            for index, _page in enumerate(pages, start=1):
                page_url = f"https://www.bilibili.com/video/{bvid}?p={index}"
                page_output = os.path.join(temp_dir, f"page_{index}.%(ext)s")
                ydl_opts = {
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                    "outtmpl": page_output,
                    "http_headers": {"Referer": "https://www.bilibili.com"},
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": QUALITY_MAP.get(quality, "64"),
                    }],
                    "noplaylist": True,
                    "quiet": False,
                }
                if self._cookiefile:
                    ydl_opts["cookiefile"] = self._cookiefile
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(page_url, download=True)
                audio_path = os.path.join(temp_dir, f"page_{index}.mp3")
                if not os.path.exists(audio_path):
                    raise FileNotFoundError(f"第 {index} 个分 P 音频未生成: {audio_path}")
                audio_files.append(audio_path)

            final_audio = os.path.join(output_dir, f"{bvid}.mp3")
            concat_list = os.path.join(temp_dir, "concat.txt")
            with open(concat_list, "w", encoding="utf-8") as f:
                for audio_file in audio_files:
                    f.write(f"file '{audio_file.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n")
            subprocess.run([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy", final_audio,
            ], check=True, capture_output=True)

            return AudioDownloadResult(
                file_path=final_audio,
                title=bvid,
                duration=sum(float(page.get("duration") or 0) for page in pages),
                cover_url=None,
                platform="bilibili",
                video_id=bvid,
                raw_info={"id": bvid, "title": bvid, "bili_pages": page_meta},
                video_path=None,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def download_video(
        self,
        video_url: str,
        output_dir: Union[str, None] = None,
    ) -> str:
        """
        下载视频，返回视频文件路径
        """

        if output_dir is None:
            output_dir = get_data_dir()
        os.makedirs(output_dir, exist_ok=True)
        print("video_url",video_url)
        video_id=extract_video_id(video_url, "bilibili")
        video_path = os.path.join(output_dir, f"{video_id}.mp4")
        if os.path.exists(video_path):
            return video_path

        # 检查是否已经存在


        output_path = os.path.join(output_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            'format': 'bv*[ext=mp4]/bestvideo+bestaudio/best',
            'outtmpl': output_path,
            'http_headers': {'Referer': 'https://www.bilibili.com'},
            'noplaylist': True,
            'quiet': False,
            'merge_output_format': 'mp4',  # 确保合并成 mp4
        }
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id")
            video_path = os.path.join(output_dir, f"{video_id}.mp4")

        if not os.path.exists(video_path):
            raise FileNotFoundError(f"视频文件未找到: {video_path}")

        return video_path

    def delete_video(self, video_path: str) -> str:
        """
        删除视频文件
        """
        if os.path.exists(video_path):
            os.remove(video_path)
            return f"视频文件已删除: {video_path}"
        else:
            return f"视频文件未找到: {video_path}"

    def download_subtitles(self, video_url: str, output_dir: str = None,
                           langs: List[str] = None) -> Optional[TranscriptResult]:
        """
        尝试获取B站视频字幕

        :param video_url: 视频链接
        :param output_dir: 输出路径
        :param langs: 优先语言列表
        :return: TranscriptResult 或 None
        """
        # 1) 优先走 B 站官方 player API（直拉，无需下视频；AI 字幕需 SESSDATA cookie）
        fetcher = BilibiliSubtitleFetcher()
        try:
            result = fetcher.fetch_subtitles(video_url)
            if result and result.segments:
                page_count = int((result.raw or {}).get("page_count") or 0)
                merged_pages = int((result.raw or {}).get("merged_pages") or 0)
                if page_count > 1 and merged_pages < page_count:
                    # 只拿到部分章节时不能直接返回，否则后续流程会误判为字幕完整。
                    logger.warning(
                        "B站多 P 字幕不完整（%s/%s），跳过 yt-dlp 首 P 字幕，改用全章节音频转写",
                        merged_pages,
                        page_count,
                    )
                    return None
                return result
        except Exception as e:
            logger.warning(f"player API 直拉字幕异常，回退到 yt-dlp: {e}")

        # yt-dlp 对不带 p 参数的多 P 链接通常只返回首 P；已知是多 P 时不能使用这个兜底。
        # 否则前端看到的是成功结果，但内容实际只覆盖第一章。
        bvid = extract_video_id(video_url, "bilibili")
        if bvid and extract_bilibili_p_number(video_url) is None:
            pages = fetcher.get_pages(bvid)
            if len(pages) > 1:
                logger.warning("B站多 P 链接跳过 yt-dlp 单 P 字幕兜底，将转写合并后的全章节音频")
                return None

        # 2) Fallback：原 yt-dlp 路径（更脆弱，遇到签名/Cookie 问题失败概率较高）
        if output_dir is None:
            output_dir = get_data_dir()
        if not output_dir:
            output_dir = self.cache_data
        os.makedirs(output_dir, exist_ok=True)

        if langs is None:
            langs = ['zh-Hans', 'zh', 'zh-CN', 'ai-zh', 'en', 'en-US']

        video_id = extract_video_id(video_url, "bilibili")

        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': langs,
            'subtitlesformat': 'srt/json3/best',  # 支持多种格式
            'skip_download': True,
            'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
            'quiet': True,
        }

        # 通过 CookieConfigManager 注入 B站 Cookie（Netscape cookiefile）
        if self._cookiefile:
            ydl_opts['cookiefile'] = self._cookiefile
            ydl_opts['http_headers'] = {'Referer': 'https://www.bilibili.com'}

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)

                # 查找下载的字幕文件
                subtitles = info.get('requested_subtitles') or {}
                if not subtitles:
                    logger.info(f"B站视频 {video_id} 没有可用字幕")
                    return None

                # 按优先级查找字幕
                detected_lang = None
                sub_info = None
                for lang in langs:
                    if lang in subtitles:
                        detected_lang = lang
                        sub_info = subtitles[lang]
                        break

                # 如果按优先级没找到，取第一个可用的（排除弹幕）
                if not detected_lang:
                    for lang, info_item in subtitles.items():
                        if lang != 'danmaku':  # 排除弹幕
                            detected_lang = lang
                            sub_info = info_item
                            break

                if not sub_info:
                    logger.info(f"B站视频 {video_id} 没有可用字幕（排除弹幕）")
                    return None

                # 检查是否有内嵌数据（yt-dlp 有时直接返回字幕内容）
                if 'data' in sub_info and sub_info['data']:
                    logger.info(f"直接从返回数据解析字幕: {detected_lang}")
                    return self._parse_srt_content(sub_info['data'], detected_lang)

                # 查找字幕文件
                ext = sub_info.get('ext', 'srt')
                subtitle_file = os.path.join(output_dir, f"{video_id}.{detected_lang}.{ext}")

                if not os.path.exists(subtitle_file):
                    logger.info(f"字幕文件不存在: {subtitle_file}")
                    return None

                # 根据格式解析字幕文件
                if ext == 'json3':
                    return self._parse_json3_subtitle(subtitle_file, detected_lang)
                else:
                    with open(subtitle_file, 'r', encoding='utf-8') as f:
                        return self._parse_srt_content(f.read(), detected_lang)

        except Exception as e:
            logger.warning(f"获取B站字幕失败: {e}")
            return None

    def _parse_srt_content(self, srt_content: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 SRT 格式字幕内容

        :param srt_content: SRT 字幕文本内容
        :param language: 语言代码
        :return: TranscriptResult
        """
        import re
        try:
            segments = []
            # SRT 格式: 序号\n时间戳\n文本\n\n
            pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\n\d+\n|$)'
            matches = re.findall(pattern, srt_content, re.DOTALL)

            for match in matches:
                idx, start_time, end_time, text = match
                text = text.strip()
                if not text:
                    continue

                # 转换时间格式 00:00:00,000 -> 秒
                def time_to_seconds(t):
                    parts = t.replace(',', '.').split(':')
                    return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])

                segments.append(TranscriptSegment(
                    start=time_to_seconds(start_time),
                    end=time_to_seconds(end_time),
                    text=text
                ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)
            logger.info(f"成功解析B站SRT字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'format': 'srt'}
            )

        except Exception as e:
            logger.warning(f"解析SRT字幕失败: {e}")
            return None

    def _parse_json3_subtitle(self, subtitle_file: str, language: str) -> Optional[TranscriptResult]:
        """
        解析 json3 格式字幕文件

        :param subtitle_file: 字幕文件路径
        :param language: 语言代码
        :return: TranscriptResult
        """
        try:
            with open(subtitle_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            segments = []
            events = data.get('events', [])

            for event in events:
                # json3 格式中时间单位是毫秒
                start_ms = event.get('tStartMs', 0)
                duration_ms = event.get('dDurationMs', 0)

                # 提取文本
                segs = event.get('segs', [])
                text = ''.join(seg.get('utf8', '') for seg in segs).strip()

                if text:  # 只添加非空文本
                    segments.append(TranscriptSegment(
                        start=start_ms / 1000.0,
                        end=(start_ms + duration_ms) / 1000.0,
                        text=text
                    ))

            if not segments:
                return None

            full_text = ' '.join(seg.text for seg in segments)

            logger.info(f"成功解析B站字幕，共 {len(segments)} 段")
            return TranscriptResult(
                language=language,
                full_text=full_text,
                segments=segments,
                raw={'source': 'bilibili_subtitle', 'file': subtitle_file}
            )

        except Exception as e:
            logger.warning(f"解析字幕文件失败: {e}")
            return None
