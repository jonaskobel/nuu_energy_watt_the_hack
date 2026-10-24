"""Calculate exactly one metric: annual_performance_factor."""

from ...config import AssessmentConfig
from ...contracts import UserInput, CalculationOutput, MetricResult
from .base import MetricModule


class AnnualPerformanceFactorModule(MetricModule):
    """Derive annual_performance_factor without making an investment decision."""

    output_key = "annual_performance_factor"
    requires = ()

    def __init__(self, config: AssessmentConfig) -> None:
        """Store validated calculation configuration; no IO is performed."""
        self.config = config

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return one metric from input and declared prior metrics; inputs stay unchanged."""
        temperature = user_input.flow_temperature_c
        if user_input.heat_distribution == "underfloor" and temperature is None:
            return self.available(
                self.config.jaz_underfloor,
                "JAZ",
                ("Fußbodenheizung: angenommener Betrieb bei ca. 35 °C.",),
            )
        if temperature is None or user_input.heat_distribution == "unknown":
            return self.missing(
                "Heizflächenart und/oder benötigte Vorlauftemperatur fehlen."
            )
        if user_input.heat_distribution == "underfloor" and temperature <= 35:
            return self.available(self.config.jaz_underfloor, "JAZ")
        if temperature <= self.config.low_flow_temperature_max_c:
            return self.available(
                self.config.jaz_low_temperature,
                "JAZ",
                (
                    "Challenge-Zuordnung bis 55 °C; Mischsystem nach gemeinsamer Vorlauftemperatur.",
                ),
            )
        if temperature <= self.config.max_flow_temperature_c:
            return self.available(
                self.config.jaz_high_temperature,
                "JAZ",
                ("Challenge-Zuordnung über 55 bis 60 °C.",),
            )
        return self.missing("Für Vorlauf über 60 °C ist keine Challenge-JAZ definiert.")
