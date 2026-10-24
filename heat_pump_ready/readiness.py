"""Technical readiness criteria (rule readiness-criteria-v1); no economics, no IO.

Each criterion is met, open or an obstacle. A met criterion is either confirmed
by user facts or a rule-based indicator; its gap says what would confirm it.
"""

from typing import List, Optional, Tuple
from .config import AssessmentConfig
from .contracts import CalculationOutput, CriterionResult, MetricResult, UserInput

MET, OPEN, OBSTACLE = "met", "open", "obstacle"
CONFIRMED, INDICATOR, MISSING = "confirmed", "indicator", "missing"
HEAT_LOAD, TEMPERATURE, HYDRAULICS = "heat_load", "temperature", "hydraulics"
CRITERION_LABELS = {
    HEAT_LOAD: "Heizlast",
    TEMPERATURE: "Temperaturniveau",
    HYDRAULICS: "Hydraulik",
}

FLOW_GAP = "Vorlauftemperatur an einem kalten Tag bestätigen (z. B. 55-Grad-Test)."
PIPE_GAP = "Rohrsystem bestätigen (z. B. Foto vom Heizkörperanschluss)."


def is_available(metric: Optional[MetricResult]) -> bool:
    """Return whether a metric contains an available value; None is unavailable."""
    return metric is not None and metric.status == "available"


def is_confirmed(metric: Optional[MetricResult]) -> bool:
    """Return whether a metric is available and carries no uncertainty note."""
    return is_available(metric) and not metric.uncertainty


def assess_heat_load(results: CalculationOutput) -> CriterionResult:
    """Met when a heat load estimate exists; an uncertain estimate is an indicator."""
    heat_load, specific = results.heat_load, results.specific_heat_load
    if not is_available(heat_load):
        return CriterionResult(
            HEAT_LOAD, OPEN, MISSING, "Heizlast fehlt.", "Beheizte Fläche und Baujahr angeben."
        )
    reason = f"Heizlast ca. {heat_load.value:.1f} kW"
    if is_available(specific):
        reason += f" ({specific.value:.0f} W/m²)"
    if not heat_load.uncertainty:
        return CriterionResult(HEAT_LOAD, MET, CONFIRMED, reason + ".")
    return CriterionResult(
        HEAT_LOAD, MET, INDICATOR, reason + ".", "Heizlast bestätigen. " + heat_load.uncertainty
    )


def assess_temperature(
    results: CalculationOutput, user_input: UserInput, config: AssessmentConfig
) -> CriterionResult:
    """Use a known flow temperature, else underfloor or the specific heat load."""
    flow = user_input.flow_temperature_c
    if flow is not None:
        return temperature_from_flow(flow, results.specific_heat_load, config)
    if user_input.heat_distribution == "underfloor":
        return CriterionResult(
            TEMPERATURE,
            MET,
            INDICATOR,
            "Vorlauf unbekannt; Fußbodenheizung arbeitet üblicherweise mit ca. 35 °C.",
            FLOW_GAP,
        )
    if user_input.heat_distribution == "unknown":
        return CriterionResult(
            TEMPERATURE, OPEN, MISSING, "Heizflächenart ist unbekannt.", "Heizflächenart angeben."
        )
    return temperature_from_load(results.specific_heat_load, config)


def temperature_from_flow(
    flow: float, specific: Optional[MetricResult], config: AssessmentConfig
) -> CriterionResult:
    """Classify a user-confirmed flow temperature against the JAZ thresholds."""
    low, high = config.low_flow_temperature_max_c, config.max_flow_temperature_c
    if flow <= low:
        return CriterionResult(TEMPERATURE, MET, CONFIRMED, f"Vorlauf {flow:g} °C ≤ {low:g} °C.")
    hint = heating_curve_hint(specific, config)
    gap = f"Prüfen, ob größere Heizkörper oder eine flachere Heizkurve {low:g} °C ermöglichen."
    if flow <= high:
        return CriterionResult(
            TEMPERATURE,
            OPEN,
            CONFIRMED,
            f"Vorlauf {flow:g} °C über {low:g} °C: geringere Effizienz (JAZ {config.jaz_high_temperature:g})."
            + hint,
            gap,
        )
    return CriterionResult(
        TEMPERATURE,
        OBSTACLE,
        CONFIRMED,
        f"Vorlauf {flow:g} °C über {high:g} °C: ohne Anpassung der Heizflächen nicht geeignet."
        + hint,
        gap,
    )


def heating_curve_hint(specific: Optional[MetricResult], config: AssessmentConfig) -> str:
    """Return a plausibility hint when a high flow meets a low specific heat load."""
    if not is_available(specific) or specific.value > config.low_temperature_max_w_per_m2:
        return ""
    return (
        f" Bei {specific.value:.0f} W/m² ist das ungewöhnlich hoch; möglicherweise ist nur "
        "die Heizkurve zu steil eingestellt."
    )


