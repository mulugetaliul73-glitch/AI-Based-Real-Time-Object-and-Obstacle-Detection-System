"""
=============================================================================
 distance.py — Distance, Direction & Danger-Level Estimation
=============================================================================

 Project : AI-Based Real-Time Object and Obstacle Detection System
           for Visually Impaired People

 Purpose : Estimate how far away each detected object is, which direction
           it is in, and how dangerous it is.

 Method  : Pinhole camera model
              distance = (real_height × focal_length_px) / box_height_px

 Levels  : 🔴 DANGER  — under 2 m   → "Stop!"
           🟡 WARNING — 2.0 – 2.6 m   → "Careful."
           🟢 SAFE    — over 3.0 m    → (silent)
=============================================================================
"""

from __future__ import annotations

import math


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — TUNE THESE TO CHANGE SENSITIVITY
# ═════════════════════════════════════════════════════════════════════════════

# Real-world heights (metres) for common objects.
# The more accurate this is, the better the distance estimate.
KNOWN_HEIGHTS_M: dict[str, float] = {
    # People & animals
    "person": 1.7,
    "dog": 0.5,
    "cat": 0.3,
    "horse": 1.6,
    "cow": 1.4,

    # Vehicles
    "bicycle": 1.0,
    "car": 1.5,
    "motorcycle": 1.2,
    "bus": 3.0,
    "truck": 3.0,

    # Street furniture
    "traffic light": 0.9,
    "fire hydrant": 0.7,
    "stop sign": 0.75,
    "bench": 0.9,

    # Indoor objects
    "chair": 0.9,
    "couch": 0.9,
    "potted plant": 0.6,
    "bed": 0.6,
    "dining table": 0.75,
    "tv": 0.6,
    "refrigerator": 1.7,
}

# Fallback height if the object label isn't in the table above
DEFAULT_HEIGHT_M = 1.0

# Camera's vertical field of view (typical webcam ≈ 60°)
DEFAULT_VERTICAL_FOV_DEG = 60.0

# ─────────────────────────────────────────────────────────────────────────────
# DANGER THRESHOLDS — Change these numbers to adjust sensitivity!
# ─────────────────────────────────────────────────────────────────────────────
#  Examples:
#    More sensitive (more alerts):  DANGER = 2.5,  WARNING = 5.0
#    Less sensitive (fewer alerts): DANGER = 1.0,  WARNING = 2.0
#    Default balanced:              DANGER = 1.5,  WARNING = 3.0
# ─────────────────────────────────────────────────────────────────────────────
DANGER_DISTANCE_M = 2.0    # < this → 🔴 danger
WARNING_DISTANCE_M = 2.6   # < this → 🟡 warning; else 🟢 safe


# ═════════════════════════════════════════════════════════════════════════════
# CORE FUNCTIONS
# ═════════════════════════════════════════════════════════════════════════════

def focal_length_px(
    image_height: int,
    vertical_fov_deg: float = DEFAULT_VERTICAL_FOV_DEG,
) -> float:
    """
    Compute focal length in pixels from image height and vertical FOV.

    Args:
        image_height: Image height in pixels.
        vertical_fov_deg: Camera's vertical field of view in degrees.

    Returns:
        Focal length in pixels.
    """
    return (image_height / 2) / math.tan(math.radians(vertical_fov_deg) / 2)


def estimate_distance(
    label: str,
    bbox: list[float],
    image_height: int,
) -> float | None:
    """
    Estimate distance to an object using the pinhole camera model.

    Args:
        label: Object class name (e.g., "person").
        bbox: Bounding box [x1, y1, x2, y2] in pixels.
        image_height: Image height in pixels.

    Returns:
        Distance in metres (rounded to 2 decimals), or None if invalid.
    """
    box_height = bbox[3] - bbox[1]
    if box_height <= 0 or image_height <= 0:
        return None

    real_height = KNOWN_HEIGHTS_M.get(label, DEFAULT_HEIGHT_M)
    distance = real_height * focal_length_px(image_height) / box_height
    return round(distance, 2)


def get_direction(bbox: list[float], image_width: int) -> str:
    """
    Determine horizontal direction of an object.

    Splits the image into thirds:
        left third    → "left"
        middle third  → "ahead"
        right third   → "right"

    Args:
        bbox: Bounding box [x1, y1, x2, y2] in pixels.
        image_width: Image width in pixels.

    Returns:
        One of "left", "ahead", "right".
    """
    centre = (bbox[0] + bbox[2]) / 2
    ratio = centre / image_width if image_width else 0.5

    if ratio < 0.33:
        return "left"
    if ratio > 0.66:
        return "right"
    return "ahead"


def get_danger_level(distance: float | None) -> str:
    """
    Classify a distance as 'danger', 'warning', or 'safe'.

    Uses the DANGER_DISTANCE_M and WARNING_DISTANCE_M constants defined
    at the top of this file.

    Args:
        distance: Distance in metres, or None if unknown.

    Returns:
        One of "danger", "warning", "safe".
    """
    if distance is None:
        return "safe"
    if distance < DANGER_DISTANCE_M:
        return "danger"
    if distance < WARNING_DISTANCE_M:
        return "warning"
    return "safe"


def enrich_detections(
    detections: list[dict],
    image_width: int,
    image_height: int,
) -> list[dict]:
    """
    Add distance, direction, and danger level to raw YOLO detections.

    Also sorts the result so the NEAREST object comes first.

    Args:
        detections: List of raw detections from YOLO. Each must have:
                    { "label": str, "confidence": float, "bbox": [x1,y1,x2,y2] }
        image_width: Image width in pixels.
        image_height: Image height in pixels.

    Returns:
        The same list with three extra fields on each item:
            distance_m, direction, danger_level
        Sorted by distance (nearest first).
    """
    enriched: list[dict] = []

    for det in detections:
        distance = estimate_distance(det["label"], det["bbox"], image_height)
        enriched.append(
            {
                **det,
                "distance_m": distance,
                "direction": get_direction(det["bbox"], image_width),
                "danger_level": get_danger_level(distance),
            }
        )

    # Sort nearest-first; None distances go to the end
    enriched.sort(
        key=lambda d: d["distance_m"] if d["distance_m"] is not None else float("inf")
    )
    return enriched