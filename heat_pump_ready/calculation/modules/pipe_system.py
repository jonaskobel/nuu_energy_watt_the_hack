"""Classify connection photos individually and aggregate their pipe-system votes."""

from dataclasses import replace

from ...contracts import UserInput, CalculationOutput, MetricResult
from .extraction import ExtractionModule

PIPE_SYSTEM_PROMPT = """Classify the heating pipe system in this single photograph.
Return value="single-pipe" or "two-pipe" when supported by visible evidence;
otherwise return null. Explain the visible evidence in German.
Use these clues, including their limitations:
- Valve at the top, return fitting at the bottom, two separate pipes without
  a connection between them: likely two-pipe.
- One pipe along the wall/skirting from radiator to radiator, often with a
  short bypass: likely single-pipe.
- One bottom connection with both floor pipes entering one valve: often
  single-pipe, but two-pipe versions exist; this alone is not proof.
- Compact H-block with two pipes: exists for both systems, so normally
  inconclusive. An extra adjustable side port for a bypass points to single-pipe.
- A 1960s/1970s apartment building makes single-pipe more likely, but is not proof.
Do not invent hidden pipe routing or infer the building age from the photograph.
Two visible connections alone do not establish two-pipe. Do not force a decision
when the photo does not distinguish the systems.
"""


class PipeSystemModule(ExtractionModule):
    """Preserve manual input; otherwise use the majority of conclusive image votes."""

    output_key = "pipe_system"
    requires = ()

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return a majority classification with each photo's decision and evidence.

        Inconclusive/failed images abstain. A tie or no votes leaves the system
        unknown; if every image fails technically, return a failed metric.
        """
        if user_input.pipe_system != "unknown":
            return self.available(
                user_input.pipe_system, evidence=("Explizite Nutzerangabe.",)
            )
        images = [file for file in user_input.attachments if file.category == "pipes"]
        images.extend(user_input.heating_connection_images)
        if not images:
            return self.missing("Kein passendes Bild vorhanden.")
        if not self.runner.supports_images:
            return self.missing("LLM-Bildanalyse ist deaktiviert.")

        results = []
        evidence = []
        labels = {"single-pipe": "Einrohrsystem", "two-pipe": "Zweirohrsystem"}
        for index, image in enumerate(images, start=1):
            if image.media_type not in ("image/jpeg", "image/png"):
                result = self.missing("Keine Bilddatei; bitte JPG/PNG verwenden.")
            else:
                result = self.extract(
                    [image], PIPE_SYSTEM_PROMPT, ("single-pipe", "two-pipe")
                )
            results.append(result)
            decision = labels.get(result.value, "Fehler" if result.status == "failed" else "Nicht bestimmbar")
            details = " ".join(result.evidence)
            if result.uncertainty:
                details += " " + result.uncertainty
            evidence.append(f"Bild {index} ({image.name}): {decision}. {details}")

        votes = {key: sum(result.value == key for result in results) for key in labels}
        abstentions = len(images) - sum(votes.values())
        evidence.append(
            f"Abstimmung: Einrohrsystem {votes['single-pipe']}, "
            f"Zweirohrsystem {votes['two-pipe']}, ohne Entscheidung {abstentions}."
        )
        source = "; ".join(dict.fromkeys(result.source for result in results if result.source))
        if votes["single-pipe"] == votes["two-pipe"]:
            reason = "Keine eindeutige Mehrheit der Bildentscheidungen."
            status = "failed" if all(result.status == "failed" for result in results) else "missing_input"
            return MetricResult(
                self.output_key, status, source=source,
                evidence=tuple(evidence) + (reason,),
            )
        winner = max(votes, key=votes.get)
        return replace(
            self.available(
                winner,
                evidence=evidence,
                uncertainty="LLM-Bildauswertung, nicht bestätigt; Mehrheit der auswertbaren Bilder.",
            ),
            source=source,
        )
