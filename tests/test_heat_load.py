"""Tests for the area/consumption heat-load estimate (rule heat-load-m4-demo-v1)."""
import csv
from dataclasses import replace
from pathlib import Path
import unittest
from heat_pump_ready.calculation.heat_load_classes import classify
from heat_pump_ready.calculation.orchestrator import CalculationOrchestrator
from heat_pump_ready.calculation.registry import build_modules
from heat_pump_ready.config import AssessmentConfig
from heat_pump_ready.contracts import UserInput
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.validator import validate_and_decide

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'


def load_dataset(relative_path):
    """Map one dataset CSV to (building id, UserInput); references stay out of the input."""
    with open(DATA_DIR / relative_path, newline='', encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    cases = []
    for row in rows:
        carrier = 'lpg' if 'LPG' in row['energy_carrier_detail'] else row['energy_carrier']
        cases.append((row['building_id'], UserInput(
            construction_year=int(row['construction_year']),
            floor_area_m2=float(row['floor_area_m2']),
            renovation_status=row['renovation_status'] or 'unknown',
            annual_consumption=float(row['annual_consumption_kwh']),
            energy_carrier=carrier,
            persons_in_household=int(row['persons_in_household']),
            hot_water_via_heating=row['hot_water_via_heating'] == 'yes',
            heat_distribution=row['heat_distribution'],
            pipe_system=row['pipe_system'])))
    return cases


def run_pipeline(modules, user_input, disabled=()):
    """Run one orchestrated calculation."""
    return CalculationOrchestrator(modules, disabled).run(user_input)


class ClassificationTests(unittest.TestCase):
    """Building class ladder: challenge classes plus flagged own supplements."""

    def test_challenge_classes_are_unflagged(self):
        """Years inside a challenge class need no own supplement."""
        for year, index in ((1970, 0), (1978, 0), (1980, 1), (1999, 1), (2002, 2), (2015, 2)):
            result = classify(year, 'unrenovated')
            self.assertEqual(result.index, index, year)
            self.assertFalse(result.own_supplement, year)

    def test_year_gaps_go_to_nearest_class_and_are_flagged(self):
        """1979, 2000 and 2001 are not covered by the challenge and are flagged."""
        for year, index in ((1979, 1), (2000, 1), (2001, 2)):
            result = classify(year, 'unrenovated')
            self.assertEqual(result.index, index, year)
            self.assertTrue(result.own_supplement, year)

    def test_partial_renovation_is_one_class_better_but_capped(self):
        """Partial renovation moves one class up, never beyond 'saniert oder ab 2002'."""
        self.assertEqual(classify(1970, 'partially').index, 1)
        self.assertEqual(classify(1990, 'partially').index, 2)
        self.assertEqual(classify(2005, 'partially').index, 2)
        self.assertTrue(classify(1970, 'partially').own_supplement)

    def test_unknown_renovation_uses_year_class_with_note(self):
        """Unknown renovation status is classified by year and says so."""
        result = classify(1987, 'unknown')
        self.assertEqual(result.index, 1)
        self.assertFalse(result.own_supplement)
        self.assertTrue(any('unbekannt' in note for note in result.notes))

    def test_renovation_status_without_year(self):
        """Fully renovated and low-energy buildings need no year; unknown needs one."""
        self.assertEqual(classify(None, 'fully').index, 2)
        self.assertEqual(classify(None, 'low_energy').index, 3)
        self.assertIsNone(classify(None, 'unknown'))


class EstimateRuleTests(unittest.TestCase):
    """Estimate rule: consumption value only when it fits the building class."""

    def setUp(self):
        """Use a 2005 building: class 40-60 W/m² on 180 m² gives 7.2-10.8 kW."""
        self.config = AssessmentConfig()
        self.modules = build_modules(self.config, DisabledRunner())
        self.base = UserInput(construction_year=2005, floor_area_m2=180, renovation_status='unknown',
                              energy_carrier='gas', persons_in_household=3, hot_water_via_heating=True)

    def run_case(self, consumption_kwh, disabled=()):
        """Run the pipeline for one annual consumption in kWh."""
        return run_pipeline(self.modules, replace(self.base, annual_consumption=consumption_kwh), disabled)

    def test_consumption_inside_band_is_used(self):
        """A consumption-based load inside the class band is the best estimate."""
        output = self.run_case(22000)
        self.assertAlmostEqual(output.heat_load_consumption.value, 8.18)
        self.assertEqual(output.heat_load.value, output.heat_load_consumption.value)

    def test_consumption_below_band_falls_back_to_band_middle(self):
        """Too low consumption (extra heat sources, incomplete data) gives the middle."""
        output = self.run_case(15500)
        self.assertAlmostEqual(output.heat_load_consumption.value, 5.32)
        self.assertAlmostEqual(output.heat_load.value, 9.0)
        self.assertIn('Zusatzwärme', output.heat_load.uncertainty)

    def test_consumption_above_band_is_kept_and_flagged(self):
        """Higher consumption is not averaged away; sizing must not be underestimated."""
        output = self.run_case(30000)
        self.assertAlmostEqual(output.heat_load_consumption.value, 11.7)
        self.assertEqual(output.heat_load.value, output.heat_load_consumption.value)
        self.assertIn('über', output.heat_load.uncertainty)

    def test_without_consumption_the_band_middle_is_used(self):
        """Area method alone: middle of the class band, marked as such."""
        output = self.run_case(22000, disabled=('annual_consumption',))
        self.assertAlmostEqual(output.heat_load.value, 9.0)
        self.assertTrue(output.heat_load.demonstration)

    def test_missing_area_blocks_estimate(self):
        """No floor area means no estimate; zero is never substituted."""
        user_input = replace(self.base, floor_area_m2=None, annual_consumption=22000)
        self.assertEqual(run_pipeline(self.modules, user_input).heat_load.status, 'blocked')

    def test_unknown_person_count_means_no_hot_water_deduction(self):
        """Unknown persons: no deduction, flagged; unknown hot-water route still blocks."""
        user_input = replace(self.base, annual_consumption=15500, persons_in_household=None)
        output = run_pipeline(self.modules, user_input)
        self.assertEqual(output.hot_water_demand.value, 0)
        self.assertIsNotNone(output.hot_water_demand.uncertainty)
        self.assertAlmostEqual(output.heat_load_consumption.value, 15500 * 0.88 / 2000)
        blocked = run_pipeline(self.modules, replace(user_input, hot_water_via_heating=None))
        self.assertEqual(blocked.hot_water_demand.status, 'missing_input')


class DatasetRegressionTests(unittest.TestCase):
    """Challenge buildings: documented results of rule heat-load-m4-demo-v1."""

    EXPECTED_KW = {'B-01': 9.75, 'B-02': 9.0, 'B-03': 16.6, 'B-04': 16.0, 'B-05': 10.38}

    def setUp(self):
        """Load dev and eval inputs without any reference values."""
        self.config = AssessmentConfig()
        self.modules = build_modules(self.config, DisabledRunner())
        self.cases = dict(load_dataset('dev_csv/buildings_dev.csv') + load_dataset('test_csv/buildings_eval.csv'))

    def test_estimates_match_documented_values(self):
        """The five buildings give the values documented in docs/HEIZLAST_M4.md."""
        for building_id, expected in self.EXPECTED_KW.items():
            output = run_pipeline(self.modules, self.cases[building_id])
            self.assertAlmostEqual(output.heat_load.value, expected, places=2, msg=building_id)

    def test_dev_references_are_compared_afterwards_only(self):
        """References are never inputs; B-03 is a documented miss (14.5 kW < 16.0 kW)."""
        references = {'B-01': 9.6, 'B-02': 9.7, 'B-03': 14.5}
        for building_id, reference in references.items():
            low, high = run_pipeline(self.modules, self.cases[building_id]).heat_load_area.value
            if building_id == 'B-03':
                self.assertLess(reference, low)
            else:
                self.assertTrue(low <= reference <= high, building_id)

    def test_strong_disagreement_is_a_note_not_a_blocker(self):
        """B-01 consumption (2.4 kW) is far below its class band but does not block."""
        output = run_pipeline(self.modules, self.cases['B-01'])
        decision = validate_and_decide(output, self.config)
        self.assertEqual(decision.validation_issues, ())
        self.assertTrue(any('Heizlastmethoden' in reason for reason in decision.reasons))
        self.assertIn('heat-load-m4-demo-v1', decision.applied_rules)


if __name__ == '__main__':
    unittest.main()
