"""Validated challenge assumptions and runtime configuration."""

from dataclasses import dataclass, fields
import math


@dataclass(frozen=True)
class AssessmentConfig:
    """Positive parameters in kWh, hours, EUR and dimensionless efficiencies."""

    boiler_efficiency: float = 0.88
    hot_water_kwh_per_person: float = 1000.0
    full_load_hours: float = 2000.0
    hp_price_eur_kwh: float = 0.26
    gas_price_eur_kwh: float = 0.11
    oil_price_eur_kwh: float = 0.17
    fuel_kwh_per_unit: float = 10.0
    jaz_underfloor: float = 4.0
    jaz_low_temperature: float = 3.5
    jaz_high_temperature: float = 2.8
    low_flow_temperature_max_c: float = 55.0
    max_flow_temperature_c: float = 60.0
    discrepancy_ratio: float = 2.0
    # Own demo assumptions (readiness-criteria-v1), not challenge values; frozen before eval.
    low_temperature_max_w_per_m2: float = 60.0
    two_pipe_likely_from_year: float = 1995.0

    def __post_init__(self):
        """Reject nonfinite/nonpositive constants and invalid boiler efficiency."""
        for field in fields(self):
            value = getattr(self, field.name)
            if not math.isfinite(value) or value <= 0:
                raise ValueError("Invalid configuration: " + field.name)
        if self.boiler_efficiency > 1 or self.discrepancy_ratio <= 1:
            raise ValueError("Invalid efficiency or discrepancy ratio")
        if self.low_flow_temperature_max_c > self.max_flow_temperature_c:
            raise ValueError("Invalid flow temperature thresholds")
