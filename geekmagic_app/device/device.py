"""
device.py - Sends rendered images to a GeekMagic SmallTV Ultra display.

The SmallTV Ultra (ESP8266, stock firmware) exposes a simple HTTP API:

    POST /doUpload?dir=/image/        multipart file upload
    GET  /set?img=/image/x.jpg        display a single image immediately
    GET  /set?theme=<n>               switch display theme
    GET  /set?picint=<seconds>        set photo album slideshow interval
    GET  /set?brt=<0-100>             set brightness
    GET  /app.json                    device status / ping

THEME NUMBERS (SmallTV Ultra V9.0.41):
    1 = Weather Clock Today
    2 = Weather Forecast
    3 = Photo Album  ← this is what we use for slideshow
    4 = Time Style 1
    5 = Time Style 2
    6 = Time Style 3
    7 = Simple Weather Clock

SLIDESHOW WORKFLOW:
    1. Upload all images with numbered filenames (hd_00.jpg, hd_01.jpg, ...)
    2. Call set_theme(THEME_PHOTO_ALBUM) → device enters album mode
    3. Call set_slideshow_interval(seconds) → device cycles at that speed
    The device handles cycling itself from that point on.

Usage:
    device = SmallTVDevice(ip="10.0.0.195")
    ok, msg = device.ping()
    ok, msg = device.send_all([img1, img2, img3], interval=10)
    ok, msg = device.send_image(img)      # single image, immediate display
"""

import io
import json
import http.client
import requests
from pathlib import Path
from PIL import Image
from typing import Callable


CANVAS_SIZE     = 240
DEFAULT_PORT    = 80
DEFAULT_TIMEOUT = 8
UPLOAD_DIR      = "/image/"
FILENAME_PREFIX = "hd_"       # hd_00.jpg, hd_01.jpg, ...
JPEG_QUALITY    = 90

# Theme number for Photo Album mode on SmallTV Ultra V9
# If your device shows a different theme, change this constant.
THEME_PHOTO_ALBUM = 3


