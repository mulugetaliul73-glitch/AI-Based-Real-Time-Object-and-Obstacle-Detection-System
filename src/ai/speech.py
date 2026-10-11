"""
=============================================================================
 speech.py — Multi-Language Text-to-Speech Alerts
=============================================================================

 Project : AI-Based Real-Time Object and Obstacle Detection System
           for Visually Impaired People

 Supports 26 world languages. The frontend picks a language code and the
 backend returns an alert message in that language.
=============================================================================
"""

from __future__ import annotations

import logging
import os
import queue
import threading
import time

logger = logging.getLogger(__name__)

SPEECH_ENABLED = os.getenv("SPEECH_ENABLED", "1") == "1"
COOLDOWN_SECONDS = float(os.getenv("SPEECH_COOLDOWN", "3"))


# ═════════════════════════════════════════════════════════════════════════════
# LANGUAGE TEMPLATES
# ═════════════════════════════════════════════════════════════════════════════
# Each language has three templates:
#   danger  : very close alert
#   warning : nearby alert
#   safe    : distant object info
#
# Placeholders:
#   {label}     - object name (person, car, chair, ...)
#   {distance}  - meters (e.g. "2.4")
#   {direction} - left / ahead / right (already translated)
# ═════════════════════════════════════════════════════════════════════════════

