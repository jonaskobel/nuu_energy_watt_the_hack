"""Generate separate investment feedback from completed, validated calculations."""

from dataclasses import asdict, fields
import json
from pathlib import Path

from ..config import AssessmentConfig
from ..contracts import (
    UserInput, CalculationOutput, InvestmentDecision, InvestmentRecommendation,
)
from ..calculation.modules.extraction import parse_extraction_response
from .interfaces import LLMRequest, LLMRunner, RunnerError

PROMPT_PATH = Path(__file__).parent / 'prompts' / 'investment_recommendation.txt'
TEXT_FIELDS = ('summary', 'technical_assessment', 'economic_assessment', 'conclusion')
LIST_FIELDS = ('uncertainties', 'next_steps')


def recommendation_schema(decision: InvestmentDecision) -> str:
    """Constrain narrative feedback and prevent upgrading an unresolved decision."""
    verdicts = list(dict.fromkeys((decision.verdict, 'undetermined')))
    properties = {'verdict': {'enum': verdicts}}
    properties.update({key: {'type': 'string', 'minLength': 1, 'maxLength': 5000}
                       for key in TEXT_FIELDS})
    properties.update({key: {'type': 'array', 'maxItems': 10,
                            'items': {'type': 'string', 'minLength': 1, 'maxLength': 1000}}
                       for key in LIST_FIELDS})
    return json.dumps({'type': 'object', 'properties': properties,
                       'required': list(properties), 'additionalProperties': False})


def build_recommendation_prompt(
    user_input: UserInput, results: CalculationOutput,
    decision: InvestmentDecision, config: AssessmentConfig,
) -> str:
    """Include input facts, metrics and assumptions without raw files or test labels."""
    facts = {field.name: getattr(user_input, field.name) for field in fields(user_input)
             if field.name not in ('attachments', 'heating_connection_images')}
    context = {'user_input': facts, 'metrics': asdict(results),
               'decision': asdict(decision), 'configuration': asdict(config)}
    return PROMPT_PATH.read_text(encoding='utf-8') + json.dumps(
        context, ensure_ascii=False, allow_nan=False,
    )


def generate_recommendation(
    runner: LLMRunner, user_input: UserInput, results: CalculationOutput,
    decision: InvestmentDecision, config: AssessmentConfig, enabled: bool = True,
) -> InvestmentRecommendation:
    """Return validated model feedback; failure never discards calculated results.

    Args: configured runner, completed assessment snapshots and explicit LLM mode.
    Returns: immutable available, disabled or failed feedback with model provenance.
    """
    if not enabled:
        return InvestmentRecommendation('disabled')
    source = getattr(runner, 'model_id', getattr(runner, 'model', ''))
    if not isinstance(source, str):
        source = ''
    try:
        response = runner.generate(LLMRequest(
            build_recommendation_prompt(user_input, results, decision, config),
            json_schema=recommendation_schema(decision), max_tokens=3200,
        ))
        source = response.model
        data = parse_extraction_response(response.text)
        expected = {'verdict', *TEXT_FIELDS, *LIST_FIELDS}
        if set(data) != expected or data['verdict'] not in (decision.verdict, 'undetermined'):
            raise ValueError('Ungültige oder der Prüfentscheidung widersprechende Empfehlung.')
        for key in TEXT_FIELDS:
            if not isinstance(data[key], str) or not data[key].strip() or len(data[key]) > 5000:
                raise ValueError('Ungültiger Textabschnitt: ' + key)
        for key in LIST_FIELDS:
            if (not isinstance(data[key], list) or len(data[key]) > 10 or
                    any(not isinstance(item, str) or not item.strip() or len(item) > 1000
                        for item in data[key])):
                raise ValueError('Ungültige Liste: ' + key)
            data[key] = tuple(data[key])
        return InvestmentRecommendation('available', source=source, **data)
    except (RunnerError, ValueError, TypeError) as error:
        return InvestmentRecommendation('failed', source=source, error=str(error))
