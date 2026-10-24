"""Calculate exactly one metric: heat_load_area."""

from ...config import AssessmentConfig
from ...contracts import UserInput, CalculationOutput, MetricResult
from ..heat_load_classes import CLASSES, classify
from .base import MetricModule


class AreaHeatLoadModule(MetricModule):
    """Derive heat_load_area without making an investment decision."""

    output_key = "heat_load_area"
    requires = ()

    def __init__(self, config: AssessmentConfig) -> None:
        """Store validated calculation configuration; no IO is performed."""
        self.config = config

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return one metric from input and declared prior metrics; inputs stay unchanged."""
        area = user_input.floor_area_m2
        if area is None:
            return self.missing("Beheizte Fläche fehlt.")
        classification = classify(
            user_input.construction_year, user_input.renovation_status
        )
        if classification is None:
            return self.missing("Baujahr oder eindeutige Gebäudeklasse fehlt.")
        building_class = CLASSES[classification.index]
        low, high = building_class.low_w_per_m2, building_class.high_w_per_m2
        if classification.own_supplement:
            uncertainty = (
                "Eigene Ergänzung jenseits der Challenge-Richtwerte; nicht normiert."
            )
        elif user_input.renovation_status == "unknown":
            uncertainty = "Sanierungsstand unbekannt; Einstufung nur nach Baujahr."
        else:
            uncertainty = "Grobe Challenge-Richtwerte."
        return self.available(
            (area * low / 1000, area * high / 1000),
            "kW",
            (f"{building_class.label}: {low:g}–{high:g} W/m².", *classification.notes),
            demonstration=classification.own_supplement,
            uncertainty=uncertainty,
        )
