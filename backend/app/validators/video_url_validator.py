from pydantic import AnyUrl, validator, BaseModel, field_validator
import re
from urllib.parse import parse_qs, urlparse

SUPPORTED_PLATFORMS = {
    "bilibili": r"(https?://)?(www\.)?bilibili\.com/video/[a-zA-Z0-9]+",
    "youtube": r"(https?://)?(www\.)?(youtube\.com/(watch\?v=|shorts/)|youtu\.be/)[\w\-]+",
    "douyin": "douyin",
    "kuaishou": "kuaishou"
}


def is_supported_video_url(url: str) -> bool:
    parsed = urlparse(url)

    # 检查是否为Bilibili的短链接
    if parsed.netloc == "b23.tv":
        return True

    # YouTube 分享链接的查询参数顺序不固定，不能只用 watch?v= 的正则判断。
    host = parsed.netloc.lower().split(":", 1)[0]
    path = parsed.path.rstrip("/")
    if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        query = parse_qs(parsed.query)
        if path == "/watch" and re.fullmatch(r"[\w-]{11}", query.get("v", [""])[0]):
            return True
        if re.fullmatch(r"/(shorts|embed|live)/[\w-]{11}", path):
            return True
    if host == "youtu.be" and re.fullmatch(r"/[\w-]{11}", path):
        return True

    for name, pattern in SUPPORTED_PLATFORMS.items():
        if name == "youtube":
            continue
        if pattern in ["douyin", "kuaishou"]:
            if pattern in url:
                return True
        else:
            if re.match(pattern, url):
                return True
    return False


class VideoRequest(BaseModel):
    url: AnyUrl
    platform: str

    @field_validator("url")
    def validate_video_url(cls, v):
        if not is_supported_video_url(str(v)):
            raise ValueError("暂不支持该视频平台或链接格式无效")
        return v
