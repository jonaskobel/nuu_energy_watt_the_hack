"""Extract a single radiator type only when one radiator image is supplied."""

from ...contracts import UserInput, CalculationOutput, MetricResult
from .extraction import ExtractionModule


RADIATOR_TYPE_PROMPT = """Classify the panel radiator shown in this photograph.
Return the type as the string "11", "22" or "33", or null if not identifiable.
The first digit counts the water-bearing heating panels; the second digit
counts the convector fin layers between/behind those panels:
- Type 11: one heating panel and one convector fin layer.
- Type 22: two heating panels and two convector fin layers.
- Type 33: three heating panels and three convector fin layers.
Count the panels and fin layers only when clearly visible, preferably from
the top or side. A decorative top grille is not a convector fin layer.
A front-only view, cover, valve, connection or overall thickness alone is
insufficient to distinguish the types. Do not invent hidden layers.
For other radiator types (such as type 10, 20 or 21, column radiators or towel
rails), return null and explain the unsupported type in the evidence.
If a legible manufacturer/type label is visible, use it as evidence.
Explain the observed panel and fin counts, or the missing visual information,
in German. Do not infer dimensions, heating output, the other radiators in
the building or suitability for a heat pump from this photograph.
"""


class RadiatorTypeModule(ExtractionModule):
    """A pictured radiator does not describe every radiator in the building."""

    output_key = "radiator_type"
    requires = ()

    def calculate(
        self, user_input: UserInput, previous_results: CalculationOutput
    ) -> MetricResult:
        """Return type 11/22/33 for one pictured radiator; ambiguous sets stay unknown."""
        images = [
            file for file in user_input.attachments if file.category == "radiator"
        ]
        if not images:
            return self.missing(
                "Bitte ein Heizkörperfoto unter der Kategorie Heizkörper hochladen; "
                "Heizplatten und Konvektorlagen sollten von oben oder seitlich sichtbar sein."
            )
        if len(images) > 1:
            return self.missing(
                "Für diese Kennzahl bitte genau ein repräsentatives Heizkörperfoto wählen."
            )
        if images[0].media_type not in ("image/jpeg", "image/png"):
            return self.missing("Für die Heizkörpertyp-Erkennung bitte JPG/PNG verwenden.")
        return self.extract(
            images,
            RADIATOR_TYPE_PROMPT,
            ("11", "22", "33"),
        )
