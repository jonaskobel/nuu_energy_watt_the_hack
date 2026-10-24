"""Sequential composition; no formula, model prompt or investment rule lives here."""

from dataclasses import replace
from typing import Iterable
from .interfaces import CalculationModule
from ..contracts import UserInput
from ..contracts import CalculationOutput, METRIC_KEYS, MetricResult


class CalculationOrchestrator:
    """Execute explicitly ordered modules. Args: modules and disabled output keys."""

    def __init__(
        self, modules: Iterable[CalculationModule], disabled: Iterable[str] = ()
    ) -> None:
        """Validate producers and dependency order before any processing starts."""
        self.modules = tuple(modules)
        self.disabled = frozenset(disabled)

        keys = [module.output_key for module in self.modules]

        if len(set(keys)) != len(keys) or any(key not in METRIC_KEYS for key in keys):
            raise ValueError("Duplicate or unknown metric producer")

        if not self.disabled.issubset(METRIC_KEYS):
            raise ValueError("Unknown disabled module")

        seen = set()

        for module in self.modules:
            if any(key in keys and key not in seen for key in module.requires):
                raise ValueError("Incorrect dependency order: " + module.name)

            if any(key not in METRIC_KEYS for key in module.requires):
                raise ValueError("Unknown dependency: " + module.name)

            seen.add(module.output_key)

    def run(self, user_input: UserInput) -> CalculationOutput:
        """Return immutable metrics; disabled dependencies block only their consumers."""
        output = CalculationOutput(
            **{
                key: MetricResult(key, "disabled", source="Nicht im aktiven Stack")
                for key in METRIC_KEYS
            }
        )
        for module in self.modules:
            if module.output_key in self.disabled:
                continue
            missing = [
                key for key in module.requires if output.get(key).status != "available"
            ]
            if missing:
                result = MetricResult(
                    module.output_key, "blocked", evidence=tuple(missing)
                )
            else:
                result = module.calculate(user_input, output)
            if result.key != module.output_key:
                raise ValueError("Module returned wrong metric: " + module.name)

            if result.status not in ("available", "missing_input", "blocked", "failed"):
                raise ValueError("Invalid metric status")

            if (result.status == "available") != (result.value is not None):
                raise ValueError("Metric status and value disagree")

            inherited_demo = any(
                output.get(key).demonstration for key in module.requires
            )

            if inherited_demo and not result.demonstration:
                result = replace(result, demonstration=True)

            output = replace(output, **{module.output_key: result})
            print()

        return output
