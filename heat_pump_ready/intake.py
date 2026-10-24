"""Translate UI JSON into UserInput; no extraction or domain assessment occurs here."""

import base64
import binascii
import math
from datetime import date
from .contracts import UserInput, Attachment

ENUMS = {
    "renovation_status": ("unknown", "unrenovated", "partially", "fully", "low_energy"),
    "consumption_unit": ("kwh", "litre", "m3"),
    "energy_carrier": ("gas", "oil", "lpg", "district", "electric"),
    "heat_distribution": ("unknown", "radiators", "underfloor", "mixed"),
    "pipe_system": ("unknown", "single-pipe", "two-pipe"),
}
BOUNDS = {
    "construction_year": (1700, date.today().year),
    "floor_area_m2": (1, 10000),
    "annual_consumption": (0, 10000000),
    "persons_in_household": (0, 100),
    "flow_temperature_c": (10, 100),
    "investment_eur": (0, 1000000),
    "subsidy_eur": (0, 1000000),
    "horizon_years": (1, 50),
}
INTEGER_FIELDS = ("construction_year", "persons_in_household")


def build_user_input(payload: dict) -> UserInput:
    """Build immutable input from JSON. Raises: ValueError for invalid fields/files."""
    if not isinstance(payload, dict):
        raise ValueError("Eingabe muss ein JSON-Objekt sein.")
    values = {}
    for key, (low, high) in BOUNDS.items():
        raw = payload.get(key)
        if raw is None or raw == "":
            continue
        if isinstance(raw, bool):
            raise ValueError(key + ": Zahl erwartet.")
        try:
            value = float(raw)
        except (TypeError, ValueError) as error:
            raise ValueError(key + ": Zahl erwartet.") from error
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key}: Wert muss zwischen {low} und {high} liegen.")
        if key in INTEGER_FIELDS and not value.is_integer():
            raise ValueError(key + ": Ganze Zahl erwartet.")
        values[key] = int(value) if key in INTEGER_FIELDS else value
    for key, allowed in ENUMS.items():
        if key in payload:
            if payload[key] not in allowed:
                raise ValueError(key + ": Unbekannte Auswahl.")
            values[key] = payload[key]
    hot_water = payload.get("hot_water_via_heating")
    if hot_water is not None and type(hot_water) is not bool:
        raise ValueError("Warmwasser muss true, false oder null sein.")
    values["hot_water_via_heating"] = hot_water
    for key in ("location", "notes"):
        value = payload.get(key, "")
        if not isinstance(value, str) or len(value) > 4000:
            raise ValueError(key + ": Ungültiger Text.")
        values[key] = value
    values["attachments"] = parse_attachments(payload.get("attachments", []))
    return UserInput(**values)


def parse_attachments(files: list) -> tuple:
    """Validate at most six files, each at most 4 MiB. Returns: attachment tuple."""
    if not isinstance(files, list) or len(files) > 6:
        raise ValueError("Maximal sechs Dateien erlaubt.")
    result = []
    signatures = {
        "image/jpeg": b"\xff\xd8\xff",
        "image/png": b"\x89PNG\r\n\x1a\n",
        "application/pdf": b"%PDF-",
    }
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("Ungültige Datei.")
        mime = item.get("media_type")
        category = item.get("category")
        name = item.get("name", "Datei")
        if mime not in signatures or category not in (
            "bill",
            "radiator",
            "pipes",
            "outdoor",
        ):
            raise ValueError("Dateityp oder Bildkategorie nicht unterstützt.")
        if not isinstance(name, str) or len(name) > 255:
            raise ValueError("Ungültiger Dateiname.")
        try:
            content = base64.b64decode(item.get("data", ""), validate=True)
        except (ValueError, TypeError, binascii.Error) as error:
            raise ValueError("Datei ist nicht gültig kodiert.") from error
        if not content.startswith(signatures[mime]) or len(content) > 4 * 1024 * 1024:
            raise ValueError("Datei ist ungültig oder größer als 4 MiB.")
        result.append(Attachment(name, mime, category, content))
    return tuple(result)
