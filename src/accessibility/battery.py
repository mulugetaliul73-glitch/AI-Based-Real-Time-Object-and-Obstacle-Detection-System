"""Validation and representation helpers for client-reported battery status."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real


@dataclass(frozen=True)
class BatteryStatus:
    """Normalized client battery level and charging state."""

    level_percent: int
    charging: bool
    is_low: bool


def create_battery_status(
    level: float,
    charging: bool,
    low_threshold: float = 0.2,
) -> BatteryStatus:
    """Convert a fractional battery level (0–1) to a validated status."""
    if isinstance(level, bool) or not isinstance(level, Real) or not math.isfinite(level):
        raise ValueError("Battery level must be a finite number between 0 and 1.")
    if not 0 <= level <= 1:
        raise ValueError("Battery level must be between 0 and 1.")
    if not isinstance(charging, bool):
        raise ValueError("Charging status must be a boolean.")
    if (
        isinstance(low_threshold, bool)
        or not isinstance(low_threshold, Real)
        or not math.isfinite(low_threshold)
        or not 0 <= low_threshold <= 1
    ):
        raise ValueError("Low-battery threshold must be a number between 0 and 1.")

    return BatteryStatus(
        level_percent=round(level * 100),
        charging=charging,
        is_low=level <= low_threshold,
    )
"""
Battery Monitoring — Voice alerts when battery is low.
"""
import logging
import threading
import time

import psutil
import pyttsx3

logger = logging.getLogger(__name__)

LOW_THRESHOLD = 20
CRITICAL_THRESHOLD = 10
CHECK_INTERVAL = 60


class BatteryMonitor:
    """Monitors battery and speaks warnings."""

    def __init__(self):
        self.engine = pyttsx3.init()
        self.engine.setProperty("rate", 150)
        self._thread: threading.Thread | None = None
        self._running = False
        self._last_state: str | None = None

    def _speak(self, text: str) -> None:
        try:
            self.engine.say(text)
            self.engine.runAndWait()
        except Exception as e:
            logger.warning(f"Battery alert failed: {e}")

    def _check_loop(self) -> None:
        while self._running:
            battery = psutil.sensors_battery()
            if battery is None:
                time.sleep(CHECK_INTERVAL)
                continue

            percent = int(battery.percent)
            plugged = battery.power_plugged

            if percent <= CRITICAL_THRESHOLD and self._last_state != "critical":
                self._speak(f"Critical battery. {percent} percent remaining. Please charge now.")
                self._last_state = "critical"
                logger.warning(f"🔴 Battery critical: {percent}%")

            elif percent <= LOW_THRESHOLD and self._last_state != "low":
                self._speak(f"Battery low. {percent} percent remaining.")
                self._last_state = "low"
                logger.warning(f"🟡 Battery low: {percent}%")

            elif plugged and self._last_state in ("low", "critical"):
                self._speak("Charger connected.")
                self._last_state = None
                logger.info("🟢 Charger connected")

            time.sleep(CHECK_INTERVAL)

    def start(self) -> None:
        if self._thread:
            return
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()
        logger.info("🔋 Battery monitor started")

    def stop(self) -> None:
        self._running = False
        logger.info("🔋 Battery monitor stopped")

    def get_status(self) -> dict:
        battery = psutil.sensors_battery()
        if battery is None:
            return {"available": False}
        return {
            "available": True,
            "percent": int(battery.percent),
            "plugged": battery.power_plugged,
        }


_monitor: BatteryMonitor | None = None


def get_battery_monitor() -> BatteryMonitor:
    global _monitor
    if _monitor is None:
        _monitor = BatteryMonitor()
    return _monitor