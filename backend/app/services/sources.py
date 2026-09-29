from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit

import cv2


def mask_rtsp_credentials(url: str) -> str:
    """Return an RTSP URL safe for logs / API responses.

    Replaces the password component with ``***`` so credentials never leak into
    log lines, error messages, or JSON responses. The username is preserved
    (operators need to recognise the account) but the secret is hidden.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if "@" not in (parts.netloc or ""):
        return url
    userinfo, _, hostpart = parts.netloc.rpartition("@")
    if ":" in userinfo:
        user, _, _pw = userinfo.partition(":")
        userinfo = f"{user}:***"
    else:
        userinfo = "***"
    masked = parts._replace(netloc=f"{userinfo}@{hostpart}")
    return urlunsplit(masked)


_RTSP_RE = re.compile(r"^rtsps?://", re.IGNORECASE)


class VideoSource(ABC):
    _cap: Optional[cv2.VideoCapture] = None

    @abstractmethod
    def processing_uri(self):
        """Return the value passed to cv2.VideoCapture(...)."""
        raise NotImplementedError

    def display_uri(self) -> str:
        """Human/log-safe representation of this source."""
        return str(self.processing_uri())

    @property
    def is_endless(self) -> bool:
        """True for sources that should never naturally end (live cameras)."""
        return True

    def open(self) -> cv2.VideoCapture:
        """Open and return a cv2.VideoCapture instance."""
        uri = self.processing_uri()
        cap = cv2.VideoCapture(uri)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video source: {self.display_uri()}")
        self._cap = cap
        return cap

    def close(self) -> None:
        """Release the cv2.VideoCapture instance if opened."""
        if getattr(self, "_cap", None) is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None


@dataclass
class UploadedFileSource(VideoSource):
    path: str

    def processing_uri(self) -> str:
        return self.path

    @property
    def is_endless(self) -> bool:
        return False

    @property
    def fps(self) -> float:
        cap = cv2.VideoCapture(self.path)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 25.0)
        cap.release()
        return fps if fps > 0 else 25.0

    @property
    def resolution(self) -> Tuple[int, int]:
        cap = cv2.VideoCapture(self.path)
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 1920)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 1080)
        cap.release()
        return (w, h)

    @property
    def frame_count(self) -> int:
        cap = cv2.VideoCapture(self.path)
        cnt = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        cap.release()
        return cnt


@dataclass
class WebcamSource(VideoSource):
    device_index: int = 0

    def processing_uri(self) -> int:
        return int(self.device_index)

    def display_uri(self) -> str:
        return f"webcam:{self.device_index}"


@dataclass
class RTSPSource(VideoSource):
    url: str

    def __post_init__(self) -> None:
        if not _RTSP_RE.match(self.url.strip()):
            raise ValueError("RTSP URL must start with rtsp:// or rtsps://")

    def processing_uri(self) -> str:
        return self.url

    def display_uri(self) -> str:
        return mask_rtsp_credentials(self.url)


@dataclass
class FileLoopSource(VideoSource):
    """Pseudo-camera that replays a video file as if it were a live stream.

    Used to develop and regression-test the entire live pipeline (capture
    thread, latest-frame-wins, rolling clip buffer, WebSocket status) without
    any hardware. The worker treats it like any endless source; when the file
    reaches its end the capture thread seeks back to frame 0.
    """

    path: str

    def processing_uri(self) -> str:
        return self.path

    def display_uri(self) -> str:
        return f"file-loop:{self.path}"


@dataclass
class HLSSource(VideoSource):
    """A public web stream: a direct HLS ``.m3u8`` URL or a YouTube live page.

    Our pipeline can only feed a concrete stream URL to OpenCV/ffmpeg. A YouTube
    watch URL is a webpage, not a stream, so for ``kind == "youtube"`` we shell
    out to ``yt-dlp`` to resolve the live HLS manifest at connection time. Those
    manifest URLs are time-limited, so ``processing_uri`` is re-run on every
    (re)connect — the worker's reconnect/backoff loop refreshes it for free.

    NOTE: such cameras are inherently uncalibrated (no homography for that
    viewpoint), so metric rules stay disabled — detection/tracking only.
    """

    url: str
    kind: str = "hls"  # "hls" (direct .m3u8) or "youtube"

    def __post_init__(self) -> None:
        self.kind = (self.kind or "hls").lower()
        if self.kind == "youtube" and importlib.util.find_spec("yt_dlp") is None:
            raise ValueError("yt-dlp is required for YouTube sources but is not installed.")

    def _resolve_youtube(self) -> str:
        # Invoke via the running interpreter so we always use the venv's yt-dlp,
        # regardless of the server process's PATH.
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "-g", "-f", "b", self.url],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()[:200]}")
        urls = [line for line in result.stdout.splitlines() if line.strip()]
        if not urls:
            raise RuntimeError("yt-dlp returned no stream URL.")
        # Prefer an HLS manifest if present; otherwise the first reported URL.
        for line in urls:
            if ".m3u8" in line:
                return line
        return urls[0]

    def processing_uri(self) -> str:
        if self.kind == "youtube":
            return self._resolve_youtube()
        return self.url

    def display_uri(self) -> str:
        return f"{self.kind}:{self.url}"


def build_source(source_type: str, source_uri: str) -> VideoSource:
    kind = (source_type or "").lower()
    if kind == "rtsp":
        return RTSPSource(url=source_uri)
    if kind == "webcam":
        return WebcamSource(device_index=int(source_uri or 0))
    if kind in ("file", "file_loop", "file-loop"):
        return FileLoopSource(path=source_uri)
    if kind == "youtube":
        return HLSSource(url=source_uri, kind="youtube")
    if kind == "hls":
        return HLSSource(url=source_uri, kind="hls")
    if kind == "upload":
        return UploadedFileSource(path=source_uri)
    raise ValueError(f"Unknown source type: {source_type}")
