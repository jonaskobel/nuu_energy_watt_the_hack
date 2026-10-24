"""Explicit startup modes never enable inference just from environment settings."""
from contextlib import redirect_stderr
from io import StringIO
import json
import unittest
from unittest.mock import patch, MagicMock

from heat_pump_ready.__main__ import main
from heat_pump_ready.llm.runners import ApiLLMRunner, DisabledRunner, LocalMLXRunner
from heat_pump_ready.llm.interfaces import LLMRequest


class StartupTests(unittest.TestCase):
    def launch(self, args, env=None):
        with patch.dict('os.environ', env or {}, clear=True), patch('sys.argv', ['heat_pump_ready', *args]), patch('heat_pump_ready.__main__.serve') as serve:
            main()
            return serve.call_args.args

    def test_default_ignores_llm_environment(self):
        for mode in ('api', 'mlx'):
            runner, selected, _, _ = self.launch([], {'LLM_RUNNER': mode, 'LLM_MODEL': 'unused'})
            self.assertIsInstance(runner, DisabledRunner)
            self.assertEqual(selected, 'disabled')

    def test_api_uses_configured_values_without_loading_mlx(self):
        env = {'LLM_API_URL': 'https://provider.example/v1/chat/completions', 'LLM_MODEL': 'api-model', 'LLM_API_KEY': 'test-only-placeholder'}
        for flags in (['-api'], ['--api'], ['--runner', 'api']):
            runner, selected, _, _ = self.launch(flags, env)
            self.assertIsInstance(runner, ApiLLMRunner)
            self.assertEqual((selected, runner.endpoint, runner.model, runner.api_key), ('api', env['LLM_API_URL'], env['LLM_MODEL'], env['LLM_API_KEY']))

    def test_mlx_is_explicit_and_does_not_load_during_configuration(self):
        runner, selected, _, _ = self.launch(['-mlx'])
        self.assertIsInstance(runner, LocalMLXRunner)
        self.assertEqual(selected, 'mlx')
        self.assertIsNone(runner.model)

    def test_conflicting_modes_and_missing_api_settings_fail_before_serving(self):
        for flags in (['-api', '-mlx'], ['-api', '--runner', 'mlx'], ['-api']):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as error:
                self.launch(flags)
            self.assertEqual(error.exception.code, 2)

    def test_claude_compatibility_omits_temperature_and_supports_workspace(self):
        runner = ApiLLMRunner('https://api.anthropic.com/v1/chat/completions', 'claude-test', 'test-key', 'workspace-test')
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': 'Claude-Antwort'}}]}).encode()
        with patch('urllib.request.urlopen', return_value=response) as call:
            result = runner.generate(LLMRequest('Bitte erklären.'))
        request = call.call_args.args[0]
        self.assertNotIn('temperature', json.loads(request.data))
        self.assertGreaterEqual(json.loads(request.data)['max_tokens'], 4096)
        self.assertEqual(request.get_header('Anthropic-workspace-id'), 'workspace-test')
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(result.text, 'Claude-Antwort')

    def test_api_adapter_sends_configured_request_and_reads_response(self):
        runner, _, _, _ = self.launch(['-api'], {'LLM_API_URL': 'https://provider.example/v1/chat/completions', 'LLM_MODEL': 'api-model', 'LLM_API_KEY': 'test-key'})
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'choices': [{'message': {'content': 'Antwort'}}]}).encode()
        with patch('urllib.request.urlopen', return_value=response) as call:
            result = runner.generate(LLMRequest('Bitte Ampel erklären.'))
        request = call.call_args.args[0]
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-key')
        self.assertEqual(json.loads(request.data)['model'], 'api-model')
        self.assertEqual(result.text, 'Antwort')


if __name__ == '__main__':
    unittest.main()
