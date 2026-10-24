"""Behavior tests for calculations, dependency composition and cautious decisions."""
from dataclasses import FrozenInstanceError, replace
import unittest
import base64
import json
from unittest.mock import Mock
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

    def test_connection_images_reach_pipe_analysis(self):
        """Multiple new photos and legacy pipe uploads reach the existing runner."""
        image = {'name': 'connection.png', 'media_type': 'image/png',
                 'category': 'pipes', 'data': base64.b64encode(b'\x89PNG\r\n\x1a\nphoto').decode()}
        user_input = build_user_input({'heating_connection_images': [image, image],
                                      'attachments': [image]})
        self.assertEqual(len(user_input.heating_connection_images), 2)
        self.assertEqual(user_input.heating_connection_images[0].content, b'\x89PNG\r\n\x1a\nphoto')
        runner = FakeRunner('{"value":"two-pipe","evidence":"Kennzeichnung","confidence":"high"}')
        runner.generate = Mock(wraps=runner.generate)
        output = CalculationOrchestrator(build_modules(self.config, runner)).run(user_input)
        self.assertEqual(output.pipe_system.value, 'two-pipe')
        self.assertEqual(runner.generate.call_count, 3)
        self.assertTrue(all(len(call.args[0].attachments) == 1
                            for call in runner.generate.call_args_list))
        runner.generate.reset_mock()
        output = CalculationOrchestrator(build_modules(self.config, runner)).run(
            replace(user_input, pipe_system='single-pipe'))
        self.assertEqual(output.pipe_system.value, 'single-pipe')
        runner.generate.assert_not_called()

    def test_pipe_image_majority_and_abstentions(self):
        """Each photo votes once; ties, failures and unclear photos stay explicit."""
        from heat_pump_ready.llm.interfaces import RunnerError
        cases = (
            (['single-pipe', 'two-pipe', 'single-pipe'], 'available', 'single-pipe'),
            (['two-pipe', 'single-pipe', 'two-pipe'], 'available', 'two-pipe'),
            (['single-pipe', 'two-pipe'], 'missing_input', None),
            ([None, None], 'missing_input', None),
            (['two-pipe', None, 'error'], 'available', 'two-pipe'),
            (['error', 'error'], 'failed', None),
        )
        for decisions, status, value in cases:
            with self.subTest(decisions=decisions):
                images = tuple(Attachment(f'{i}.png', 'image/png', 'pipes', b'fake')
                               for i in range(len(decisions)))
                responses = [RunnerError('Modellfehler') if vote == 'error' else
                             LLMResponse(json.dumps({
                                 'value': vote, 'evidence': 'Sichtbare Rohrführung',
                                 'confidence': 'medium'}), 'test-model')
                             for vote in decisions]
                runner = FakeRunner('')
                runner.generate = Mock(side_effect=responses)
                user_input = replace(self.input, pipe_system='unknown',
                                     heating_connection_images=images)
                output = CalculationOrchestrator(build_modules(self.config, runner)).run(user_input)
                self.assertEqual((output.pipe_system.status, output.pipe_system.value), (status, value))
                self.assertEqual(runner.generate.call_count, len(images))
                for index, call in enumerate(runner.generate.call_args_list):
                    self.assertEqual(call.args[0].attachments, (images[index],))
                    self.assertIn(f'Bild {index + 1} ({images[index].name})',
                                  output.pipe_system.evidence[index])
                self.assertIn('Abstimmung:', output.pipe_system.evidence[len(images)])

    def test_local_runner_defaults_to_existing_gemma(self):
        """MLX selects the existing Gemma ID without loading it during construction."""
        from unittest.mock import patch
        from heat_pump_ready.llm.runners import build_runner, LocalMLXRunner
        with patch.dict('os.environ', {}, clear=True):
            runner = build_runner('mlx')
        self.assertIsInstance(runner, LocalMLXRunner)
        self.assertEqual(runner.model_id, 'mlx-community/gemma-4-12B-it-4bit')
        self.assertIsNone(runner.model)

    def test_connection_upload_validation(self):
        """Connection photos enforce type, content and shared file-count limits."""
        image = {'name': 'connection.png', 'media_type': 'image/png',
                 'category': 'pipes', 'data': base64.b64encode(b'\x89PNG\r\n\x1a\nphoto').decode()}
        for payload in (
            {'heating_connection_images': [dict(image, media_type='application/pdf', data='JVBERi0=')]},
            {'heating_connection_images': [dict(image, category='bill')]},
            {'heating_connection_images': [dict(image, data='broken')]},
            {'heating_connection_images': [image] * 4, 'attachments': [image] * 3},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                build_user_input(payload)
        self.assertEqual(build_user_input({}).heating_connection_images, ())

    def test_fenced_json_and_unknown_image_preserve_model(self):
        """Formatting wrappers are accepted; inconclusive images retain provenance."""
        from heat_pump_ready.calculation.modules.pipe_system import PipeSystemModule
        user_input = replace(self.input, pipe_system='unknown', heating_connection_images=(
            Attachment('h-block.jpeg', 'image/jpeg', 'pipes', b'fake'),))
        for value in ('two-pipe', None):
            with self.subTest(value=value):
                answer = '```json\n' + json.dumps({
                    'value': value, 'evidence': 'H-Block nicht eindeutig' if value is None else 'Rohrführung',
                    'confidence': 'low'}) + '\n```'
                runner = FakeRunner(answer)
                runner.generate = Mock(wraps=runner.generate)
                output = PipeSystemModule(runner).calculate(user_input, None)
                self.assertEqual(output.value, value)
                self.assertEqual(output.status, 'missing_input' if value is None else 'available')
                self.assertEqual(output.source, 'test-model')
                schema = json.loads(runner.generate.call_args.args[0].json_schema)
                self.assertEqual(schema['properties']['value']['enum'], [None, 'single-pipe', 'two-pipe'])

    def test_invalid_extraction_stays_failed(self):
        """Malformed or unsupported classifications never become votes."""
        from heat_pump_ready.calculation.modules.pipe_system import PipeSystemModule
        user_input = replace(self.input, pipe_system='unknown', heating_connection_images=(
            Attachment('pipes.jpeg', 'image/jpeg', 'pipes', b'fake'),))
        answers = ('{"value":', '[]',
                   '{"value":"two-pipe","evidence":"x","confidence":"certain"}',
                   '{"value":"Zweirohr","evidence":"x","confidence":"high"}',
                   '{"value":null,"evidence":[],"confidence":"low"}',
                   'Reasoning: {"value":"two-pipe","evidence":"x","confidence":"high"}')
        for answer in answers:
            with self.subTest(answer=answer):
                output = PipeSystemModule(FakeRunner(answer)).calculate(user_input, None)
                self.assertEqual(output.status, 'failed')
                self.assertIsNone(output.value)
                self.assertEqual(output.source, 'test-model')

    def test_local_extraction_uses_json_grammar(self):
        """MLX receives a grammar and thinking is disabled in template and decoding."""
        from types import SimpleNamespace
        from unittest.mock import patch
        from heat_pump_ready.llm.runners import LocalMLXRunner
        from heat_pump_ready.llm.interfaces import LLMRequest
        generate = Mock(return_value=SimpleNamespace(text='{}'))
        template = Mock(return_value='formatted prompt')
        grammar = Mock(return_value='grammar-processor')
        modules = {
            'mlx_vlm': SimpleNamespace(generate=generate),
            'mlx_vlm.prompt_utils': SimpleNamespace(apply_chat_template=template),
            'mlx_vlm.structured': SimpleNamespace(build_json_schema_logits_processor=grammar),
            'PIL': SimpleNamespace(Image=Mock()),
        }
        runner = LocalMLXRunner('gemma')
        runner.model = SimpleNamespace(config={})
        runner.processor = SimpleNamespace(tokenizer='tokenizer')
        with patch.dict('sys.modules', modules):
            response = runner.generate(LLMRequest('extract', json_schema='{"type":"object"}'))
        self.assertEqual(response.model, 'gemma')
        self.assertFalse(template.call_args.kwargs['enable_thinking'])
        self.assertFalse(generate.call_args.kwargs['enable_thinking'])
        self.assertTrue(generate.call_args.kwargs['skip_special_tokens'])
        self.assertEqual(generate.call_args.kwargs['logits_processors'], ['grammar-processor'])
        grammar.assert_called_once_with('tokenizer', '{"type":"object"}')

    def test_radiator_image_classification_in_pipeline(self):
        """The registered radiator module classifies only its image using the template."""
        from heat_pump_ready.calculation.modules.radiator_type import RADIATOR_TYPE_PROMPT
        image = Attachment('radiator.png', 'image/png', 'radiator', b'fake')
        other = Attachment('outdoor.png', 'image/png', 'outdoor', b'fake')
        user_input = replace(self.input, attachments=(other, image))
        for radiator_type in ('11', '22', '33', None):
            with self.subTest(radiator_type=radiator_type):
                runner = FakeRunner(json.dumps({'value': radiator_type,
                                               'evidence': 'Sichtbare Platten und Konvektorlagen',
                                               'confidence': 'medium'}))
                runner.generate = Mock(wraps=runner.generate)
                modules = build_modules(self.config, runner)
                self.assertEqual(sum(m.output_key == 'radiator_type' for m in modules), 1)
                output = CalculationOrchestrator(modules).run(user_input)
                self.assertEqual(output.radiator_type.value, radiator_type)
                self.assertEqual(output.radiator_type.status,
                                 'missing_input' if radiator_type is None else 'available')
                self.assertEqual(output.radiator_type.source, 'test-model')
                runner.generate.assert_called_once()
                request = runner.generate.call_args.args[0]
                self.assertEqual(request.attachments, (image,))
                self.assertIn(RADIATOR_TYPE_PROMPT, request.prompt)
                self.assertEqual(json.loads(request.json_schema)['properties']['value']['enum'],
                                 [None, '11', '22', '33'])
                self.assertEqual(output.annual_savings, self.run_case().annual_savings)

    def test_radiator_missing_multiple_and_disabled(self):
        """Missing/ambiguous uploads and disabled modules do not call the model."""
        image = Attachment('radiator.png', 'image/png', 'radiator', b'fake')
        pdf = Attachment('radiator.pdf', 'application/pdf', 'radiator', b'fake')
        runner = FakeRunner('')
        runner.generate = Mock(wraps=runner.generate)
        for attachments, disabled, expected in (
            ((), (), 'missing_input'),
            ((image, image), (), 'missing_input'),
            ((pdf,), (), 'missing_input'),
            ((image,), ('radiator_type',), 'disabled'),
        ):
            with self.subTest(attachments=attachments, disabled=disabled):
                output = CalculationOrchestrator(build_modules(self.config, runner), disabled).run(
                    replace(self.input, attachments=attachments))
                self.assertEqual(output.radiator_type.status, expected)
        runner.generate.assert_not_called()

    def test_invalid_radiator_type_is_rejected(self):
        """Unsupported or malformed classifications never become a radiator type."""
        image = Attachment('radiator.png', 'image/png', 'radiator', b'fake')
        for answer in ('not json', json.dumps({'value': '21', 'evidence': 'Foto', 'confidence': 'high'})):
            with self.subTest(answer=answer):
                output = CalculationOrchestrator(build_modules(self.config, FakeRunner(answer))).run(
                    replace(self.input, attachments=(image,)))
                self.assertEqual(output.radiator_type.status, 'failed')
                self.assertIsNone(output.radiator_type.value)

    def test_invalid_model_response_is_explicit_failure(self):
        """Malformed JSON does not become missing input or fabricated evidence."""
        user_input = replace(self.input, pipe_system='unknown', attachments=(Attachment('pipes.png','image/png','pipes',b'fake'),))
        output = CalculationOrchestrator(build_modules(self.config, FakeRunner('not json'))).run(user_input)
        self.assertEqual(output.pipe_system.status, 'failed')
        self.assertEqual(output.annual_savings.status, 'available')

if __name__ == '__main__':
    unittest.main()