TEMPLATES: dict[str, dict[str, str]] = {
    # ── English ────────────────────────────────────────────
    "en": {
        "danger":  "Stop! {label} very close {direction}, {distance} meters.",
        "warning": "Careful. {label} {direction}, {distance} meters.",
        "safe":    "{label} detected {direction}, {distance} meters away.",
        "clear":   "Path is clear.",
    },
    # ── Amharic (Ethiopia) ─────────────────────────────────
    "am": {
        "danger":  "ቁም! {label} በጣም ቅርብ {direction}, {distance} ሜትር።",
        "warning": "ጥንቃቄ። {label} {direction}, {distance} ሜትር።",
        "safe":    "{label} {direction}, {distance} ሜትር ርቀት።",
        "clear":   "መንገዱ ነፃ ነው።",
    },
    # ── Tigrinya (Ethiopia/Eritrea) ────────────────────────
    "ti": {
        "danger":  "ቁም! {label} ኣዝዩ ቀረባ {direction}, {distance} ሜተር።",
        "warning": "ተጠንቀቕ። {label} {direction}, {distance} ሜተር።",
        "safe":    "{label} {direction}, {distance} ሜተር ርሕቀት።",
        "clear":   "መንገዲ ናጻ እዩ።",
    },
    # ── Oromo (Ethiopia) ───────────────────────────────────
    "om": {
        "danger":  "Dhaabi! {label} baay'ee dhihoo {direction}, {distance} meetira.",
        "warning": "Of eeggadhu. {label} {direction}, {distance} meetira.",
        "safe":    "{label} {direction}, {distance} meetira fagoo.",
        "clear":   "Karaan qulqulluu dha.",
    },
    # ── Somali ─────────────────────────────────────────────
    "so": {
        "danger":  "Jooji! {label} aad u dhow {direction}, {distance} mitir.",
        "warning": "Taxadar. {label} {direction}, {distance} mitir.",
        "safe":    "{label} {direction}, {distance} mitir fog.",
        "clear":   "Waddadu waa bannaan.",
    },
    # ── Arabic ─────────────────────────────────────────────
    "ar": {
        "danger":  "توقف! {label} قريب جداً {direction}، {distance} متر.",
        "warning": "احترس. {label} {direction}، {distance} متر.",
        "safe":    "تم اكتشاف {label} {direction}، {distance} متر.",
        "clear":   "الطريق واضح.",
    },
    # ── Spanish ────────────────────────────────────────────
    "es": {
        "danger":  "¡Alto! {label} muy cerca {direction}, {distance} metros.",
        "warning": "Cuidado. {label} {direction}, {distance} metros.",
        "safe":    "{label} detectado {direction}, a {distance} metros.",
        "clear":   "El camino está despejado.",
    },
    # ── French ─────────────────────────────────────────────
    "fr": {
        "danger":  "Arrêtez! {label} très proche {direction}, {distance} mètres.",
        "warning": "Attention. {label} {direction}, {distance} mètres.",
        "safe":    "{label} détecté {direction}, à {distance} mètres.",
        "clear":   "Le chemin est libre.",
    },
    # ── Portuguese ─────────────────────────────────────────
    "pt": {
        "danger":  "Pare! {label} muito perto {direction}, {distance} metros.",
        "warning": "Cuidado. {label} {direction}, {distance} metros.",
        "safe":    "{label} detectado {direction}, a {distance} metros.",
        "clear":   "O caminho está livre.",
    },
    # ── German ─────────────────────────────────────────────
    "de": {
        "danger":  "Stopp! {label} sehr nah {direction}, {distance} Meter.",
        "warning": "Vorsicht. {label} {direction}, {distance} Meter.",
        "safe":    "{label} erkannt {direction}, {distance} Meter entfernt.",
        "clear":   "Der Weg ist frei.",
    },
    # ── Italian ────────────────────────────────────────────
    "it": {
        "danger":  "Fermo! {label} molto vicino {direction}, {distance} metri.",
        "warning": "Attenzione. {label} {direction}, {distance} metri.",
        "safe":    "{label} rilevato {direction}, a {distance} metri.",
        "clear":   "Il percorso è libero.",
    },
    # ── Russian ────────────────────────────────────────────
    "ru": {
        "danger":  "Стоп! {label} очень близко {direction}, {distance} метров.",
        "warning": "Осторожно. {label} {direction}, {distance} метров.",
        "safe":    "{label} обнаружен {direction}, {distance} метров.",
        "clear":   "Путь свободен.",
    },
    # ── Chinese (Simplified) ───────────────────────────────
    "zh": {
        "danger":  "停！{label}非常近，{direction}，{distance}米。",
        "warning": "小心。{label} {direction}，{distance}米。",
        "safe":    "检测到{label} {direction}，{distance}米远。",
        "clear":   "道路畅通。",
    },
    # ── Japanese ───────────────────────────────────────────
    "ja": {
        "danger":  "止まれ！{label}がすぐ{direction}に{distance}メートル。",
        "warning": "注意。{label}が{direction}に{distance}メートル。",
        "safe":    "{label}を{direction}に{distance}メートルで検出。",
        "clear":   "道は空いています。",
    },
    # ── Korean ─────────────────────────────────────────────
    "ko": {
        "danger":  "정지! {label}가 {direction}에 {distance}미터로 매우 가깝습니다.",
        "warning": "주의. {label}가 {direction}에 {distance}미터.",
        "safe":    "{label}가 {direction}에 {distance}미터 거리에서 감지되었습니다.",
        "clear":   "길이 비어 있습니다.",
    },
    # ── Hindi ──────────────────────────────────────────────
    "hi": {
        "danger":  "रुकें! {label} बहुत पास {direction}, {distance} मीटर।",
        "warning": "सावधान। {label} {direction}, {distance} मीटर।",
        "safe":    "{label} {direction}, {distance} मीटर दूर पाया गया।",
        "clear":   "रास्ता साफ है।",
    },
    # ── Swahili ────────────────────────────────────────────
    "sw": {
        "danger":  "Simama! {label} karibu sana {direction}, mita {distance}.",
        "warning": "Kuwa mwangalifu. {label} {direction}, mita {distance}.",
        "safe":    "{label} imegunduliwa {direction}, mita {distance}.",
        "clear":   "Njia ni wazi.",
    },
    # ── Turkish ────────────────────────────────────────────
    "tr": {
        "danger":  "Dur! {label} çok yakın {direction}, {distance} metre.",
        "warning": "Dikkat. {label} {direction}, {distance} metre.",
        "safe":    "{label} {direction}, {distance} metre uzaklıkta.",
        "clear":   "Yol açık.",
    },
    # ── Vietnamese ─────────────────────────────────────────
    "vi": {
        "danger":  "Dừng lại! {label} rất gần {direction}, {distance} mét.",
        "warning": "Cẩn thận. {label} {direction}, {distance} mét.",
        "safe":    "Phát hiện {label} {direction}, cách {distance} mét.",
        "clear":   "Đường thông thoáng.",
    },
    # ── Indonesian ─────────────────────────────────────────
    "id": {
        "danger":  "Berhenti! {label} sangat dekat {direction}, {distance} meter.",
        "warning": "Hati-hati. {label} {direction}, {distance} meter.",
        "safe":    "{label} terdeteksi {direction}, {distance} meter jauhnya.",
        "clear":   "Jalanan kosong.",
    },
    # ── Urdu ───────────────────────────────────────────────
    "ur": {
        "danger":  "رکو! {label} بہت قریب {direction}، {distance} میٹر۔",
        "warning": "احتیاط۔ {label} {direction}، {distance} میٹر۔",
        "safe":    "{label} {direction}، {distance} میٹر کی دوری پر۔",
        "clear":   "راستہ صاف ہے۔",
    },
    # ── Persian/Farsi ──────────────────────────────────────
    "fa": {
        "danger":  "بایست! {label} بسیار نزدیک {direction}، {distance} متر.",
        "warning": "مراقب باش. {label} {direction}، {distance} متر.",
        "safe":    "{label} {direction}، {distance} متر تشخیص داده شد.",
        "clear":   "مسیر آزاد است.",
    },
    # ── Hebrew ─────────────────────────────────────────────
    "he": {
        "danger":  "עצור! {label} קרוב מאוד {direction}, {distance} מטר.",
        "warning": "זהירות. {label} {direction}, {distance} מטר.",
        "safe":    "{label} זוהה {direction}, במרחק {distance} מטר.",
        "clear":   "הדרך פנויה.",
    },
    # ── Polish ─────────────────────────────────────────────
    "pl": {
        "danger":  "Stop! {label} bardzo blisko {direction}, {distance} metrów.",
        "warning": "Ostrożnie. {label} {direction}, {distance} metrów.",
        "safe":    "{label} wykryty {direction}, {distance} metrów.",
        "clear":   "Droga wolna.",
    },
    # ── Dutch ──────────────────────────────────────────────
    "nl": {
        "danger":  "Stop! {label} heel dichtbij {direction}, {distance} meter.",
        "warning": "Voorzichtig. {label} {direction}, {distance} meter.",
        "safe":    "{label} gedetecteerd {direction}, {distance} meter.",
        "clear":   "Het pad is vrij.",
    },
    # ── Ukrainian ──────────────────────────────────────────
    "uk": {
        "danger":  "Стоп! {label} дуже близько {direction}, {distance} метрів.",
        "warning": "Обережно. {label} {direction}, {distance} метрів.",
        "safe":    "{label} виявлено {direction}, {distance} метрів.",
        "clear":   "Шлях вільний.",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# DIRECTION WORDS (per language)
# ═════════════════════════════════════════════════════════════════════════════
DIRECTIONS: dict[str, dict[str, str]] = {
    "en": {"left": "on your left",     "ahead": "ahead",     "right": "on your right"},
    "am": {"left": "በግራ በኩል",           "ahead": "በፊት",       "right": "በቀኝ በኩል"},
    "ti": {"left": "በጸጋኻ",             "ahead": "ቀዳማይ",      "right": "በየማንካ"},
    "om": {"left": "bitaa kee",         "ahead": "fuuldura",   "right": "mirga kee"},
    "so": {"left": "bidixdaada",        "ahead": "hore",       "right": "midigtaada"},
    "ar": {"left": "على يسارك",         "ahead": "أمامك",       "right": "على يمينك"},
    "es": {"left": "a tu izquierda",    "ahead": "al frente",  "right": "a tu derecha"},
    "fr": {"left": "à votre gauche",    "ahead": "devant",     "right": "à votre droite"},
    "pt": {"left": "à sua esquerda",    "ahead": "à frente",   "right": "à sua direita"},
    "de": {"left": "links",             "ahead": "voraus",     "right": "rechts"},
    "it": {"left": "alla tua sinistra", "ahead": "davanti",    "right": "alla tua destra"},
    "ru": {"left": "слева",             "ahead": "впереди",    "right": "справа"},
    "zh": {"left": "在你的左边",         "ahead": "在前面",      "right": "在你的右边"},
    "ja": {"left": "左側に",             "ahead": "前方に",      "right": "右側に"},
    "ko": {"left": "왼쪽에",             "ahead": "정면에",      "right": "오른쪽에"},
    "hi": {"left": "आपके बाएं",          "ahead": "सामने",       "right": "आपके दाएं"},
    "sw": {"left": "kushoto",           "ahead": "mbele",      "right": "kulia"},
    "tr": {"left": "solunuzda",         "ahead": "önde",       "right": "sağınızda"},
    "vi": {"left": "bên trái",           "ahead": "phía trước", "right": "bên phải"},
    "id": {"left": "di kiri",           "ahead": "di depan",   "right": "di kanan"},
    "ur": {"left": "آپ کے بائیں",        "ahead": "سامنے",       "right": "آپ کے دائیں"},
    "fa": {"left": "سمت چپ شما",        "ahead": "جلو",         "right": "سمت راست شما"},
    "he": {"left": "משמאלך",            "ahead": "מלפניך",       "right": "מימינך"},
    "pl": {"left": "po lewej",          "ahead": "z przodu",   "right": "po prawej"},
    "nl": {"left": "links",             "ahead": "voor",       "right": "rechts"},
    "uk": {"left": "ліворуч",           "ahead": "попереду",   "right": "праворуч"},
}


# ═════════════════════════════════════════════════════════════════════════════
# OBJECT NAME TRANSLATIONS (for common objects only)
# ═════════════════════════════════════════════════════════════════════════════
# If a label isn't in here, we use the English name (works fine).
OBJECT_NAMES: dict[str, dict[str, str]] = {
    "am": {  # Amharic
        "person": "ሰው", "car": "መኪና", "bicycle": "ብስክሌት",
        "chair": "ወንበር", "dog": "ውሻ", "cat": "ድመት",
    },
    "ti": {  # Tigrinya
        "person": "ሰብ", "car": "መኪና", "bicycle": "ብስክሌት",
        "chair": "መንበር", "dog": "ከልቢ", "cat": "ድሙ",
    },
    "ar": {
        "person": "شخص", "car": "سيارة", "chair": "كرسي",
    },
    "es": {
        "person": "persona", "car": "coche", "chair": "silla",
        "dog": "perro", "cat": "gato", "bicycle": "bicicleta",
    },
    "fr": {
        "person": "personne", "car": "voiture", "chair": "chaise",
        "dog": "chien", "cat": "chat", "bicycle": "vélo",
    },
    "de": {
        "person": "Person", "car": "Auto", "chair": "Stuhl",
        "dog": "Hund", "cat": "Katze", "bicycle": "Fahrrad",
    },
    "it": {
        "person": "persona", "car": "auto", "chair": "sedia",
        "dog": "cane", "cat": "gatto", "bicycle": "bicicletta",
    },
    "pt": {
        "person": "pessoa", "car": "carro", "chair": "cadeira",
        "dog": "cachorro", "cat": "gato", "bicycle": "bicicleta",
    },
    "ru": {
        "person": "человек", "car": "машина", "chair": "стул",
    },
    "zh": {
        "person": "人", "car": "汽车", "chair": "椅子",
        "dog": "狗", "cat": "猫",
    },
    "ja": {
        "person": "人", "car": "車", "chair": "椅子",
    },
    "ko": {
        "person": "사람", "car": "차", "chair": "의자",
    },
    "hi": {
        "person": "व्यक्ति", "car": "कार", "chair": "कुर्सी",
    },
    "tr": {
        "person": "kişi", "car": "araba", "chair": "sandalye",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# MESSAGE BUILDER
# ═════════════════════════════════════════════════════════════════════════════

def _translate_label(label: str, language: str) -> str:
    """Translate an object label if we have a translation, else keep English."""
    return OBJECT_NAMES.get(language, {}).get(label, label)


def build_message(detections: list[dict], language: str = "en") -> str | None:
    """
    Build a voice alert message in the requested language.

    Args:
        detections: Enriched detections (nearest first).
        language: ISO 639-1 language code (en, am, es, fr, ...).

    Returns:
        The alert text, or None if nothing is urgent.
    """
    # Fall back to English if language isn't supported
    if language not in TEMPLATES:
        language = "en"

    templates = TEMPLATES[language]
    directions = DIRECTIONS.get(language, DIRECTIONS["en"])

    # Announce the nearest object; urgent detections take priority.
    urgent = [d for d in detections if d.get("danger_level") in ("danger", "warning")]
    if not detections:
        return None

    top = urgent[0] if urgent else detections[0]
    level = top.get("danger_level", "safe")
    distance = top.get("distance_m") or 0
    direction_key = top.get("direction", "ahead")
    direction_word = directions.get(direction_key, directions["ahead"])

    # Localize the object name if we have a translation
    label = _translate_label(top.get("label", "obstacle"), language)

    # Build the message
    template = templates.get(level, templates["warning"])
    return template.format(
        label=label,
        distance=f"{distance:.1f}",
        direction=direction_word,
    )


# ═════════════════════════════════════════════════════════════════════════════
# SERVER-SIDE SPEAKER (optional, browser usually speaks)
# ═════════════════════════════════════════════════════════════════════════════

class Speaker:
    """Optional server-side TTS. Browser speechSynthesis is preferred."""

    def __init__(self, enabled: bool = SPEECH_ENABLED, cooldown: float = COOLDOWN_SECONDS):
        self.enabled = enabled
        self.cooldown = cooldown
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=1)
        self._last_message = ""
        self._last_time = 0.0
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.enabled or self._thread:
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def say(self, message: str | None) -> None:
        if not self.enabled or not message:
            return
        now = time.time()
        if message == self._last_message and now - self._last_time < self.cooldown:
            return
        self._last_message, self._last_time = message, now
        try:
            self._queue.put_nowait((message, "en"))  # Server-side default
        except queue.Full:
            pass

    def _worker(self) -> None:
        try:
            import pyttsx3
            engine = pyttsx3.init()
        except Exception as exc:
            logger.warning("Server TTS unavailable: %s", exc)
            self.enabled = False
            return
        while True:
            message, _ = self._queue.get()
            try:
                engine.say(message)
                engine.runAndWait()
            except Exception as exc:
                logger.warning("Speech failed: %s", exc)