
import math
import queue
import threading
import time
from pathlib import Path

import cv2
import mediapipe as mp
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection


# ==========================================
# SETTINGS
# ==========================================

CAMERA_INDEX = 0
MIRROR = True
DEVICE = "cpu"

MODEL_ID = "IDEA-Research/grounding-dino-tiny"

OBJECT_NAMES = [
    "a smartphone",
    "a set of keys",
    "a water bottle",
    "a book",
    "a computer mouse",
]

MODEL_PATH = (
    Path(__file__).resolve().parent
    / "models"
    / "hand_landmarker.task"
)

# Afterimage settings
AFTERIMAGE_OPACITY = 0.45
HAND_PADDING = 35

TRACK_DISTANCE = 120
MAX_MISSED_SCANS = 4
STALE_SECONDS = 2.0


# ==========================================
# HAND / OBJECT OVERLAP
# ==========================================

def finger_near_box(fingers, bbox, padding=HAND_PADDING):
    """Check whether a fingertip is near an object."""

    x1, y1, x2, y2 = bbox

    return any(
        x1 - padding <= finger["x"] <= x2 + padding
        and y1 - padding <= finger["y"] <= y2 + padding
        for finger in fingers
    )


# ==========================================
# HAND TRACKING
# ==========================================

class HandTracker:

    def __init__(self):

        options = mp.tasks.vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(MODEL_PATH)
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_hands=2,
        )

        self.model = (
            mp.tasks.vision.HandLandmarker
            .create_from_options(options)
        )

        self.start = time.monotonic()
        self.last_ms = -1

    def detect(self, frame):

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=rgb
        )

        ms = max(
            int((time.monotonic() - self.start) * 1000),
            self.last_ms + 1
        )

        self.last_ms = ms

        result = self.model.detect_for_video(image, ms)

        height, width = frame.shape[:2]
        fingers = []

        for hand_id, landmarks in enumerate(
            result.hand_landmarks
        ):

            for name, index in (
                ("thumb", 4),
                ("index", 8),
                ("middle", 12)
            ):

                point = landmarks[index]

                fingers.append({
                    "hand": hand_id,
                    "finger": name,
                    "x": int(point.x * width),
                    "y": int(point.y * height),
                })

        return fingers

    def close(self):
        self.model.close()


# ==========================================
# ASYNCHRONOUS GROUNDING DINO
# ==========================================

class DinoWorker:

    def __init__(self):

        self.inbox = queue.Queue(maxsize=1)
        self.outbox = queue.Queue(maxsize=1)

        self.running = True
        self.error = None
        self.status = "Loading Grounding DINO..."

        self.thread = threading.Thread(
            target=self._run,
            daemon=True
        )

        self.thread.start()

    def submit(self, frame, fingers):

        # Discard old waiting frames.
        if self.inbox.full():
            try:
                self.inbox.get_nowait()
            except queue.Empty:
                pass

        try:
            self.inbox.put_nowait((
                frame.copy(),
                [dict(f) for f in fingers],
                time.monotonic()
            ))
        except queue.Full:
            pass

    def latest_result(self):

        try:
            return self.outbox.get_nowait()
        except queue.Empty:
            return None

    def _run(self):

        try:

            processor = AutoProcessor.from_pretrained(
                MODEL_ID
            )

            model = (
                AutoModelForZeroShotObjectDetection
                .from_pretrained(MODEL_ID)
            )

            model = model.to(DEVICE).eval()

            self.status = "Grounding DINO ready"

            while self.running:

                try:
                    frame, capture_fingers, captured_at = (
                        self.inbox.get(timeout=0.2)
                    )
                except queue.Empty:
                    continue

                start = time.perf_counter()

                h, w = frame.shape[:2]

                rgb = cv2.cvtColor(
                    frame,
                    cv2.COLOR_BGR2RGB
                )

                inputs = processor(
                    images=Image.fromarray(rgb),
                    text=[OBJECT_NAMES],
                    return_tensors="pt"
                ).to(DEVICE)

                with torch.inference_mode():
                    outputs = model(**inputs)

                result = (
                    processor
                    .post_process_grounded_object_detection(
                        outputs,
                        inputs.input_ids,
                        threshold=0.35,
                        text_threshold=0.25,
                        target_sizes=[(h, w)]
                    )
                )[0]

                labels = result.get(
                    "text_labels",
                    result["labels"]
                )

                detections = []

                for box, score, label in zip(
                    result["boxes"],
                    result["scores"],
                    labels
                ):

                    x1, y1, x2, y2 = [
                        int(v) for v in box.cpu().tolist()
                    ]

                    x1 = max(0, x1)
                    x2 = min(w, x2)
                    y1 = max(0, y1)
                    y2 = min(h, y2)

                    if x2 <= x1 or y2 <= y1:
                        continue

                    detections.append({
                        "label": str(label).strip().lower(),
                        "bbox": [x1, y1, x2, y2],
                        "center": [
                            (x1 + x2) // 2,
                            (y1 + y2) // 2
                        ],
                        "confidence": float(score.item())
                    })

                # Include the original image and fingertips.
                # This prevents the afterimage from being
                # captured from the wrong camera frame.
                completed = (
                    detections,
                    captured_at,
                    time.perf_counter() - start,
                    frame,
                    capture_fingers
                )

                if self.outbox.full():
                    try:
                        self.outbox.get_nowait()
                    except queue.Empty:
                        pass

                self.outbox.put_nowait(completed)

        except Exception as exc:

            self.error = (
                f"{type(exc).__name__}: {exc}"
            )

            self.status = "Grounding DINO error"

    def close(self):

        self.running = False
        self.thread.join(timeout=1)


