"""Immutable input, metric and decision contracts; units are explicit in field names."""

from __future__ import annotations
from dataclasses import dataclass, fields
from typing import Optional, Union, Tuple

MetricValue = Union[float, str, Tuple[float, float]]


@dataclass(frozen=True)
class Attachment:
    """Uploaded file held in memory. Args: name, media_type, category, content bytes."""

    name: str
    media_type: str
    category: str
    content: bytes


@dataclass(frozen=True)
class UserInput:
    """User-confirmed facts. None means unknown; files are immutable byte payloads."""

    construction_year: Optional[int] = None
    floor_area_m2: Optional[float] = None
    renovation_status: str = "unknown"
    annual_consumption: Optional[float] = None
    consumption_unit: str = "kwh"
    energy_carrier: str = "gas"
    persons_in_household: Optional[int] = None
    hot_water_via_heating: Optional[bool] = None
    heat_distribution: str = "unknown"
    pipe_system: str = "unknown"
    flow_temperature_c: Optional[float] = None
    investment_eur: Optional[float] = None
    subsidy_eur: Optional[float] = None
    horizon_years: float = 20.0
    location: str = ""
    notes: str = ""
    attachments: Tuple[Attachment, ...] = ()


@dataclass(frozen=True)
class MetricResult:
    """One metric plus provenance. value is None unless status is available."""

    key: str
    status: str
    value: Optional[MetricValue] = None
    unit: Optional[str] = None
    source: str = ""
    assumptions: Tuple[str, ...] = ()
    evidence: Tuple[str, ...] = ()
    uncertainty: Optional[str] = None
    demonstration: bool = False


@dataclass(frozen=True)
class CalculationOutput:
    """Read-only calculation snapshot. Only the orchestrator assembles new instances."""

    annual_consumption: Optional[MetricResult] = None
    useful_heat: Optional[MetricResult] = None
    hot_water_demand: Optional[MetricResult] = None
    space_heating_demand: Optional[MetricResult] = None
    heat_load_consumption: Optional[MetricResult] = None
    heat_load_area: Optional[MetricResult] = None
    heat_load: Optional[MetricResult] = None
    radiator_type: Optional[MetricResult] = None
    pipe_system: Optional[MetricResult] = None
    annual_performance_factor: Optional[MetricResult] = None
    current_energy_cost: Optional[MetricResult] = None
    heat_pump_energy_cost: Optional[MetricResult] = None
    annual_savings: Optional[MetricResult] = None
    net_investment: Optional[MetricResult] = None
    payback_period: Optional[MetricResult] = None
    horizon: Optional[MetricResult] = None

    def get(self, key: str) -> Optional[MetricResult]:
        """Return metric by declared key. Raises: KeyError for an unknown key."""
        if key not in METRIC_KEYS:
            raise KeyError(key)
        return getattr(self, key)


METRIC_KEYS = tuple(field.name for field in fields(CalculationOutput))


@dataclass(frozen=True)
class InvestmentDecision:
    """Validator output, separate from unmodified numerical and categorical metrics."""

    verdict: str
    readiness: str
    summary: str
    reasons: Tuple[str, ...]
    validation_issues: Tuple[str, ...]
    missing_information: Tuple[str, ...]
    technician_checks: Tuple[str, ...]
    applied_rules: Tuple[str, ...]
    demonstration: bool
