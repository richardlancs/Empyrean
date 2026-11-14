"""Tests for scene naming: padded JPEG crops and the one retry."""

import math

import cv2
import numpy as np

from config.thresholds import NAME_CROP_PADDING, PROCESS_HEIGHT, PROCESS_WIDTH
from contracts.messages import Box, NameRequest, NameResult
from scene.naming import after_name_result, crop_jpeg, request_for_new_idle

_MARKER = (20, 180, 240)
_BOX = Box(100, 100, 200, 200)


def _frame(height: int = PROCESS_HEIGHT, width: int = PROCESS_WIDTH) -> np.ndarray:
    """Blank BGR frame."""
    return np.zeros((height, width, 3), dtype=np.uint8)


def _padded_bounds(box: Box, width: int, height: int) -> tuple[int, int, int, int]:
    """Exclusive crop after padding, clamping, floor, and ceil."""
    pad_x = (box.x2 - box.x1) * NAME_CROP_PADDING
    pad_y = (box.y2 - box.y1) * NAME_CROP_PADDING
    left = min(max(box.x1 - pad_x, 0.0), float(width))
    top = min(max(box.y1 - pad_y, 0.0), float(height))
    right = min(max(box.x2 + pad_x, 0.0), float(width))
    bottom = min(max(box.y2 + pad_y, 0.0), float(height))
    return math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)


def _paint(image: np.ndarray, box: Box) -> tuple[int, int, int, int]:
    """Paint the expected padded rect and return its exclusive bounds."""
    height, width = image.shape[:2]
    x1, y1, x2, y2 = _padded_bounds(box, width, height)
    image[y1:y2, x1:x2] = _MARKER
    return x1, y1, x2, y2


def _decode(jpeg: bytes) -> np.ndarray:
    """Decode a JPEG crop."""
    decoded = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decoded is not None
    return decoded


def _assert_marker(decoded: np.ndarray) -> None:
    """The decoded crop is the painted rect, within JPEG error."""
    delta = np.abs(decoded.astype(np.int16) - np.array(_MARKER, dtype=np.int16))
    assert int(delta.max()) <= 5


def test_crop_pads_each_side_by_name_crop_padding() -> None:
    image = _frame()
    x1, y1, x2, y2 = _paint(image, _BOX)
    # Width and height are 100. 10% is 10 px each side, so 120 x 120.
    # Those padded edges are integers, so floor and ceil do not change them.
    pad = (_BOX.x2 - _BOX.x1) * NAME_CROP_PADDING
    assert (_BOX.x1 - pad, _BOX.y1 - pad, _BOX.x2 + pad, _BOX.y2 + pad) == (
        90.0,
        90.0,
        210.0,
        210.0,
    )
    assert (x2 - x1, y2 - y1) == (120, 120)
    jpeg = crop_jpeg(image, _BOX)
    assert jpeg is not None
    assert jpeg.startswith(b"\xff\xd8")
    decoded = _decode(jpeg)
    assert decoded.shape[1] == 120
    assert decoded.shape[0] == 120
    _assert_marker(decoded)


def test_crop_touching_the_origin_is_clamped() -> None:
    box = Box(0, 0, 50, 40)
    pad_x = (box.x2 - box.x1) * NAME_CROP_PADDING
    pad_y = (box.y2 - box.y1) * NAME_CROP_PADDING
    assert box.x1 - pad_x < 0
    assert box.y1 - pad_y < 0
    image = _frame()
    x1, y1, x2, y2 = _paint(image, box)
    assert (x1, y1) == (0, 0)
    unclamped_w = math.ceil(box.x2 + pad_x) - math.floor(box.x1 - pad_x)
    unclamped_h = math.ceil(box.y2 + pad_y) - math.floor(box.y1 - pad_y)
    assert x2 - x1 < unclamped_w
    assert y2 - y1 < unclamped_h
    jpeg = crop_jpeg(image, box)
    assert jpeg is not None
    decoded = _decode(jpeg)
    assert decoded.shape[1] == x2 - x1
    assert decoded.shape[0] == y2 - y1
    assert decoded.shape[1] <= PROCESS_WIDTH
    assert decoded.shape[0] <= PROCESS_HEIGHT
    _assert_marker(decoded)


def test_crop_uses_the_image_size_when_the_array_is_present() -> None:
    width = 800
    height = 400
    image = _frame(height, width)
    box = Box(700, 100, 780, 200)
    x1, y1, x2, y2 = _paint(image, box)
    assert x1 > PROCESS_WIDTH
    assert y2 < height
    jpeg = crop_jpeg(image, box)
    assert jpeg is not None
    decoded = _decode(jpeg)
    assert (decoded.shape[1], decoded.shape[0]) == (x2 - x1, y2 - y1)
    _assert_marker(decoded)


def test_fractional_box_uses_floor_and_ceil() -> None:
    box = Box(100.2, 80.8, 200.2, 180.8)
    pad_x = (box.x2 - box.x1) * NAME_CROP_PADDING
    pad_y = (box.y2 - box.y1) * NAME_CROP_PADDING
    right = box.x2 + pad_x
    bottom = box.y2 + pad_y
    assert math.ceil(right) != math.trunc(right)
    assert math.ceil(bottom) != math.trunc(bottom)
    image = _frame()
    x1, y1, x2, y2 = _paint(image, box)
    assert (x1, y1, x2, y2) == (
        math.floor(box.x1 - pad_x),
        math.floor(box.y1 - pad_y),
        math.ceil(right),
        math.ceil(bottom),
    )
    jpeg = crop_jpeg(image, box)
    assert jpeg is not None
    decoded = _decode(jpeg)
    assert decoded.shape[1] == x2 - x1
    assert decoded.shape[0] == y2 - y1
    _assert_marker(decoded)


