"""Tests for the technical traffic light (rule readiness-criteria-v1)."""
from dataclasses import replace
import unittest
from heat_pump_ready.calculation.orchestrator import CalculationOrchestrator
from heat_pump_ready.calculation.registry import build_modules
from heat_pump_ready.config import AssessmentConfig
from heat_pump_ready.contracts import Attachment, UserInput
from heat_pump_ready.llm.interfaces import LLMResponse
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.validator import validate_and_decide
from tests.test_heat_load import load_dataset

EXPECTED_DEV = {'B-01': 'green', 'B-02': 'green', 'B-03': 'yellow'}

# Radiators, two-pipe, 2005: area band 40–60 W/m², consumption-based load fits it.
BASE = UserInput(
    construction_year=2005, floor_area_m2=180, renovation_status='fully',
    annual_consumption=24000, energy_carrier='gas', persons_in_household=3,
    hot_water_via_heating=True, heat_distribution='radiators', pipe_system='two-pipe')


class FakeRunner:
    """Return one fixed model answer without network or file IO."""
    supports_images = True

    def __init__(self, text):
        """Store raw test response."""
        self.text = text

    def generate(self, request):
        """Return controlled response."""
        return LLMResponse(self.text, 'test-model')


class ReadinessTests(unittest.TestCase):
    """Traffic light from heat load, temperature and hydraulics criteria."""

    def setUp(self):
        """Prepare default modules and the dataset cases."""
        self.config = AssessmentConfig()
        self.modules = build_modules(self.config, DisabledRunner())
        self.cases = dict(load_dataset('dev_csv/buildings_dev.csv'))
        self.cases.update(load_dataset('test_csv/buildings_eval.csv'))

    def decide(self, user_input, modules=None):
        """Run pipeline and validator for one input."""
        output = CalculationOrchestrator(modules or self.modules).run(user_input)
        return validate_and_decide(output, self.config, user_input)

    def criterion(self, decision, key):
        """Return one named criterion from a decision."""
        return next(item for item in decision.criteria if item.key == key)

    def test_dev_cases_match_reference_traffic_light(self):
        """B-01/B-02 green and B-03 yellow without any building-specific rule."""
        for building_id, expected in EXPECTED_DEV.items():
            decision = self.decide(self.cases[building_id])
            self.assertEqual(decision.readiness, expected, building_id)

    def test_green_from_indicators_names_what_is_missing(self):
        """B-01 is green on indicators and lists flow temperature and pipe system as gaps."""
        decision = self.decide(self.cases['B-01'])
        self.assertEqual(self.criterion(decision, 'temperature').strength, 'indicator')
        self.assertEqual(self.criterion(decision, 'hydraulics').strength, 'indicator')
        gaps = ' '.join(decision.readiness_gaps)
        self.assertIn('Vorlauftemperatur', gaps)
        self.assertIn('Rohrsystem', gaps)

    def test_underfloor_does_not_need_pipe_system(self):
        """B-02: unknown pipe system is irrelevant for underfloor heating."""
        decision = self.decide(self.cases['B-02'])
        self.assertEqual(self.criterion(decision, 'hydraulics').state, 'met')
        self.assertTrue(any('Holzofen' in gap for gap in decision.readiness_gaps))

    def test_b03_yellow_because_temperature_is_open(self):
        """B-03: two-pipe is met, but 83 W/m² leaves the flow temperature open."""
        decision = self.decide(self.cases['B-03'])
        self.assertEqual(self.criterion(decision, 'hydraulics').state, 'met')
        self.assertEqual(self.criterion(decision, 'temperature').state, 'open')

    def test_eval_cases_are_not_green(self):
        """Single-pipe B-04 and mixed B-05 with 83 W/m² stay yellow."""
        for building_id in ('B-04', 'B-05'):
            self.assertEqual(self.decide(self.cases[building_id]).readiness, 'yellow', building_id)

    def test_specific_heat_load_metric(self):
        """Specific heat load is the estimate divided by heated area in W/m²."""
        output = CalculationOrchestrator(self.modules).run(self.cases['B-03'])
        self.assertEqual(output.specific_heat_load.unit, 'W/m²')
        self.assertAlmostEqual(output.specific_heat_load.value, 83.0, places=0)

    def test_known_flow_temperature_boundaries(self):
        """≤55 °C met, over 55 to 60 °C open, over 60 °C an obstacle (red)."""
        for flow, state, readiness in ((55, 'met', 'green'), (55.1, 'open', 'yellow'),
                                       (60, 'open', 'yellow'), (60.1, 'obstacle', 'red')):
            decision = self.decide(replace(BASE, flow_temperature_c=flow))
            self.assertEqual(self.criterion(decision, 'temperature').state, state, flow)
            self.assertEqual(decision.readiness, readiness, flow)

    def test_confirmed_flow_temperature_is_not_an_indicator(self):
        """A user-confirmed 50 °C gives a confirmed criterion and no temperature gap."""
        decision = self.decide(replace(BASE, flow_temperature_c=50))
        self.assertEqual(self.criterion(decision, 'temperature').strength, 'confirmed')
        self.assertFalse(any('Vorlauftemperatur' in gap for gap in decision.readiness_gaps))

    def test_high_flow_in_efficient_house_is_flagged(self):
        """70 °C in a 50 W/m² house hints at a too steep heating curve."""
        decision = self.decide(replace(BASE, flow_temperature_c=70))
        self.assertIn('Heizkurve', self.criterion(decision, 'temperature').reason)

    def test_specific_heat_load_threshold(self):
        """Unknown flow: a load equal to the threshold is an indicator, above it stays open."""
        output = CalculationOrchestrator(self.modules).run(BASE)
        load = output.specific_heat_load.value
        for threshold, state in ((load, 'met'), (load - 0.01, 'open')):
            config = replace(self.config, low_temperature_max_w_per_m2=threshold)
            decision = validate_and_decide(output, config, BASE)
            self.assertEqual(self.criterion(decision, 'temperature').state, state, threshold)

    def test_construction_year_threshold_for_unknown_pipe_system(self):
        """Unknown pipes: from the configured year a two-pipe system is an indicator."""
        year = int(self.config.two_pipe_likely_from_year)
        for construction_year, state in ((year, 'met'), (year - 1, 'open')):
            user_input = replace(BASE, construction_year=construction_year, pipe_system='unknown')
            decision = self.decide(user_input)
            self.assertEqual(self.criterion(decision, 'hydraulics').state, state, construction_year)

    def test_single_pipe_stays_open(self):
        """A confirmed single-pipe system needs review but is no exclusion."""
        decision = self.decide(replace(BASE, pipe_system='single-pipe'))
        self.assertEqual(self.criterion(decision, 'hydraulics').state, 'open')
        self.assertEqual(decision.readiness, 'yellow')

    def test_unconfirmed_llm_pipe_system_counts_as_open(self):
        """A model-read two-pipe system before 1995 does not authorize green."""
        user_input = replace(BASE, construction_year=1975, renovation_status='fully',
                             pipe_system='unknown', flow_temperature_c=50,
                             attachments=(Attachment('p.png', 'image/png', 'pipes', b'x'),))
        runner = FakeRunner('{"value":"two-pipe","evidence":"zwei Rohre","confidence":"high"}')
        decision = self.decide(user_input, build_modules(self.config, runner))
        self.assertEqual(self.criterion(decision, 'hydraulics').state, 'open')
        self.assertNotEqual(decision.readiness, 'green')

    def test_missing_heat_load_and_temperature_is_red_for_data(self):
        """Without area and flow temperature there is too little evidence (F05)."""
        decision = self.decide(replace(BASE, floor_area_m2=None))
        self.assertEqual(decision.readiness, 'red')
        self.assertTrue(any('Belege' in reason for reason in decision.reasons))

    def test_known_flow_without_heat_load_is_not_green(self):
        """JAZ and two-pipe alone no longer give green when the heat load is missing."""
        decision = self.decide(replace(BASE, floor_area_m2=None, flow_temperature_c=50))
        self.assertEqual(self.criterion(decision, 'heat_load').state, 'open')
        self.assertEqual(decision.readiness, 'yellow')


if __name__ == '__main__':
    unittest.main()
