"""Normalize one annual consumption value or extract it from a bill image."""

from ...contracts import UserInput, CalculationOutput, MetricResult
from dataclasses import replace
from ...config import AssessmentConfig
from ...llm.interfaces import LLMRunner
from .extraction import ExtractionModule


class AnnualConsumptionModule(ExtractionModule):
    """Prefer explicit user values over uncertain bill extraction."""

    output_key = "annual_consumption"
    requires = ()

    def __init__(self, runner: LLMRunner, config: AssessmentConfig) -> None:
        """Inject the runner and the validated fuel conversion constant."""
        super().__init__(runner)
        self.config = config

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return annual fuel energy in kWh, not useful heat."""
        if user_input.annual_consumption is not None:
            unit = user_input.consumption_unit
            compatible = (
                unit == "kwh"
                or (unit == "litre" and user_input.energy_carrier == "oil")
                or (unit == "m3" and user_input.energy_carrier == "gas")
            )
            if not compatible:
                return self.missing("Verbrauchseinheit passt nicht zum Energieträger.")
            factor = 1 if unit == "kwh" else self.config.fuel_kwh_per_unit
            return self.available(
                user_input.annual_consumption * factor,
                "kWh/a",
                (
                    (
                        f"1 Liter Öl bzw. 1 m³ Gas ≈ {factor:g} kWh."
                        if unit != "kwh"
                        else "Jahresverbrauch laut Nutzer."
                    ),
                ),
            )
        images = [file for file in user_input.attachments if file.category == "bill"]
        result = self.extract(
            images,
            "Gesuchter Wert: Jahresenergieverbrauch in kWh. Keine Monatswerte annualisieren; keine Zählerstände oder Geldbeträge verwenden. Nur explizit belegten Jahresverbrauch übernehmen.",
        )
        return replace(result, unit="kWh/a")
