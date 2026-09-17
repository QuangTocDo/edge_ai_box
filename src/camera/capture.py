"""Mo nguon video/stream + doc frame chong tre (danh cho pipeline edge).

- File video: dung cv2.VideoCapture truc tiep.
- Stream RTSP/HTTP: dung AsyncStreamReader (thread nen doc lien tuc, chi giu
  frame moi nhat) de triet tre tich luy khi inference cham hon FPS stream.
"""
import logging
import threading
import time

import cv2


def _mask_source(src):
    """An user:pass trong RTSP khi log (khong lo credential)."""
    if isinstance(src, str) and "://" in src and "@" in src:
        try:
            pre, rest = src.split("://", 1)
            creds, tail = rest.split("@", 1)
            user = creds.split(":", 1)[0]
            return f"{pre}://{user}:***@{tail}"
        except ValueError:
            return "<rtsp>"
    return src


def _is_stream(src):
    return isinstance(src, str) and src.startswith(("rtsp://", "rtsps://",
                                                    "http://", "https://"))


def _open_capture(src, attempts=5, delay_s=3.0):
    """Mo VideoCapture co retry (cho RTSP rot mang). Tra ve cap hoac None."""
    for i in range(max(1, attempts)):
        cap = cv2.VideoCapture(src)
        if cap.isOpened():
            return cap
        cap.release()
        if i + 1 < attempts:
            logging.warning("Khong mo duoc source %s (lan %d/%d), thu lai sau %.0fs",
                            _mask_source(src), i + 1, attempts, delay_s)
            time.sleep(delay_s)
    return None


class AsyncStreamReader:
    """Thread-safe background frame grabber cho RTSP/HTTP streams.

    Doc frame lien tuc tren thread rieng va chi giu frame moi nhat.
    Loai bo hoan toan hien tuong tre tich luy (video drift) khi inference chay cham hon FPS stream.
    """

    def __init__(self, src, reconnect_fn=None, should_stop=None):
        self.src = src
        self.reconnect_fn = reconnect_fn or _open_capture
        # should_stop: callable() -> bool, de dung loop khi pipeline shutdown
        self.should_stop = should_stop or (lambda: False)
        self.cap = None
        self.lock = threading.Lock()
        self.stopped = False
        self.latest_frame = None
        self.thread = None
        self._init_cap()

    def _init_cap(self):
        self.cap = self.reconnect_fn(self.src)
        if self.cap and self.cap.isOpened():
            self.stopped = False
            self.thread = threading.Thread(target=self._worker, daemon=True)
            self.thread.start()

    def _worker(self):
        while not self.stopped and not self.should_stop():
            if not self.cap or not self.cap.isOpened():
                time.sleep(0.5)
                continue
            ok, frame = self.cap.read()
            if ok and frame is not None:
                with self.lock:
                    self.latest_frame = frame
            else:
                logging.warning("Stream reader mat ket noi %s, dang reconnect...",
                                _mask_source(self.src))
                if self.cap:
                    try:
                        self.cap.release()
                    except Exception:
                        pass
                self.cap = self.reconnect_fn(self.src)
                time.sleep(1.0)

    def read(self):
        with self.lock:
            if self.latest_frame is None:
                return False, None
            return True, self.latest_frame.copy()

    def get(self, prop_id):
        with self.lock:
            if self.cap:
                return self.cap.get(prop_id)
        return 0.0

    def isOpened(self):
        with self.lock:
            return bool(self.cap and self.cap.isOpened())

    def release(self):
        self.stopped = True
        with self.lock:
            if self.cap:
                try:
                    self.cap.release()
                except Exception:
                    pass
