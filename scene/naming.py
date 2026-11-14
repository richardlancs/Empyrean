"""When the scene asks for a name, and the JPEG crop that goes with it."""

from __future__ import annotations

import logging
import math

import cv2

from config.thresholds import NAME_CROP_PADDING, PROCESS_HEIGHT, PROCESS_WIDTH
from contracts.messages import Box, NameRequest, NameResult

logger = logging.getLogger("scene")


def crop_jpeg(image: object, box: Box) -> bytes | None:
    """JPEG of the box padded by NAME_CROP_PADDING, or None if image is None."""
    if image is None:
        return None
    frame_width, frame_height = _frame_size(image)
    bounds = _crop_bounds(box, frame_width, frame_height)
    if bounds is None:
        return None
    x1, y1, x2, y2 = bounds
    crop = image[y1:y2, x1:x2]
    if getattr(crop, "size", 0) == 0:
        return None
    try:
        ok, encoded = cv2.imencode(".jpg", crop)
    except cv2.error:
        logger.warning("could not encode a name crop")
        return None
    if not ok:
        logger.warning("could not encode a name crop")
        return None
    jpeg = encoded.tobytes()
    if not jpeg:
        return None
    return jpeg


def request_for_new_idle(
    ts: float,
    object_id: int,
    class_label: str,
    name: str,
    requests_sent: int,
    box: Box,
    image: object,
) -> NameRequest | None:
    """NameRequest the first time an idle object still needs a name.

    Return None if name is already non-empty, requests_sent is not 0,
    image is None, or the crop is empty.
    """
    if _has_name(name) or requests_sent != 0 or image is None:
        return None
    return _name_request(ts, object_id, class_label, box, image)


def after_name_result(
    ts: float,
    class_label: str,
    name: str,
    requests_sent: int,
    box: Box,
    image: object,
    result: NameResult,
) -> tuple[str, int, NameRequest | None]:
    """Apply a NameResult.

    Success (ok and a non-blank name): return (result.name, requests_sent, None).
    If name is already non-empty, keep it and return (name, requests_sent, None)
    even if this result failed.
    Failure while requests_sent < 2: return ("", requests_sent + 1, a new NameRequest)
    when a crop is available. If image is None, return ("", requests_sent + 1, None).
    Failure when requests_sent >= 2: return ("", requests_sent, None). No third try.
    """
    if _has_name(name):
        return (name, requests_sent, None)
    if result.ok and _has_name(result.name):
        return (result.name, requests_sent, None)
    if requests_sent >= 2:
        return ("", requests_sent, None)
    sent = requests_sent + 1
    if image is None:
        return ("", sent, None)
    return ("", sent, _name_request(ts, result.object_id, class_label, box, image))


def _has_name(name: str) -> bool:
    """True when name has something other than whitespace."""
    return name.strip() != ""


def _frame_size(image: object) -> tuple[int, int]:
    """Return (width, height) from the image, else the processed frame size."""
    shape = getattr(image, "shape", None)
    if shape is not None and len(shape) >= 2:
        height = int(shape[0])
        width = int(shape[1])
        if width > 0 and height > 0:
            return width, height
    return PROCESS_WIDTH, PROCESS_HEIGHT


def _crop_bounds(
    box: Box, frame_width: int, frame_height: int
) -> tuple[int, int, int, int] | None:
    """Padded exclusive pixel bounds, or None when the crop is empty.

    Padding is NAME_CROP_PADDING of the box width on the left and right and
    of the box height on the top and bottom. Clamp to the frame, then take
    floor of x1 and y1 and ceil of x2 and y2.
    """
    pad_x = (box.x2 - box.x1) * NAME_CROP_PADDING
    pad_y = (box.y2 - box.y1) * NAME_CROP_PADDING
    left = min(max(box.x1 - pad_x, 0.0), float(frame_width))
    top = min(max(box.y1 - pad_y, 0.0), float(frame_height))
    right = min(max(box.x2 + pad_x, 0.0), float(frame_width))
    bottom = min(max(box.y2 + pad_y, 0.0), float(frame_height))
    x1 = math.floor(left)
    y1 = math.floor(top)
    x2 = math.ceil(right)
    y2 = math.ceil(bottom)
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def _name_request(
    ts: float,
    object_id: int,
    class_label: str,
    box: Box,
    image: object,
) -> NameRequest | None:
    """NameRequest for this crop, or None when the JPEG is missing."""
    jpeg = crop_jpeg(image, box)
    if jpeg is None:
        return None
    return NameRequest(
        ts=ts,
        object_id=object_id,
        class_label=class_label,
        crop_jpeg=jpeg,
    )
