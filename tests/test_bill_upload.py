"""Bill uploads unlock dependent calculations without overriding user facts."""

from dataclasses import replace
import base64
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from heat_pump_ready.calculation.orchestrator import CalculationOrchestrator
from heat_pump_ready.calculation.registry import build_modules
from heat_pump_ready.config import AssessmentConfig
from heat_pump_ready.contracts import Attachment
from heat_pump_ready.demo_cases import SYNTHETIC
from heat_pump_ready.intake import build_user_input
from heat_pump_ready.llm.bill_images import prepare_bill_images
from heat_pump_ready.llm.interfaces import LLMResponse, RunnerError
from heat_pump_ready.llm.runners import DisabledRunner
from heat_pump_ready.server import make_handler


class BillUploadTests(unittest.TestCase):
    """Verify extraction, priority, unit handling and downstream savings."""

    def setUp(self):
        """Prepare complete heating facts with an intentionally missing annual use."""
        self.config = AssessmentConfig()
        self.bill = Attachment('bill.jpg', 'image/jpeg', 'bill', b'photo')
        self.input = replace(build_user_input(SYNTHETIC), annual_consumption=None,
                             attachments=(self.bill,))
        self.runner = SimpleNamespace(supports_images=True, generate=Mock(return_value=LLMResponse(
            json.dumps({'value': 13666, 'evidence': 'Gas: aktueller Verbrauch 13.666 kWh für 358 Tage.',
                        'confidence': 'high'}), 'gemma-test')))

    def run_case(self, user_input=None, runner=None):
        """Run the production module registry using deterministic model observations."""
        return CalculationOrchestrator(build_modules(self.config, runner or self.runner)).run(user_input or self.input)

    def test_bill_consumption_unlocks_cost_savings_and_payback(self):
        """A photo fills the consumption metric and unlocks the normal calculation graph."""
        output = self.run_case()
        self.assertEqual(output.annual_consumption.value, 13666)
        self.assertEqual(output.annual_consumption.unit, 'kWh/a')
        self.assertEqual(output.annual_consumption.source, 'gemma-test')
        self.assertIsNotNone(output.annual_consumption.uncertainty)
        self.assertAlmostEqual(output.current_energy_cost.value, 13666 * .11)
        self.assertAlmostEqual(output.heat_pump_energy_cost.value, 13666 * .88 / 3.5 * .26)
        self.assertAlmostEqual(output.annual_savings.value,
                               output.current_energy_cost.value - output.heat_pump_energy_cost.value)
        self.assertEqual(output.payback_period.status, 'available')
        self.assertEqual(output.heat_load_consumption.status, 'available')
        self.runner.generate.assert_called_once()
        request = self.runner.generate.call_args.args[0]
        self.assertEqual(request.attachments, (self.bill,))
        self.assertIn('13.666 kWh means 13666 kWh', request.prompt)
        self.assertIn('energy carrier: gas', request.prompt)

    def test_manual_consumption_takes_priority_over_bill(self):
        """Uploaded files never replace a known consumption value or its unit conversion."""
        output = self.run_case(replace(self.input, annual_consumption=2400,
                                       consumption_unit='litre', energy_carrier='oil'))
        self.assertEqual(output.annual_consumption.value, 24000)
        self.runner.generate.assert_not_called()

    def test_missing_jaz_cannot_be_invented_from_bill(self):
        """Consumption can fill while annual savings stays open without efficiency input."""
        output = self.run_case(replace(self.input, flow_temperature_c=None))
        self.assertEqual(output.annual_consumption.status, 'available')
        self.assertEqual(output.current_energy_cost.status, 'available')
        self.assertEqual(output.annual_savings.status, 'blocked')

    def test_unreadable_bill_does_not_become_zero(self):
        """An inconclusive or failed extraction leaves dependent calculations blocked."""
        for text, expected in (
            (json.dumps({'value': None, 'evidence': 'Nur Abschlag erkennbar.', 'confidence': 'low'}), 'missing_input'),
            ('invalid json', 'failed'),
        ):
            with self.subTest(text=text):
                self.runner.generate.return_value = LLMResponse(text, 'gemma-test')
                output = self.run_case()
                self.assertEqual(output.annual_consumption.status, expected)
                self.assertIsNone(output.annual_consumption.value)
                self.assertEqual(output.annual_savings.status, 'blocked')

    def test_bill_pdf_is_rendered_before_vision_request(self):
        """PDF attachments become page images, and renderer failures stay metric failures."""
        pdf = Attachment('bill.pdf', 'application/pdf', 'bill', b'%PDF-fake')
        user_input = replace(self.input, attachments=(pdf,))
        with patch('heat_pump_ready.llm.bill_images.render_bill_pdf', return_value=(self.bill,)) as render:
            output = self.run_case(user_input)
        self.assertEqual(output.annual_consumption.value, 13666)
        render.assert_called_once_with(pdf, 6)
        self.assertEqual(self.runner.generate.call_args.args[0].attachments, (self.bill,))
        with patch('heat_pump_ready.llm.bill_images.render_bill_pdf', side_effect=RunnerError('PDF nicht lesbar')):
            output = self.run_case(user_input)
        self.assertEqual(output.annual_consumption.status, 'failed')
        self.assertIn('PDF nicht lesbar', output.annual_consumption.evidence)

    def test_assessment_route_returns_bill_analysis_and_savings(self):
        """The upload JSON route uses the bill value and exports the additional panel data."""
        runner = SimpleNamespace(supports_images=True, generate=Mock(side_effect=[
            self.runner.generate.return_value, RunnerError('Empfehlung im Test deaktiviert'),
        ]))
        input_data = dict(SYNTHETIC, annual_consumption=None, attachments=[{
            'name': 'bill.jpg', 'media_type': 'image/jpeg', 'category': 'bill',
            'data': base64.b64encode(b'\xff\xd8\xffphoto').decode(),
        }])
        body = json.dumps({'input': input_data}).encode()
        handler_class = make_handler(runner, 'mlx')
        handler = handler_class.__new__(handler_class)
        handler.path = '/api/assessments'
        handler.headers = {'Host': 'localhost:8000', 'Content-Type': 'application/json',
                           'Content-Length': str(len(body))}
        handler.server = SimpleNamespace(server_port=8000)
        handler.connection = Mock()
        handler.rfile = BytesIO(body)
        handler.send_content = Mock()
        handler.do_POST()
        status, response = handler.send_content.call_args.args
        self.assertEqual(status, 200)
        self.assertEqual(response['bill_analysis']['value'], 13666)
        self.assertEqual(response['metrics']['annual_savings']['status'], 'available')
        self.assertEqual(response['decision']['verdict'], 'undetermined')

    def test_page_limit_and_offline_mode(self):
        """No model work happens for excessive page sets or when inference is disabled."""
        with self.assertRaises(RunnerError):
            prepare_bill_images((self.bill,) * 7)
        output = self.run_case(runner=DisabledRunner())
        self.assertEqual(output.annual_consumption.status, 'missing_input')
        self.assertIn('deaktiviert', output.annual_consumption.evidence[0])
        self.runner.generate.assert_not_called()


if __name__ == '__main__':
    unittest.main()