def temperature_from_load(
    specific: Optional[MetricResult], config: AssessmentConfig
) -> CriterionResult:
    """Without a flow temperature, a low specific heat load is an indicator."""
    if not is_available(specific):
        return CriterionResult(
            TEMPERATURE, OPEN, MISSING, "Vorlauftemperatur und Heizlast fehlen.", FLOW_GAP
        )
    load, limit = specific.value, config.low_temperature_max_w_per_m2
    low = config.low_flow_temperature_max_c
    if load <= limit:
        return CriterionResult(
            TEMPERATURE,
            MET,
            INDICATOR,
            f"Vorlauf unbekannt; bei {load:.0f} W/m² (≤ {limit:g} W/m²) reichen die "
            f"Heizkörper wahrscheinlich für ≤ {low:g} °C.",
            FLOW_GAP,
        )
    return CriterionResult(
        TEMPERATURE,
        OPEN,
        MISSING,
        f"Vorlauf unbekannt; bei {load:.0f} W/m² (> {limit:g} W/m²) ist offen, ob "
        f"≤ {low:g} °C reichen.",
        FLOW_GAP,
    )


def assess_hydraulics(
    results: CalculationOutput, user_input: UserInput, config: AssessmentConfig
) -> CriterionResult:
    """Underfloor needs no pipe system; else confirmed pipes, else construction year."""
    if user_input.heat_distribution == "underfloor":
        return CriterionResult(
            HYDRAULICS,
            MET,
            CONFIRMED,
            "Nur Fußbodenheizung: Das Rohrsystem von Heizkörpern ist nicht relevant.",
        )
    pipe = results.pipe_system
    if is_confirmed(pipe):
        return hydraulics_from_pipe(pipe.value)
    return hydraulics_from_year(user_input.construction_year, is_available(pipe), config)


def hydraulics_from_pipe(pipe_system: str) -> CriterionResult:
    """Two-pipe is met; a confirmed single-pipe system needs professional review."""
    if pipe_system == "two-pipe":
        return CriterionResult(HYDRAULICS, MET, CONFIRMED, "Zweirohrsystem bestätigt.")
    return CriterionResult(
        HYDRAULICS,
        OPEN,
        CONFIRMED,
        "Einrohrsystem: höherer Vorlauf und schwierigerer Abgleich möglich.",
        "Hydraulik des Einrohrsystems fachlich prüfen.",
    )


def hydraulics_from_year(
    construction_year: Optional[int], model_reading: bool, config: AssessmentConfig
) -> CriterionResult:
    """Unknown or unconfirmed pipes: recent buildings usually have two-pipe systems."""
    reason = "Rohrsystem unbekannt"
    if model_reading:
        reason += " (Bildauswertung noch unbestätigt)"
    if construction_year is not None and construction_year >= config.two_pipe_likely_from_year:
        return CriterionResult(
            HYDRAULICS,
            MET,
            INDICATOR,
            f"{reason}; bei Baujahr {construction_year} ist ein Zweirohrsystem üblich.",
            PIPE_GAP,
        )
    return CriterionResult(HYDRAULICS, OPEN, MISSING, reason + ".", PIPE_GAP)


def assess_criteria(
    results: CalculationOutput, user_input: UserInput, config: AssessmentConfig
) -> Tuple[CriterionResult, ...]:
    """Return heat load, temperature and hydraulics criteria in display order."""
    return (
        assess_heat_load(results),
        assess_temperature(results, user_input, config),
        assess_hydraulics(results, user_input, config),
    )


def combine(criteria: Tuple[CriterionResult, ...]) -> Tuple[str, List[str], List[str]]:
    """Return traffic light, one headline reason and gaps; details stay in criteria.

    Red for an obstacle or when heat load and temperature are both open, green
    when every criterion is met, otherwise yellow.
    """
    states = {criterion.key: criterion.state for criterion in criteria}
    gaps = [criterion.gap for criterion in criteria if criterion.gap]
    obstacles = [criterion.reason for criterion in criteria if criterion.state == OBSTACLE]
    if obstacles:
        return "red", ["Hindernis: " + reason for reason in obstacles], gaps
    if states[HEAT_LOAD] == OPEN and states[TEMPERATURE] == OPEN:
        return "red", [
            "Zu wenige Belege für eine positive Ersteinschätzung: Heizlast und Temperaturniveau sind offen."
        ], gaps
    open_labels = [CRITERION_LABELS[key] for key, state in states.items() if state != MET]
    if open_labels:
        return "yellow", [
            "Kein Hindernis erkennbar, aber noch offen: " + ", ".join(open_labels) + "."
        ], gaps
    if gaps:
        return "green", [
            "Alle technischen Kriterien erfüllt, teilweise nur auf Basis von Indizien."
        ], gaps
    return "green", ["Alle technischen Kriterien erfüllt."], gaps
