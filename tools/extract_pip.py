"""Extract individual Pip poses from the supplied reference sheet (design tooling).

Each pose is one connected component in the sheet's alpha channel. Everything
else (about 3,900 near-transparent specks) is dropped. Near-opaque body pixels
(alpha >= 200, the sheet tops out at 254) become fully opaque; the anti-aliased
outline keeps its partial alpha. Each pose is cropped with even padding and
resized on premultiplied colour so edges do not pick up a dark halo.

    python tools/extract_pip.py SHEET.png OUT_DIR
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

# name: (approximate centre in the 1536 x 1024 sheet, output height in pixels)
POSES = {
    "pip-wave": ((230, 270), 192),     # top left: waving, eyes open
    "pip-point": ((730, 270), 192),    # top middle: pointing
    "pip-sit": ((230, 775), 192),      # bottom left: seated
    "pip-sign": ((1250, 760), 400),    # bottom right: holding a wide blank sign
}
# The help sign is drawn in HTML so its text can grow; this crop keeps Pip and its
# hands above the sign's top edge, trimmed to the sign's width.
PEEK_FROM = "pip-sign"
PADDING = 0.04
OPAQUE_FROM = 200


def extract(sheet: np.ndarray, centre: tuple[int, int], height: int) -> np.ndarray:
    """Return a clean RGBA image of the pose whose component contains centre."""
    alpha = sheet[:, :, 3]
    _count, labels, stats, _ = cv2.connectedComponentsWithStats((alpha > 0).astype(np.uint8), 8)
    label = labels[centre[1], centre[0]]
    if label == 0:
        raise ValueError(f"no pose at {centre}")
    x, y, w, h = stats[label, :4]
    keep = labels == label
    out = sheet.copy()
    out[~keep] = 0
    a = out[:, :, 3]
    a[keep & (a >= OPAQUE_FROM)] = 255
    pad = int(max(w, h) * PADDING)
    crop = out[max(0, y - pad): y + h + pad, max(0, x - pad): x + w + pad].astype(np.float32)
    # Resize premultiplied colour, then un-premultiply.
    rgb, a = crop[:, :, :3], crop[:, :, 3:4] / 255.0
    scale = height / crop.shape[0]
    size = (round(crop.shape[1] * scale), height)
    rgb_p = cv2.resize(rgb * a, size, interpolation=cv2.INTER_AREA)
    a_r = cv2.resize(a[:, :, 0], size, interpolation=cv2.INTER_AREA)[:, :, None]
    rgb_out = np.where(a_r > 1e-3, rgb_p / np.maximum(a_r, 1e-3), 0)
    result = np.concatenate([np.clip(rgb_out, 0, 255), np.clip(a_r * 255, 0, 255)], axis=2)
    return result.round().astype(np.uint8)


def peek(sign: np.ndarray) -> tuple[np.ndarray, dict[str, int]]:
    """Crop Pip above the sign's top border, between the sign's side borders."""
    h, w = sign.shape[:2]
    alpha = sign[:, :, 3]
    dark = (alpha > 200) & (sign[:, :, :3].mean(axis=2) < 110)
    top = next(y for y in range(int(h * 0.3), h) if dark[y].sum() > 0.25 * w)
    row = min(h - 1, top + int(h * 0.2))
    edges = [x for x in range(w) if alpha[row, x] > 128]
    left, right = edges[0], edges[-1] + 1
    return sign[:top, left:right], {"top": top, "left": left, "right": right, "width": w}


def main(argv: list[str]) -> int:
    """Write one PNG per pose."""
    sheet = cv2.imread(argv[1], cv2.IMREAD_UNCHANGED)
    if sheet is None or sheet.shape[2] != 4:
        raise SystemExit("the sheet must be an RGBA PNG")
    out_dir = Path(argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (centre, height) in POSES.items():
        image = extract(sheet, centre, height)
        path = out_dir / f"{name}.png"
        cv2.imwrite(str(path), image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        print(f"{path.name}: {image.shape[1]}x{image.shape[0]}, {path.stat().st_size} bytes")
        if name == PEEK_FROM:
            crop, where = peek(image)
            peek_path = out_dir / "pip-peek.png"
            cv2.imwrite(str(peek_path), crop, [cv2.IMWRITE_PNG_COMPRESSION, 9])
            print(f"{peek_path.name}: {crop.shape[1]}x{crop.shape[0]} (sign top {where['top']}, x {where['left']}-{where['right']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
