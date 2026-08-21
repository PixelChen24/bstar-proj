"""B站数据采集模块"""

from .video import fetch_video_info
from .danmaku import fetch_danmaku
from .comment import fetch_comments

__all__ = ["fetch_video_info", "fetch_danmaku", "fetch_comments"]
