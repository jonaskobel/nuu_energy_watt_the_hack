"""Building classes for the area-based heat load (W/m²), ordered worst to best.

The four classes are the challenge guide values (project_description.md, 5.1).
Year gaps (1979, 2000, 2001) and partial renovation are own supplements; they
are flagged so that results can mark them as demonstration assumptions.
"""

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class HeatLoadClass:
    """One guide-value class with its specific heat load range in W/m²."""

    label: str
    low_w_per_m2: float
    high_w_per_m2: float


CLASSES = (
    HeatLoadClass("unsaniert, vor 1979", 120, 180),
    HeatLoadClass("Baujahr 1980er–1990er", 80, 120),
    HeatLoadClass("saniert oder ab 2002", 40, 60),
    HeatLoadClass("Niedrigenergiehaus", 15, 40),
)
UNRENOVATED, MID_AGE, RENOVATED, LOW_ENERGY = range(len(CLASSES))

GAP_NOTE = "Baujahr {year} liegt zwischen den Challenge-Klassen; {reason} der Klasse „{label}“ zugeordnet."
NEAREST_YEAR = "dem nächstliegenden Jahr folgend"


@dataclass(frozen=True)
class Classification:
    """Chosen class index, explanatory notes and whether an own supplement applied."""

    index: int
    notes: Tuple[str, ...]
    own_supplement: bool


def _gap_note(year: int, reason: str, index: int) -> str:
    """Describe how a year outside the challenge classes was assigned."""
    return GAP_NOTE.format(year=year, reason=reason, label=CLASSES[index].label)


def _year_class(year: int) -> Tuple[int, Optional[str]]:
    """Return the class for a construction year and a note if it falls in a gap."""
    if year < 1979:
        return UNRENOVATED, None
    if year == 1979:
        return MID_AGE, _gap_note(year, "der nächsten Klasse", MID_AGE)
    if year <= 1999:
        return MID_AGE, None
    if year == 2000:
        return MID_AGE, _gap_note(year, NEAREST_YEAR, MID_AGE)
    if year == 2001:
        return RENOVATED, _gap_note(year, NEAREST_YEAR, RENOVATED)
    return RENOVATED, None


def classify(year: Optional[int], renovation: str) -> Optional[Classification]:
    """Return the class for year and renovation status, or None if not determinable."""
    if renovation == "low_energy":
        return Classification(LOW_ENERGY, (), False)
    if renovation == "fully":
        return Classification(RENOVATED, (), False)
    if year is None:
        return None
    index, gap_note = _year_class(year)
    notes = [gap_note] if gap_note else []
    own_supplement = gap_note is not None
    if renovation == "partially":
        own_supplement = True
        if index < RENOVATED:
            index += 1
            notes.append(
                "Teilsaniert: eine Klasse besser als die Baujahrsklasse (eigene Ergänzung)."
            )
        else:
            notes.append(
                "Teilsaniert ab Baujahr 2002: keine bessere Klasse als „saniert oder ab 2002“ (eigene Ergänzung)."
            )
    elif renovation == "unknown":
        notes.append("Sanierungsstand unbekannt: nach Baujahr eingestuft.")
    return Classification(index, tuple(notes), own_supplement)
