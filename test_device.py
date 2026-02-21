"""
test_device.py - Test your GeekMagic SmallTV Ultra connection and image upload.

Run from the hackadoodle/ root:
    python test_device.py <ip>                          ← ping + status
    python test_device.py <ip> send                     ← send first preview image
    python test_device.py <ip> send <path.png>          ← send specific file
    python test_device.py <ip> brightness <0-100>       ← set brightness
    python test_device.py <ip> album                    ← read album.json state
    python test_device.py <ip> album probe              ← probe /set commands
    python test_device.py <ip> album upload             ← try uploading album.json
    python test_device.py <ip> probe                    ← full endpoint discovery
"""

import sys
import json
import time
import http.client
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from geekmagic_app.device.device import SmallTVDevice


def upload_file(ip: str, upload_dir: str, filename: str, data: bytes, content_type: str) -> tuple[int, str]:
    """Raw multipart upload using http.client — same method as device.py."""
    boundary = b"----HackadoodleBoundary"
    crlf = b"\r\n"
    body = (
        b"--" + boundary + crlf +
        b'Content-Disposition: form-data; name="file"; filename="' + filename.encode() + b'"' + crlf +
        b"Content-Type: " + content_type.encode() + crlf +
        crlf +
        data + crlf +
        b"--" + boundary + b"--" + crlf
    )
    conn = http.client.HTTPConnection(ip, 80, timeout=8)
    conn.request(
        "POST",
        f"/doUpload?dir={upload_dir}",
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python test_device.py <ip> [action] [arg]")
        sys.exit(1)

    ip     = sys.argv[1]
    action = sys.argv[2] if len(sys.argv) > 2 else "ping"
    arg    = sys.argv[3] if len(sys.argv) > 3 else None

    device = SmallTVDevice(ip=ip)

    # ── Always ping first ─────────────────────────────────────────────────────
    print(f"\nPinging {ip}...")
    ok, msg = device.ping()
    print(f"  {'✓' if ok else '✗'} {msg}")
    if not ok:
        print("\nCannot continue — fix connection first.")
        sys.exit(1)

    ok, status = device.get_status()
    if ok and status:
        print(f"  Device status: {status}")

    # ── Actions ───────────────────────────────────────────────────────────────

    if action == "send":
        target = Path(arg) if arg else sorted(Path("preview_output").glob("preview_*.png"))[0]
        print(f"\nSending {target.name}...")
        ok, msg = device.send_image_file(target)
        print(f"  {'✓' if ok else '✗'} {msg}")

    elif action == "delete":
        print("\nDeleting hd_xx.jpg images from device...")
        ok, msg = device.delete_hackadoodle_images()
        print(f"  {'✓' if ok else '✗'} {msg}")

    elif action == "brightness":
        level = int(arg) if arg else 75
        print(f"\nSetting brightness to {level}%...")
        ok, msg = device.set_brightness(level)
        print(f"  {'✓' if ok else '✗'} {msg}")

    elif action == "album":
        r = requests.get(f"http://{ip}/album.json", timeout=5)
        print(f"\n  Album state: {r.text.strip()}")

        if arg == "probe":
            # Try every plausible /set command for autoplay
            print("\nProbing /set commands for autoplay...")
            tests = [
                ("autoplay=1",  {"autoplay": 1}),
                ("autoplay=0",  {"autoplay": 0}),
                ("auto=1",      {"auto": 1}),
                ("play=1",      {"play": 1}),
                ("i_i=5",       {"i_i": 5}),
                ("delay=5",     {"delay": 5}),
            ]
            for label, params in tests:
                r = requests.get(f"http://{ip}/set", params=params, timeout=5)
                print(f"  /set?{label:<20} → {r.status_code}  {r.text.strip()!r}")

            time.sleep(0.5)
            r = requests.get(f"http://{ip}/album.json", timeout=5)
            print(f"\n  Album state after: {r.text.strip()}")

        elif arg == "upload":
            # Try uploading album.json to the root filesystem
            # This is how the web UI likely persists the setting
            print("\nTrying to upload album.json...")
            payload = json.dumps({"autoplay": 1, "i_i": 5}).encode()

            for upload_dir in ["/", "/image/", "/cfg/", "/config/"]:
                try:
                    status, body = upload_file(ip, upload_dir, "album.json", payload, "application/json")
                    print(f"  Upload to {upload_dir:<12} → HTTP {status}  {body!r}")
                except Exception as e:
                    print(f"  Upload to {upload_dir:<12} → ERROR: {e}")

            time.sleep(1)
            r = requests.get(f"http://{ip}/album.json", timeout=5)
            print(f"\n  Album state after upload: {r.text.strip()}")

    elif action == "probe":
        print("\nProbing endpoints...")
        endpoints = [
            "/app.json", "/album.json", "/status", "/status.json",
            "/config", "/config.json", "/settings", "/settings.json",
            "/list", "/list?dir=/image/", "/files", "/files?dir=/image/",
            "/get", "/state", "/state.json", "/", "/index.html",
        ]
        for path in endpoints:
            try:
                r = requests.get(f"http://{ip}{path}", timeout=5)
                print(f"  GET {path:<30} → {r.status_code}  {r.text[:120].strip()!r}")
            except Exception as e:
                print(f"  GET {path:<30} → ERROR: {e}")


if __name__ == "__main__":
    main()
