"""Calculate exactly one metric: heat_load (rule heat-load-m4-demo-v1)."""

from ...config import AssessmentConfig
from ...contracts import UserInput, CalculationOutput, MetricResult
from .base import MetricModule

BELOW_BAND_NOTE = (
    "Der Verbrauch liegt unter der Gebäudeklasse; Zusatzwärme (z. B. Holzofen) oder "
    "unvollständige Verbrauchsdaten sind möglich. Angezeigt wird die Mitte der "
    "Gebäudeklasse."
)
ABOVE_BAND_NOTE = (
    "Der Verbrauch liegt über der Gebäudeklasse; der höhere Wert wird angezeigt, damit "
    "die Auslegung nicht unterschätzt wird. Zusatznutzung oder höheren Bedarf prüfen."
)


class HeatLoadEstimateModule(MetricModule):
    """Combine the class band with the consumption-based load; no decision is made.

    The class band estimates the design heat load. A consumption-based value is
    taken only if it fits the band, because it measures the annual heat used from
    one fuel and not the design load. It is read optionally: without it the band
    middle is used.
    """

    output_key = "heat_load"
    requires = ("heat_load_area",)

    def __init__(self, config: AssessmentConfig) -> None:
        """Store validated calculation configuration; no IO is performed."""
        self.config = config

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return the heat load estimate in kW from the band and optional consumption."""
        low, high = previous_results.heat_load_area.value
        middle = (low + high) / 2
        band = f"Gebäudeklasse: {low:.1f}–{high:.1f} kW."
        consumption = previous_results.heat_load_consumption
        if consumption is None or consumption.status != "available":
            return self.available(
                middle,
                "kW",
                (band, "Nur Flächenmethode: Mitte der Gebäudeklasse."),
                demonstration=True,
                uncertainty="Keine Verbrauchsangabe zur Bestätigung.",
            )
        value = consumption.value
        if value > high:
            return self.available(
                value,
                "kW",
                (band, "Verbrauchsbasierte Heizlast."),
                demonstration=True,
                uncertainty=ABOVE_BAND_NOTE,
            )
        if value < low:
            return self.available(
                middle,
                "kW",
                (band, "Mitte der Gebäudeklasse statt Verbrauchswert."),
                demonstration=True,
                uncertainty=BELOW_BAND_NOTE,
            )
        return self.available(
            value,
            "kW",
            (band, "Verbrauchsbasierte Heizlast; passt zur Gebäudeklasse."),
        )