# ==========================================
# OBJECT TRACKING
# ==========================================

class ObjectTracker:

    def __init__(self):

        self.next_id = 1
        self.tracks = {}

    def update(self, detections, protected_ids=()):

        protected_ids = set(protected_ids)

        for track in self.tracks.values():
            track["visible"] = False
            track["missed"] += 1

        options = []

        for i, detection in enumerate(detections):

            for object_id, track in self.tracks.items():

                if detection["label"] != track["label"]:
                    continue

                distance = math.dist(
                    detection["center"],
                    track["center"]
                )

                if distance < TRACK_DISTANCE:

                    options.append((
                        distance,
                        i,
                        object_id
                    ))

        used_detections = set()
        used_ids = set()

        for _, i, object_id in sorted(options):

            if i in used_detections:
                continue

            if object_id in used_ids:
                continue

            self.tracks[object_id].update(
                detections[i]
            )

            self.tracks[object_id].update(
                visible=True,
                missed=0
            )

            used_detections.add(i)
            used_ids.add(object_id)

        # Create new object IDs.
        for i, detection in enumerate(detections):

            if i in used_detections:
                continue

            self.tracks[self.next_id] = {
                **detection,
                "id": self.next_id,
                "visible": True,
                "missed": 0
            }

            self.next_id += 1

        # Keep missing objects longer when covered.
        for object_id in list(self.tracks):

            track = self.tracks[object_id]

            if (
                object_id in protected_ids
                and not track["visible"]
            ):
                track["missed"] = 0

            if track["missed"] > MAX_MISSED_SCANS:
                del self.tracks[object_id]

        return [
            dict(track)
            for track in self.tracks.values()
        ]


# ==========================================
# AFTERIMAGE RENDERING
# ==========================================

def draw_afterimage(
    frame,
    saved_image,
    bbox,
    opacity=AFTERIMAGE_OPACITY
):

    height, width = frame.shape[:2]

    x1, y1, x2, y2 = bbox

    x1 = max(0, x1)
    x2 = min(width, x2)
    y1 = max(0, y1)
    y2 = min(height, y2)

    if x2 <= x1 or y2 <= y1 or saved_image.size == 0:
        return False

    region = frame[y1:y2, x1:x2]

    saved = cv2.resize(
        saved_image,
        (x2 - x1, y2 - y1)
    )

    # Blend the saved object with the live frame.
    cv2.addWeighted(
        saved,
        opacity,
        region,
        1.0 - opacity,
        0,
        dst=region
    )

    return True


# ==========================================
# MAIN EMPYREAN PROGRAM
# ==========================================