class SmallTVDevice:
    """
    Communicates with a GeekMagic SmallTV Ultra over HTTP.

    Args:
        ip:       Device IP address (shown on screen at boot)
        port:     HTTP port, default 80
        timeout:  Request timeout in seconds
    """

    def __init__(
        self,
        ip: str,
        port: int = DEFAULT_PORT,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.ip      = ip.strip()
        self.port    = port
        self.timeout = timeout
        self._base   = f"http://{self.ip}:{self.port}"

    # ── Public API ────────────────────────────────────────────────────────────

    def ping(self) -> tuple[bool, str]:
        """Test connection via /app.json. Returns (success, message)."""
        try:
            resp = requests.get(f"{self._base}/app.json", timeout=self.timeout)
            resp.raise_for_status()
            return True, f"Connected to {self.ip} ✓  (status {resp.status_code})"
        except requests.exceptions.ConnectionError:
            return False, f"Cannot reach {self.ip} — is the device on the same network?"
        except requests.exceptions.Timeout:
            return False, f"Timeout connecting to {self.ip} ({self.timeout}s)"
        except Exception as e:
            return False, f"Ping error: {e}"

    def get_status(self) -> tuple[bool, dict]:
        """Fetch /app.json as a dict. Returns (success, data)."""
        try:
            resp = requests.get(f"{self._base}/app.json", timeout=self.timeout)
            resp.raise_for_status()
            return True, resp.json()
        except Exception as e:
            return False, {"error": str(e)}

    def send_image(self, img: Image.Image, filename: str = "hd_preview.jpg") -> tuple[bool, str]:
        """
        Upload a single PIL Image and immediately display it.
        Use this for single-image / current-item preview mode.
        Returns (success, message).
        """
        try:
            jpeg_bytes = self._to_jpeg(img)
        except Exception as e:
            return False, f"Image conversion failed: {e}"

        status, msg = self._upload(jpeg_bytes, filename)
        if status not in (200, 201, 204):
            return False, msg

        ok, msg = self._display_file(f"{UPLOAD_DIR}{filename}")
        if not ok:
            return False, msg

        return True, f"Image sent to {self.ip} ✓  ({len(jpeg_bytes) / 1024:.1f} KB)"

    def send_image_file(self, path: str | Path) -> tuple[bool, str]:
        """Load a PNG/JPEG from disk and send it. Convenience wrapper."""
        p = Path(path)
        if not p.exists():
            return False, f"File not found: {p.resolve()}"
        try:
            img = Image.open(p).convert("RGB")
        except Exception as e:
            return False, f"Cannot open image: {e}"
        return self.send_image(img)

    def send_all(
        self,
        images: list[Image.Image],
        interval: int = 10,
        progress_cb: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        """
        Upload a full set of images and start the Photo Album slideshow.

        Each image gets a numbered filename: hd_00.jpg, hd_01.jpg, ...
        After all uploads, the device is switched to Photo Album mode
        and the slideshow interval is set.

        Args:
            images:      List of PIL Images to upload.
            interval:    Seconds between slides (default 10).
            progress_cb: Optional callback(current, total) for UI progress updates.

        Returns (success, message).
        """
        if not images:
            return False, "No images to send"

        # Clear previous hd_xx.jpg files before uploading fresh set
        ok, msg = self.delete_hackadoodle_images()
        if ok and msg:
            print(f"[device] {msg}")

        total = len(images)
        uploaded = 0

        for i, img in enumerate(images):
            filename = f"{FILENAME_PREFIX}{i:02d}.jpg"
            try:
                jpeg_bytes = self._to_jpeg(img)
            except Exception as e:
                return False, f"Image {i} conversion failed: {e}"

            status, msg = self._upload(jpeg_bytes, filename)
            if status not in (200, 201, 204):
                return False, f"Upload failed at image {i+1}/{total}: {msg}"

            uploaded += 1
            if progress_cb:
                progress_cb(uploaded, total)

        # Upload album.json to root — this is what the firmware reads
        # for autoplay state and interval
        ok, msg = self.set_slideshow_interval(interval)
        if not ok:
            return True, f"{uploaded} image(s) uploaded. Warning: album.json failed ({msg})"

        # Switch to Photo Album theme — this triggers the device to re-read
        # album.json and start cycling
        ok, msg = self.set_theme(THEME_PHOTO_ALBUM)
        if not ok:
            return True, f"{uploaded} image(s) uploaded. Warning: theme switch failed ({msg})"

        return True, f"{uploaded} image(s) uploaded → slideshow started ({interval}s interval)"

    def list_images(self) -> list[str]:
        """
        Return a list of filenames currently in /image/ on the device.
        Parses the HTML directory listing returned by /doUpload?dir=/image/
        by uploading a dummy 0-byte file and reading the response table.
        """
        import re
        # The device returns an HTML file listing as the response body
        # when you POST to /doUpload. We upload a 0-byte placeholder
        # just to get the listing back.
        try:
            boundary = b"----HackadoodleBoundary"
            crlf = b"\r\n"
            body = (
                b"--" + boundary + crlf +
                b'Content-Disposition: form-data; name="file"; filename=".list"' + crlf +
                b"Content-Type: application/octet-stream" + crlf +
                crlf +
                b"" + crlf +
                b"--" + boundary + b"--" + crlf
            )
            conn = http.client.HTTPConnection(self.ip, self.port, timeout=self.timeout)
            conn.request(
                "POST",
                f"/doUpload?dir={UPLOAD_DIR}",
                body=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                    "Content-Length": str(len(body)),
                    "Connection": "close",
                }
            )
            resp = conn.getresponse()
            html = resp.read().decode(errors="replace")
            conn.close()
            # Extract filenames from href attributes: href='/image//filename.jpg'
            return re.findall(r"href='[^']*?/([^/']+)'", html)
        except Exception:
            return []

    def delete_hackadoodle_images(self, delay: float = 0.3) -> tuple[bool, str]:
        """
        Delete all hd_xx.jpg images from /image/.
        First fetches the file listing so we only delete files that exist.
        """
        import time

        files = self.list_images()
        to_delete = [f for f in files if f.startswith(FILENAME_PREFIX) and f.endswith(".jpg")]

        if not to_delete:
            return True, "No images to clear"

        deleted = 0
        for filename in to_delete:
            try:
                requests.get(
                    f"{self._base}/delete",
                    params={"file": f"{UPLOAD_DIR}/{filename}"},
                    timeout=self.timeout
                )
                deleted += 1
                time.sleep(delay)
            except Exception as e:
                return False, f"Deleted {deleted}/{len(to_delete)}, then error: {e}"

        return True, f"Cleared {deleted} old image(s)"

    def set_theme(self, theme: int) -> tuple[bool, str]:
        """
        Switch the device display theme.
        Use THEME_PHOTO_ALBUM (6) for slideshow mode.
        Returns (success, message).
        """
        try:
            resp = requests.get(
                f"{self._base}/set",
                params={"theme": theme},
                timeout=self.timeout
            )
            resp.raise_for_status()
            return True, f"Theme set to {theme}"
        except Exception as e:
            return False, f"Theme error: {e}"

    def set_slideshow_interval(self, seconds: int) -> tuple[bool, str]:
        """
        Enable autoplay and set the slide interval in one call.
        /set?i_i=<seconds>&autoplay=1 is the correct combined command.
        """
        try:
            resp = requests.get(
                f"{self._base}/set",
                params={"i_i": seconds, "autoplay": 1},
                timeout=self.timeout
            )
            resp.raise_for_status()
            body = resp.text.strip()
            if body == "OK":
                return True, f"Slideshow autoplay enabled ({seconds}s interval)"
            return False, f"Device rejected command: {body}"
        except Exception as e:
            return False, f"Slideshow interval error: {e}"

    def set_autoplay(self, enabled: bool, seconds: int | None = None) -> tuple[bool, str]:
        """
        Enable or disable slideshow autoplay.
        Optionally update the interval at the same time.
        """
        # Read current state first so we preserve i_i if not changing it
        try:
            resp = requests.get(f"{self._base}/album.json", timeout=self.timeout)
            current = resp.json()
        except Exception:
            current = {"autoplay": 0, "i_i": 10}

        payload = json.dumps({
            "autoplay": 1 if enabled else 0,
            "i_i": seconds if seconds is not None else current.get("i_i", 10)
        }).encode()

        try:
            status, body = self._upload(payload, "album.json", upload_dir="/",
                                        content_type="application/json")
            if status in (200, 201, 204):
                state = "enabled" if enabled else "disabled"
                return True, f"Slideshow autoplay {state}"
            return False, f"album.json upload failed: HTTP {status} {body}"
        except Exception as e:
            return False, f"Autoplay error: {e}"

    def get_album_state(self) -> tuple[bool, dict]:
        """Read current album autoplay state from device."""
        try:
            resp = requests.get(f"{self._base}/album.json", timeout=self.timeout)
            resp.raise_for_status()
            return True, resp.json()
        except Exception as e:
            return False, {"error": str(e)}

    def set_brightness(self, level: int) -> tuple[bool, str]:
        """Set display brightness 0–100. Returns (success, message)."""
        level = max(0, min(100, level))
        try:
            resp = requests.get(
                f"{self._base}/set",
                params={"brt": level},
                timeout=self.timeout
            )
            resp.raise_for_status()
            return True, f"Brightness set to {level}%"
        except Exception as e:
            return False, f"Brightness error: {e}"

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _upload(
        self,
        data: bytes,
        filename: str,
        upload_dir: str = UPLOAD_DIR,
        content_type: str = "image/jpeg",
    ) -> tuple[int, str]:
        """
        POST data to /doUpload using raw http.client.
        Returns (http_status_code, response_body).

        Uses http.client directly to guarantee exactly one Content-Length
        header. The requests library can produce duplicate or chunked
        headers that the ESP8266 web server rejects.
        """
        boundary = b"----HackadoodleBoundary"
        body = self._build_multipart(data, filename.encode(), boundary, content_type.encode())
        path = f"/doUpload?dir={upload_dir}"

        conn = http.client.HTTPConnection(self.ip, self.port, timeout=self.timeout)
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                "Content-Length": str(len(body)),
                "Connection": "close",
            }
        )
        resp = conn.getresponse()
        body_resp = resp.read().decode(errors="replace")
        conn.close()
        return resp.status, body_resp.strip()

    def _build_multipart(self, data: bytes, filename: bytes, boundary: bytes, content_type: bytes = b"image/jpeg") -> bytes:
        """Build a minimal multipart/form-data body (equivalent to curl -F file=@img.jpg)."""
        crlf = b"\r\n"
        return (
            b"--" + boundary + crlf +
            b'Content-Disposition: form-data; name="file"; filename="' + filename + b'"' + crlf +
            b"Content-Type: " + content_type + crlf +
            crlf +
            data + crlf +
            b"--" + boundary + b"--" + crlf
        )

    def _display_file(self, img_path: str) -> tuple[bool, str]:
        """Tell device to immediately display a specific uploaded file."""
        try:
            resp = requests.get(
                f"{self._base}/set",
                params={"img": img_path},
                timeout=self.timeout
            )
            resp.raise_for_status()
            return True, "Display OK"
        except Exception as e:
            return False, f"Display command error: {e}"

    def _to_jpeg(self, img: Image.Image) -> bytes:
        """Resize to 240×240 and encode as JPEG bytes."""
        resized = img.convert("RGB").resize((CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)
        buf = io.BytesIO()
        resized.save(buf, format="JPEG", quality=JPEG_QUALITY)
        return buf.getvalue()
