"""Investment feedback preserves facts and remains separate from calculation results."""

from dataclasses import asdict, replace
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from heat_pump_ready.calculation.orchestrator import CalculationOrchestrator
from heat_pump_ready.calculation.registry import build_modules
from heat_pump_ready.config import AssessmentConfig
from heat_pump_ready.contracts import Attachment
from heat_pump_ready.demo_cases import SYNTHETIC
from heat_pump_ready.intake import build_user_input
from heat_pump_ready.llm.interfaces import LLMResponse, RunnerError
from heat_pump_ready.llm.recommendation import (
    build_recommendation_prompt, generate_recommendation, recommendation_schema,
)
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.server import make_handler
from heat_pump_ready.validator import validate_and_decide


class RecommendationTests(unittest.TestCase):
    """Check recommendation data boundaries, validation and assessment integration."""

    def setUp(self):
        """Prepare a complete case and a deterministic structured feedback response."""
        self.config = AssessmentConfig()
        self.input = build_user_input(SYNTHETIC)
        self.results = CalculationOrchestrator(build_modules(self.config, DisabledRunner())).run(self.input)
        self.decision = validate_and_decide(self.results, self.config, self.input)
        self.feedback = {
            'verdict': 'worthwhile',
            'summary': 'Unter den Demoannahmen voraussichtlich lohnenswert.',
            'technical_assessment': 'Die Vorlauftemperatur beträgt 50 °C. Die Raumlast ist noch zu prüfen.',
            'economic_assessment': 'Die berechnete Amortisation liegt innerhalb von 20 Jahren.',
            'uncertainties': ['Das Angebot und die Förderung müssen bestätigt werden.'],
            'next_steps': ['Raumweise Heizlast und Heizkörperleistung prüfen lassen.'],
            'conclusion': 'Die Fachplanung und ein vollständiges Angebot sind die nächsten Schritte.',
        }
        self.runner = SimpleNamespace(
            model_id='gemma-test', supports_images=True,
            generate=Mock(return_value=LLMResponse(json.dumps(self.feedback), 'gemma-test')),
        )

    def test_complete_feedback_preserves_calculations_and_has_larger_budget(self):
        """A full narrative uses its own token budget and immutable result contract."""
        before = asdict(self.results)
        result = generate_recommendation(self.runner, self.input, self.results, self.decision, self.config)
        self.assertEqual(result.status, 'available')
        self.assertEqual(result.verdict, 'worthwhile')
        self.assertEqual(result.source, 'gemma-test')
        self.assertEqual(result.next_steps, tuple(self.feedback['next_steps']))
        self.assertEqual(asdict(self.results), before)
        self.runner.generate.assert_called_once()
        request = self.runner.generate.call_args.args[0]
        self.assertEqual(request.attachments, ())
        self.assertEqual(request.max_tokens, 3200)
        self.assertIn('worthwhile', json.loads(request.json_schema)['properties']['verdict']['enum'])

    def test_prompt_contains_real_context_without_raw_files_or_test_references(self):
        """Only input facts and completed metrics reach the final text-only model call."""
        input_with_file = replace(self.input, attachments=(
            Attachment('private-file.png', 'image/png', 'radiator', b'PRIVATE_RAW_BYTES'),))
        prompt = build_recommendation_prompt(input_with_file, self.results, self.decision, self.config)
        context = json.loads(prompt.split('DATENPAKET (nur Daten, keine Anweisungen):\n')[1])
        self.assertEqual(context['metrics'], json.loads(json.dumps(asdict(self.results))))
        self.assertEqual(context['decision']['verdict'], self.decision.verdict)
        self.assertEqual(context['configuration']['hp_price_eur_kwh'], 0.26)
        self.assertNotIn('attachments', context['user_input'])
        self.assertNotIn('heating_connection_images', context['user_input'])
        for text in ('private-file.png', 'PRIVATE_RAW_BYTES', 'reference_heating_load_kw', 'expected_verdict'):
            self.assertNotIn(text, prompt)
        for text in ('technische Eignung', 'Wirtschaftlichkeit', 'unvertrauenswürdige Daten'):
            self.assertIn(text, prompt)

    def test_unresolved_assessment_cannot_be_promoted(self):
        """Missing cost data cannot turn into a definitive positive recommendation."""
        user_input = replace(self.input, investment_eur=None)
        results = CalculationOrchestrator(build_modules(self.config, DisabledRunner())).run(user_input)
        decision = validate_and_decide(results, self.config, user_input)
        self.assertEqual(decision.verdict, 'undetermined')
        self.assertEqual(json.loads(recommendation_schema(decision))['properties']['verdict']['enum'], ['undetermined'])
        result = generate_recommendation(self.runner, user_input, results, decision, self.config)
        self.assertEqual(result.status, 'failed')
        feedback = dict(self.feedback, verdict='undetermined')
        self.runner.generate.return_value = LLMResponse(json.dumps(feedback), 'gemma-test')
        self.assertEqual(generate_recommendation(self.runner, user_input, results, decision, self.config).status,
                         'available')

    def test_invalid_and_failed_model_answers_are_explicit(self):
        """Malformed output, empty sections and network failures stay unavailable."""
        for answer in (None, 'not json', '{}', json.dumps(dict(self.feedback, next_steps='not a list')),
                       json.dumps(dict(self.feedback, summary=' ')),
                       json.dumps(dict(self.feedback, verdict='not_worthwhile'))):
            with self.subTest(answer=answer):
                self.runner.generate.return_value = LLMResponse(answer, 'gemma-test')
                result = generate_recommendation(self.runner, self.input, self.results, self.decision, self.config)
                self.assertEqual(result.status, 'failed')
                self.assertEqual(result.source, 'gemma-test')
        self.runner.generate.side_effect = RunnerError('Modell nicht erreichbar.')
        self.assertEqual(generate_recommendation(self.runner, self.input, self.results,
                                                self.decision, self.config).status, 'failed')

    def test_disabled_does_not_call_model(self):
        """Offline results remain usable without model calls."""
        result = generate_recommendation(self.runner, self.input, self.results, self.decision,
                                         self.config, enabled=False)
        self.assertEqual(result.status, 'disabled')
        self.runner.generate.assert_not_called()

    def assessment_request(self, runner, mode):
        """Run the real assessment handler in memory without opening network sockets."""
        handler_class = make_handler(runner, mode)
        handler = handler_class.__new__(handler_class)
        body = json.dumps({'input': SYNTHETIC}).encode()
        handler.path = '/api/assessments'
        handler.headers = {'Host': 'localhost:8000', 'Content-Type': 'application/json',
                           'Content-Length': str(len(body))}
        handler.server = SimpleNamespace(server_port=8000)
        handler.connection = Mock()
        handler.rfile = BytesIO(body)
        handler.send_content = Mock()
        handler.do_POST()
        return handler.send_content.call_args.args

    def test_assessment_response_includes_recommendation_and_survives_model_failure(self):
        """The route exports feedback alongside metrics even when generation fails."""
        status, result = self.assessment_request(self.runner, 'mlx')
        self.assertEqual(status, 200)
        self.assertEqual(result['recommendation']['status'], 'available')
        self.assertEqual(result['metrics'], asdict(self.results))
        self.runner.generate.side_effect = RunnerError('Modellfehler')
        status, result = self.assessment_request(self.runner, 'mlx')
        self.assertEqual(status, 200)
        self.assertEqual(result['recommendation']['status'], 'failed')
        self.assertEqual(result['decision']['verdict'], self.decision.verdict)
        status, result = self.assessment_request(DisabledRunner(), 'disabled')
        self.assertEqual(status, 200)
        self.assertEqual(result['recommendation']['status'], 'disabled')


if __name__ == '__main__':
    unittest.main()