def main():

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Missing MediaPipe model: {MODEL_PATH}"
        )

    cap = cv2.VideoCapture(
        CAMERA_INDEX,
        cv2.CAP_AVFOUNDATION
    )

    if not cap.isOpened():
        raise RuntimeError(
            "Camera unavailable. Try CAMERA_INDEX = 1 or 2."
        )

    # Logitech camera settings
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    hands = None
    worker = None

    try:

        hands = HandTracker()
        worker = DinoWorker()
        tracker = ObjectTracker()

        # Stores each object's last clear appearance.
        afterimages = {}

        frame_number = 0
        latest_scan_at = None
        infer_seconds = None
        tracked = []

        fps = 0.0
        measured = 0

        fps_start = time.perf_counter()
        last_submit = 0.0

        while True:

            success, frame = cap.read()

            if not success:
                print("Camera frame unavailable")
                break

            if MIRROR:
                frame = cv2.flip(frame, 1)

            # Preserve original camera image.
            raw = frame.copy()

            # Detect fingertips.
            fingers = hands.detect(raw)

            now = time.monotonic()

            if worker.error:
                print("DINO failed:", worker.error)
                break

            # Submit camera frames asynchronously.
            if now - last_submit >= 0.1:

                worker.submit(raw, fingers)
                last_submit = now

            # Retrieve newest object detections.
            result = worker.latest_result()

            if result is not None:

                (
                    detections,
                    latest_scan_at,
                    infer_seconds,
                    scan_frame,
                    scan_fingers
                ) = result

                # Protect objects currently covered by hands.
                protected = {
                    obj["id"]
                    for obj in tracked
                    if finger_near_box(
                        fingers,
                        obj["bbox"]
                    )
                }

                tracked = tracker.update(
                    detections,
                    protected_ids=protected
                )

                # Save clear object images from the
                # exact frame DINO analyzed.
                for obj in tracked:

                    if not obj["visible"]:
                        continue

                    x1, y1, x2, y2 = obj["bbox"]

                    if finger_near_box(
                        scan_fingers,
                        obj["bbox"]
                    ):
                        continue

                    crop = scan_frame[
                        y1:y2,
                        x1:x2
                    ].copy()

                    if crop.size > 0:

                        afterimages[obj["id"]] = {
                            "image": crop,
                            "bbox": list(obj["bbox"])
                        }

                # Remove expired object memories.
                active_ids = {
                    obj["id"]
                    for obj in tracked
                }

                afterimages = {
                    object_id: memory
                    for object_id, memory
                    in afterimages.items()
                    if object_id in active_ids
                }

            scan_age = (
                now - latest_scan_at
                if latest_scan_at is not None
                else None
            )

            stale = (
                scan_age is None
                or scan_age > STALE_SECONDS
            )

            # ==================================
            # DRAW OBJECTS AND AFTERIMAGES
            # ==================================

            for obj in tracked:

                object_id = obj["id"]

                covered = finger_near_box(
                    fingers,
                    obj["bbox"]
                )

                memory = afterimages.get(object_id)

                if covered and memory is not None:

                    # Display previous image when covered.
                    draw_afterimage(
                        frame,
                        memory["image"],
                        memory["bbox"]
                    )

                    x1, y1, x2, y2 = memory["bbox"]

                    color = (255, 255, 0)
                    status = "AFTERIMAGE / LAST SEEN"

                elif obj["visible"] and not stale:

                    x1, y1, x2, y2 = obj["bbox"]

                    color = (255, 0, 0)
                    status = "VISIBLE"

                else:

                    # Hide old boxes when not covered.
                    continue

                cv2.rectangle(
                    frame,
                    (x1, y1),
                    (x2, y2),
                    color,
                    2
                )

                title = (
                    f"{object_id}: "
                    f"{obj['label']} "
                    f"{obj['confidence']:.2f} "
                    f"[{status}]"
                )

                cv2.putText(
                    frame,
                    title,
                    (x1, max(y1 - 8, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    color,
                    2
                )

            # ==================================
            # DRAW FINGERTIPS
            # ==================================

            for finger in fingers:

                x = finger["x"]
                y = finger["y"]

                cv2.circle(
                    frame,
                    (x, y),
                    7,
                    (0, 255, 0),
                    -1
                )

                cv2.putText(
                    frame,
                    finger["finger"],
                    (x + 8, max(y - 8, 18)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 0),
                    1
                )

            # ==================================
            # PERFORMANCE METRICS
            # ==================================

            measured += 1

            if now - fps_start >= 1.0:

                fps = measured / (now - fps_start)
                fps_start = now
                measured = 0

            lines = [
                f"Camera FPS: {fps:.1f}",
                worker.status
            ]

            if infer_seconds is not None:
                lines.append(
                    f"DINO scan: {infer_seconds:.1f}s"
                )

            if scan_age is not None:
                lines.append(
                    f"Scan age: {scan_age:.1f}s"
                )

            for i, line in enumerate(lines):

                cv2.putText(
                    frame,
                    line,
                    (15, 30 + 28 * i),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2
                )

            # ==================================
            # DATA FOR PERSON 2
            # ==================================

            vision_data = {
                "frame": frame_number,
                "fingertips": fingers,
                "objects": tracked,
                "scan_age_seconds": scan_age,
                "objects_stale": stale,
                "afterimage_ids": [
                    obj["id"]
                    for obj in tracked
                    if (
                        finger_near_box(
                            fingers,
                            obj["bbox"]
                        )
                        and obj["id"] in afterimages
                    )
                ]
            }

            if frame_number % 120 == 0:
                print(vision_data)

            cv2.imshow("Empyrean", frame)

            frame_number += 1

            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

    finally:

        cap.release()

        if hands is not None:
            hands.close()

        if worker is not None:
            worker.close()

        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()