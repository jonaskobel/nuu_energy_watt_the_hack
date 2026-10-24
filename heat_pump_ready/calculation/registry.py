"""Explicit module order; adding a metric requires a contract and a producer."""

from ..config import AssessmentConfig
from ..llm.interfaces import LLMRunner
from .modules.useful_heat import UsefulHeatModule
from .modules.hot_water_demand import HotWaterDemandModule
from .modules.space_heating_demand import SpaceHeatingDemandModule
from .modules.heat_load_consumption import ConsumptionHeatLoadModule
from .modules.heat_load_area import AreaHeatLoadModule
from .modules.heat_load_estimate import HeatLoadEstimateModule
from .modules.specific_heat_load import SpecificHeatLoadModule
from .modules.annual_performance_factor import AnnualPerformanceFactorModule
from .modules.current_energy_cost import CurrentEnergyCostModule
from .modules.heat_pump_energy_cost import HeatPumpEnergyCostModule
from .modules.annual_savings import AnnualSavingsModule
from .modules.net_investment import NetInvestmentModule
from .modules.payback_period import PaybackPeriodModule
from .modules.horizon import HorizonModule
from .modules.annual_consumption import AnnualConsumptionModule
from .modules.pipe_system import PipeSystemModule
from .modules.radiator_type import RadiatorTypeModule


def build_modules(config: AssessmentConfig, runner: LLMRunner) -> tuple:
    """Return one ordered producer per output key with explicit dependencies."""
    return (
        AnnualConsumptionModule(runner, config),
        UsefulHeatModule(config),
        HotWaterDemandModule(config),
        SpaceHeatingDemandModule(config),
        ConsumptionHeatLoadModule(config),
        AreaHeatLoadModule(config),
        HeatLoadEstimateModule(config),
        SpecificHeatLoadModule(),
        AnnualPerformanceFactorModule(config),
        CurrentEnergyCostModule(config),
        HeatPumpEnergyCostModule(config),
        AnnualSavingsModule(config),
        NetInvestmentModule(config),
        PaybackPeriodModule(config),
        HorizonModule(config),
        RadiatorTypeModule(runner),
        PipeSystemModule(runner),
    )
