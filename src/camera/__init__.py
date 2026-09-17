"""Camera layer: capture video/RTSP + anti-drift stream reader."""
from .capture import AsyncStreamReader, _is_stream, _mask_source, _open_capture

__all__ = ["AsyncStreamReader", "_is_stream", "_mask_source", "_open_capture"]
