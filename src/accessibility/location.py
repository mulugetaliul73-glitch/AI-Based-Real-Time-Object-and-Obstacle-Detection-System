"""Coordinate validation and distance helpers for client-provided locations."""

from __future__ import annotations

import math
from numbers import Real

EARTH_RADIUS_M = 6_371_000


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    """Return finite decimal-degree coordinates or raise ValueError."""
    values = (latitude, longitude)
    names = ("latitude", "longitude")
    coordinates: list[float] = []

    for name, value in zip(names, values, strict=True):
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ValueError(f"{name} must be a finite number.")
        coordinate = float(value)
        if not math.isfinite(coordinate):
            raise ValueError(f"{name} must be a finite number.")
        coordinates.append(coordinate)

    latitude_value, longitude_value = coordinates
    if not -90 <= latitude_value <= 90:
        raise ValueError("latitude must be between -90 and 90 degrees.")
    if not -180 <= longitude_value <= 180:
        raise ValueError("longitude must be between -180 and 180 degrees.")
    return latitude_value, longitude_value


def distance_between_coordinates_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    """Calculate the great-circle distance between two coordinates in metres."""
    latitude_a, longitude_a = validate_coordinates(latitude_a, longitude_a)
    latitude_b, longitude_b = validate_coordinates(latitude_b, longitude_b)

    lat_a, lat_b = math.radians(latitude_a), math.radians(latitude_b)
    delta_lat = lat_b - lat_a
    delta_lon = math.radians(longitude_b - longitude_a)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(delta_lon / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    central_angle = 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))
    return EARTH_RADIUS_M * central_angle
"""
Location — GPS coordinate capture from image EXIF metadata.
"""
import json
import logging
import os
from typing import Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

logger = logging.getLogger(__name__)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
NOMINATIM_USER_AGENT = os.getenv(
    "NOMINATIM_USER_AGENT",
    "AI-Obstacle-Detection/1.0 (assistive navigation app)",
)


def _convert_to_degrees(value) -> float:
    d, m, s = value
    return d + (m / 60.0) + (s / 3600.0)


def get_gps_from_image(image_path: str) -> Optional[dict]:
    """Extract GPS coordinates from image EXIF."""
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)
            if tag == "GPSInfo":
                for key, val in value.items():
                    gps_tag = GPSTAGS.get(key, key)
                    gps_info[gps_tag] = val

        if "GPSLatitude" not in gps_info:
            return None

        lat = _convert_to_degrees(gps_info["GPSLatitude"])
        lon = _convert_to_degrees(gps_info["GPSLongitude"])

        if gps_info.get("GPSLatitudeRef") == "S":
            lat = -lat
        if gps_info.get("GPSLongitudeRef") == "W":
            lon = -lon

        return {"latitude": round(lat, 6), "longitude": round(lon, 6)}

    except Exception as e:
        logger.error(f"GPS extraction failed: {e}")
        return None


def reverse_geocode(
    latitude: float,
    longitude: float,
    language: str = "en",
) -> Optional[str]:
    """Convert coordinates to a human-readable OpenStreetMap address."""
    try:
        latitude, longitude = validate_coordinates(latitude, longitude)
        query = urlencode(
            {
                "format": "jsonv2",
                "lat": latitude,
                "lon": longitude,
                "zoom": 18,
                "addressdetails": 1,
            }
        )
        request = Request(
            f"{NOMINATIM_URL}?{query}",
            headers={
                "User-Agent": NOMINATIM_USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": language,
            },
        )
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read(1024 * 1024))
        address = None
        if isinstance(payload, dict):
            address = payload.get("display_name") or payload.get("name")
        if isinstance(address, str) and address.strip():
            return address.strip()
        logger.info("OpenStreetMap returned no address for coordinates.")
    except (OSError, ValueError) as error:
        logger.warning("Reverse geocoding failed: %s", error)
    except Exception:
        logger.exception("Unexpected reverse geocoding failure.")
    return None


def describe_location(latitude: float, longitude: float) -> str:
    """Human-friendly location description for voice output."""
    address = reverse_geocode(latitude, longitude)
    if address:
        return f"Your current location is {address}."
    return f"Coordinates: latitude {latitude}, longitude {longitude}."
