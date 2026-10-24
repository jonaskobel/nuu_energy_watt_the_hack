"""Only this module interprets metrics as technical and economic decisions."""

import math
from typing import List, Tuple
from .contracts import CalculationOutput, CriterionResult, InvestmentDecision, UserInput
from .config import AssessmentConfig
from .readiness import assess_criteria, combine, is_available

CHECKS = (
    "Exakte Heizlast und raumweise Heizkörperleistung prüfen.",
    "Elektrischen Anschluss und Zählerschrank prüfen.",
    "Hydraulik, Außenaufstellung, Schall und Genehmigungen prüfen.",
)
REQUIRED = (
    "annual_consumption",
    "space_heating_demand",
    "annual_performance_factor",
    "annual_savings",
    "net_investment",
    "payback_period",
    "horizon",
)


def check_plausibility(results: CalculationOutput) -> List[str]:
    """Find nonfinite, negative or inverted metric values."""
    issues = []
    for key in results.__dataclass_fields__:
        metric = results.get(key)
        if not is_available(metric):
            continue
        values = metric.value if isinstance(metric.value, tuple) else (metric.value,)
        for value in values:
            if not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value):
                issues.append(metric.key + ": Nicht endlicher Wert.")
            if value < 0 and metric.key != "annual_savings":
                issues.append(metric.key + ": Negativer Wert ist fachlich unplausibel.")
        if isinstance(metric.value, tuple) and metric.value[0] > metric.value[1]:
            issues.append(metric.key + ": Ungültige Spannengrenzen.")
    return issues


def heat_load_notes(results: CalculationOutput, config: AssessmentConfig) -> List[str]:
    """Return a non-blocking note if consumption and class band disagree strongly.

    The heat load estimate already resolves the disagreement by rule; the note
    only keeps it visible, so it never blocks a decision.
    """
    consumption, area = results.heat_load_consumption, results.heat_load_area
    if not (is_available(consumption) and is_available(area)):
        return []
    low, high = area.value
    if (
        consumption.value > high * config.discrepancy_ratio
        or consumption.value * config.discrepancy_ratio < low
    ):
        return [
            "Heizlastmethoden weichen stark voneinander ab; Verbrauchsdaten und "
            "Gebäudeklasse prüfen. Die Heizlast-Schätzung folgt der Regel heat-load-m4-demo-v1."
        ]
    return []


def assess_readiness(
    results: CalculationOutput,
    issues: List[str],
    user_input: UserInput,
    config: AssessmentConfig,
) -> Tuple[str, List[str], Tuple[CriterionResult, ...], List[str]]:
    """Return traffic light, reasons, criteria and gaps, independently of economics.

    Contradictory metrics keep the light at yellow; the criteria stay visible.
    """
    criteria = assess_criteria(results, user_input, config)
    readiness, reasons, gaps = combine(criteria)
    if issues:
        return "yellow", reasons, criteria, gaps
    return readiness, reasons, criteria, gaps


def decide_economics(
    results: CalculationOutput, readiness: str
) -> Tuple[str, str, str]:
    """Apply simple payback rules only after required metrics passed validation."""
    payback = results.payback_period.value
    if results.annual_savings.value <= 0 or (
        isinstance(payback, (int, float)) and payback > results.horizon.value
    ):
        return (
            "not_worthwhile",
            "Im vereinfachten Rechenmodell lohnt sich die Investition im gewählten Zeitraum nicht.",
            "Keine positive Ersparnis oder Amortisation außerhalb des Betrachtungszeitraums.",
        )
    if readiness == "green":
        return (
            "worthwhile",
            "Im vereinfachten Rechenmodell lohnt sich die Investition unter den angegebenen Annahmen.",
            "Positive Ersparnis und Amortisation innerhalb des Betrachtungszeitraums.",
        )
    return (
        "undetermined",
        "Noch nicht beurteilbar: Die technische Eignung bleibt offen.",
        "Wirtschaftliche Kennzahlen liegen vor; technische Eignung ist noch offen.",
    )


def validate_and_decide(
    results: CalculationOutput, config: AssessmentConfig, user_input: UserInput
) -> InvestmentDecision:
    """Compose plausibility, readiness and economic rules without IO or recalculation.

    Args:
        results: Immutable completed metrics; unavailable fields stay unavailable.
        config: Validated rule thresholds and challenge assumptions.
        user_input: Read-only user facts (heating surfaces, flow temperature, year).
    Returns:
        A separate decision with provenance and outstanding professional checks.
    """
    issues = check_plausibility(results)
    missing = [key for key in REQUIRED if not is_available(results.get(key))]
    readiness, reasons, criteria, gaps = assess_readiness(
        results, issues, user_input, config
    )
    reasons.extend(heat_load_notes(results, config))
    uncertain = any(
        is_available(metric) and metric.uncertainty
        for metric in (results.annual_consumption, results.pipe_system)
    )
    verdict = "undetermined"
    summary = "Noch nicht beurteilbar: Für eine Investitionsentscheidung fehlen belastbare Angaben."
    if issues:
        summary = (
            "Noch nicht beurteilbar: Widersprüchliche Kennzahlen müssen geklärt werden."
        )
    elif not missing and not uncertain:
        verdict, summary, reason = decide_economics(results, readiness)
        reasons.append(reason)
    if uncertain:
        summary = "Noch nicht beurteilbar: Entscheidungsrelevante Modellangaben sind noch unbestätigt."
        reasons.append(
            "Entscheidungsrelevante LLM-Schätzungen müssen manuell bestätigt werden."
        )
    demo = is_available(results.payback_period)
    return InvestmentDecision(
        verdict,
        readiness,
        summary,
        tuple(reasons),
        tuple(issues),
        tuple(missing),
        CHECKS,
        (
            "plausibility-v1",
            "readiness-criteria-v1",
            "heat-load-m4-demo-v1",
            "simple-payback-demo-v1",
        ),
        demo,
        criteria,
        tuple(gaps),
    )
