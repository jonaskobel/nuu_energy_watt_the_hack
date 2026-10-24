"""Behavior tests for calculations, dependency composition and cautious decisions."""
from dataclasses import FrozenInstanceError, replace
import unittest
from heat_pump_ready.config import AssessmentConfig
from heat_pump_ready.contracts import UserInput
from heat_pump_ready.intake import build_user_input
from heat_pump_ready.calculation.registry import build_modules
from heat_pump_ready.calculation.orchestrator import CalculationOrchestrator
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.llm.interfaces import LLMResponse
from heat_pump_ready.validator import validate_and_decide
from heat_pump_ready.demo_cases import SYNTHETIC
from heat_pump_ready.contracts import Attachment

class FakeRunner:
    """Provide deterministic model responses for extraction contract tests."""
    supports_images = True

    def __init__(self, text):
        """Store raw test response."""
        self.text = text

    def generate(self, request):
        """Return controlled response without network or file IO."""
        return LLMResponse(self.text, 'test-model')

class PipelineTests(unittest.TestCase):
    """Verify business boundaries independently of the UI."""

    def setUp(self):
        """Prepare a complete synthetic case and default configuration."""
        self.config = AssessmentConfig()
        self.input = build_user_input(SYNTHETIC)
        self.modules = build_modules(self.config, DisabledRunner())

    def run_case(self, user_input=None, disabled=()):
        """Execute selected input and disabled module keys."""
        return CalculationOrchestrator(self.modules, disabled).run(user_input or self.input)

    def test_complete_synthetic_case(self):
        """A fully specified supported case gives the documented numerical outputs."""
        output = self.run_case()
        self.assertEqual(output.useful_heat.value, 21120)
        self.assertEqual(output.space_heating_demand.value, 18120)
        self.assertEqual(output.heat_load_consumption.value, 9.06)
        self.assertAlmostEqual(output.heat_pump_energy_cost.value, 1568.9142857, places=5)
        self.assertAlmostEqual(output.annual_savings.value, 1071.0857143, places=5)
        self.assertAlmostEqual(output.payback_period.value, 11.2035838, places=4)
        decision = validate_and_decide(output, self.config, self.input)
        self.assertEqual(decision.verdict, 'worthwhile')
        self.assertTrue(decision.demonstration)

    def test_missing_investment_is_not_no(self):
        """Missing investment is insufficient evidence, not proof of no return."""
        user_input = replace(self.input, investment_eur=None)
        output = self.run_case(user_input)
        self.assertEqual(validate_and_decide(output, self.config, user_input).verdict, 'undetermined')
        self.assertEqual(output.payback_period.status, 'blocked')

    def test_disabled_producer_blocks_only_dependents(self):
        """Area and pipe analysis still run when annual consumption is disabled."""
        output = self.run_case(disabled=('annual_consumption',))
        self.assertEqual(output.useful_heat.status, 'blocked')
        self.assertEqual(output.heat_load_area.status, 'available')
        self.assertEqual(output.pipe_system.status, 'available')

    def test_invalid_registry(self):
        """Duplicate producers and wrong dependency order fail before execution."""
        with self.assertRaises(ValueError):
            CalculationOrchestrator(self.modules + (self.modules[0],))
        with self.assertRaises(ValueError):
            CalculationOrchestrator(tuple(reversed(self.modules)))

    def test_missing_producer_can_be_omitted(self):
        """Removing a producer marks its consumers blocked rather than crashing."""
        output = CalculationOrchestrator(self.modules[1:]).run(self.input)
        self.assertEqual(output.annual_consumption.status, 'disabled')
        self.assertEqual(output.useful_heat.status, 'blocked')

    def test_warm_water_scope(self):
        """Separate hot water changes load, not the existing annual fuel-cost scope."""
        output = self.run_case(replace(self.input, hot_water_via_heating=False))
        self.assertEqual(output.hot_water_demand.value, 0)
        self.assertEqual(output.space_heating_demand.value, 21120)
        self.assertEqual(output.heat_pump_energy_cost.value, self.run_case().heat_pump_energy_cost.value)

    def test_unknown_hot_water(self):
        """Unknown hot water blocks heating load but not annual total energy cost."""
        output = self.run_case(replace(self.input, hot_water_via_heating=None))
        self.assertEqual(output.heat_load_consumption.status, 'blocked')
        self.assertEqual(output.heat_pump_energy_cost.status, 'available')

    def test_impossible_heat_and_subsidy(self):
        """Contradictions remain visible to the validator and prevent recommendation."""
        user_input = replace(self.input, annual_consumption=100, subsidy_eur=25000)
        output = self.run_case(user_input)
        decision = validate_and_decide(output, self.config, user_input)
        self.assertLess(output.space_heating_demand.value, 0)
        self.assertGreaterEqual(len(decision.validation_issues), 2)
        self.assertEqual(decision.verdict, 'undetermined')

    def test_jaz_boundaries(self):
        """No gap at 55/60 C and no invented JAZ beyond the challenge range."""
        for temperature, expected in ((55, 3.5), (55.1, 2.8), (60, 2.8)):
            output = self.run_case(replace(self.input, flow_temperature_c=temperature))
            self.assertEqual(output.annual_performance_factor.value, expected)
        self.assertEqual(self.run_case(replace(self.input, flow_temperature_c=61)).annual_performance_factor.status, 'missing_input')

    def test_oil_and_incompatible_units(self):
        """Oil litres normalize correctly; litres are not accepted as gas kWh."""
        output = self.run_case(replace(self.input, energy_carrier='oil', annual_consumption=2400, consumption_unit='litre'))
        self.assertEqual(output.annual_consumption.value, 24000)
        self.assertAlmostEqual(output.current_energy_cost.value, 4080)
        invalid = self.run_case(replace(self.input, consumption_unit='litre'))
        self.assertEqual(invalid.annual_consumption.status, 'missing_input')

    def test_lpg_is_not_natural_gas(self):
        """LPG keeps useful heat but does not silently inherit the natural gas tariff."""
        output = self.run_case(replace(self.input, energy_carrier='lpg'))
        self.assertEqual(output.current_energy_cost.status, 'missing_input')
        self.assertEqual(output.useful_heat.status, 'available')

    def test_negative_savings(self):
        """No finite amortisation is expressed as a category rather than infinity."""
        config = replace(self.config, hp_price_eur_kwh=1)
        output = CalculationOrchestrator(build_modules(config, DisabledRunner())).run(self.input)
        self.assertEqual(output.payback_period.value, 'no_finite_payback')
        self.assertEqual(validate_and_decide(output, config, self.input).verdict, 'not_worthwhile')

    def test_single_pipe_needs_review(self):
        """Cheap investment does not override a known unresolved technical issue."""
        user_input = replace(self.input, pipe_system='single-pipe')
        output = self.run_case(user_input)
        self.assertEqual(validate_and_decide(output, self.config, user_input).verdict, 'undetermined')

    def test_immutable_data(self):
        """Neither callers nor subsequent modules can assign to shared dataclasses."""
        with self.assertRaises(FrozenInstanceError):
            self.input.floor_area_m2 = 1
        with self.assertRaises(FrozenInstanceError):
            self.run_case().horizon = None

    def test_numeric_input_validation(self):
        """Nonfinite values, booleans-as-numbers and fractional persons fail early."""
        for data in ({'floor_area_m2': 'nan'}, {'annual_consumption': True}, {'persons_in_household': 2.5}, {'hot_water_via_heating': 'false'}):
            with self.assertRaises(ValueError):
                build_user_input(data)

    def test_extraction_does_not_auto_confirm(self):
        """Valid categorical extraction remains uncertain and cannot authorize green."""
        user_input = replace(self.input, pipe_system='unknown', attachments=(Attachment('pipes.png','image/png','pipes',b'fake'),))
        runner = FakeRunner('{"value":"two-pipe","evidence":"Ventilkennzeichnung sichtbar","confidence":"high"}')
        output = CalculationOrchestrator(build_modules(self.config, runner)).run(user_input)
        self.assertEqual(output.pipe_system.value, 'two-pipe')
        self.assertIsNotNone(output.pipe_system.uncertainty)
        self.assertEqual(validate_and_decide(output, self.config, user_input).verdict, 'undetermined')

    def test_invalid_model_response_is_explicit_failure(self):
        """Malformed JSON does not become missing input or fabricated evidence."""
        user_input = replace(self.input, pipe_system='unknown', attachments=(Attachment('pipes.png','image/png','pipes',b'fake'),))
        output = CalculationOrchestrator(build_modules(self.config, FakeRunner('not json'))).run(user_input)
        self.assertEqual(output.pipe_system.status, 'failed')
        self.assertEqual(output.annual_savings.status, 'available')

if __name__ == '__main__':
    unittest.main()
