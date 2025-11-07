import io
import json
from typing import Optional

import qrcode
from PIL import Image
import numpy as np

# NOTE: import heavy/OS-bound image libraries lazily inside functions to avoid import-time failures
# (some hosting environments may not have compatible opencv/segno binary wheels for the Python runtime).



def make_payload(row: dict) -> str:
    """Create a compact payload for a QR code from a row dict.

    Payload is JSON with at least an identifier (srn/email/name) so scanner can find the person.
    """
    # Simplified payload: include only Team Name and Name as requested
    team = row.get("Team Name") or row.get("teamName") or row.get("team") or ""
    name = row.get("Name") or row.get("name") or ""
    payload = {
        "team": team,
        "name": name,
    }
    return json.dumps(payload, ensure_ascii=False)


def generate_qr_image(payload: str, box_size: int = 6) -> Image.Image:
    """Return a PIL Image of the code for the given payload string.

    Tries to generate an Aztec code (using segno) and falls back to a QR code when segno
    isn't available.
    """
    # prefer Aztec codes when available; import segno lazily
    try:
        import segno
    except Exception:
        segno = None

    if segno is not None:
        try:
            # segno can generate aztec codes
            code = segno.make(payload, kind="aztec")
            buf = io.BytesIO()
            # save PNG to buffer
            code.save(buf, kind="png", scale=4)
            buf.seek(0)
            img = Image.open(buf).convert("RGB")
            return img
        except Exception:
            pass

    # fallback to QR via qrcode
    qr = qrcode.QRCode(box_size=box_size, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img


def decode_qr_from_bytes(image_bytes: bytes) -> Optional[str]:
    """Decode a QR code from image bytes. Returns payload string or None.
    Tries OpenCV's QRCodeDetector first (no zbar dependency). Falls back to pyzbar if available.
    """
    # Try OpenCV QRCodeDetector (import lazily)
    try:
        import cv2
    except Exception:
        cv2 = None

    if cv2 is not None:
        try:
            arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            detector = cv2.QRCodeDetector()
            data, points, straight_qrcode = detector.detectAndDecode(img)
            if data:
                return data
        except Exception:
            pass

    # Fallback to pyzbar if available (import lazily)
    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except Exception:
        pyzbar_decode = None

    if pyzbar_decode is not None:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        decoded = pyzbar_decode(img)
        if not decoded:
            return None
        data = decoded[0].data
        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("latin-1")

    # No decoder available; return None to let caller handle gracefully
    return None