def test_crop_jpeg_none_image_is_none() -> None:
    assert crop_jpeg(None, _BOX) is None


def test_request_for_new_idle_returns_a_jpeg() -> None:
    image = _frame()
    _paint(image, _BOX)
    request = request_for_new_idle(
        ts=12.5,
        object_id=4,
        class_label="bottle",
        name="",
        requests_sent=0,
        box=_BOX,
        image=image,
    )
    assert request is not None
    assert request.crop_jpeg.startswith(b"\xff\xd8")
    assert request.object_id == 4
    assert request.class_label == "bottle"
    assert request.ts == 12.5
    decoded = _decode(request.crop_jpeg)
    assert (decoded.shape[1], decoded.shape[0]) == (120, 120)


def test_request_for_new_idle_returns_none_when_not_the_first_ask() -> None:
    image = _frame()
    assert request_for_new_idle(1.0, 4, "bottle", "", 1, _BOX, image) is None
    assert (
        request_for_new_idle(1.0, 4, "bottle", "Heinz ketchup", 0, _BOX, image) is None
    )
    assert request_for_new_idle(1.0, 4, "bottle", "", 0, _BOX, None) is None


def test_after_name_result_stores_success_without_another_request() -> None:
    result = NameResult(ts=9.0, object_id=4, name="Heinz ketchup", ok=True)
    name, sent, request = after_name_result(
        ts=9.0,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=_frame(),
        result=result,
    )
    assert name == "Heinz ketchup"
    assert sent == 1
    assert request is None


def test_success_stores_the_name_exactly() -> None:
    result = NameResult(ts=2.0, object_id=8, name=" Heinz ketchup ", ok=True)
    name, sent, request = after_name_result(
        ts=2.0,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=_frame(),
        result=result,
    )
    assert name == " Heinz ketchup "
    assert sent == 1
    assert request is None


def test_failure_retries_once_and_a_second_failure_stops() -> None:
    image = _frame()
    _paint(image, _BOX)
    failed = NameResult(ts=9.0, object_id=4, name="", ok=False)
    name, sent, request = after_name_result(
        ts=3.5,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=image,
        result=failed,
    )
    assert name == ""
    assert sent == 2
    assert isinstance(request, NameRequest)
    assert request.crop_jpeg.startswith(b"\xff\xd8")
    assert request.object_id == 4
    assert request.class_label == "bottle"
    assert request.ts == 3.5
    decoded = _decode(request.crop_jpeg)
    assert (decoded.shape[1], decoded.shape[0]) == (120, 120)

    name, sent, request = after_name_result(
        ts=4.0,
        class_label="bottle",
        name=name,
        requests_sent=sent,
        box=_BOX,
        image=image,
        result=NameResult(ts=4.0, object_id=4, name="", ok=False),
    )
    assert name == ""
    assert sent == 2
    assert request is None

    name, sent, request = after_name_result(
        ts=4.0,
        class_label="bottle",
        name="",
        requests_sent=2,
        box=_BOX,
        image=image,
        result=failed,
    )
    assert name == ""
    assert sent == 2
    assert request is None


def test_failure_does_not_clear_a_stored_name() -> None:
    result = NameResult(ts=9.0, object_id=4, name="", ok=False)
    name, sent, request = after_name_result(
        ts=9.0,
        class_label="bottle",
        name="Heinz ketchup",
        requests_sent=1,
        box=_BOX,
        image=_frame(),
        result=result,
    )
    assert name == "Heinz ketchup"
    assert sent == 1
    assert request is None


def test_later_success_does_not_replace_a_stored_name() -> None:
    result = NameResult(ts=3.0, object_id=4, name="Other brand", ok=True)
    name, sent, request = after_name_result(
        ts=3.0,
        class_label="bottle",
        name="Heinz ketchup",
        requests_sent=1,
        box=_BOX,
        image=_frame(),
        result=result,
    )
    assert name == "Heinz ketchup"
    assert sent == 1
    assert request is None


def test_blank_ok_name_is_a_failure() -> None:
    image = _frame()
    result = NameResult(ts=1.0, object_id=4, name="   ", ok=True)
    name, sent, request = after_name_result(
        ts=1.0,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=image,
        result=result,
    )
    assert name == ""
    assert sent == 2
    assert request is not None
    assert request.crop_jpeg.startswith(b"\xff\xd8")


def test_error_result_does_not_store_its_name_payload() -> None:
    result = NameResult(ts=1.0, object_id=4, name="Heinz ketchup", ok=False)
    name, sent, request = after_name_result(
        ts=1.0,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=_frame(),
        result=result,
    )
    assert name == ""
    assert sent == 2
    assert request is not None


def test_failure_without_an_image_counts_the_retry_and_sends_nothing() -> None:
    result = NameResult(ts=1.0, object_id=4, name="", ok=False)
    name, sent, request = after_name_result(
        ts=1.0,
        class_label="bottle",
        name="",
        requests_sent=1,
        box=_BOX,
        image=None,
        result=result,
    )
    assert name == ""
    assert sent == 2
    assert request is None
