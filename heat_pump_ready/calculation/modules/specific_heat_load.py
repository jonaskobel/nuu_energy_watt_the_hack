"""Calculate exactly one metric: specific_heat_load in W/m²."""

from ...contracts import UserInput, CalculationOutput, MetricResult
from .base import MetricModule


class SpecificHeatLoadModule(MetricModule):
    """Divide the heat load estimate by the heated area; no decision is made."""

    output_key = "specific_heat_load"
    requires = ("heat_load",)

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return W/m² and keep the uncertainty of the underlying heat load."""
        area = user_input.floor_area_m2
        if area is None:
            return self.missing("Beheizte Fläche fehlt.")
        heat_load = previous_results.heat_load
        return self.available(
            heat_load.value * 1000 / area,
            "W/m²",
            ("Heizlast-Schätzung geteilt durch beheizte Fläche.",),
            demonstration=heat_load.demonstration,
            uncertainty=heat_load.uncertainty,
        )
