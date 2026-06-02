import os


class LLMVerbalizer:
    """Optional constrained verbalizer. Disabled unless configured by environment."""

    def __init__(self):
        self.enabled = os.getenv("LLM_VERBALIZER_ENABLED", "false").lower() == "true"
        self.api_key = os.getenv("OPENAI_API_KEY", "")

    def verbalize(self, structured_feedback):
        if not self.enabled or not self.api_key:
            return structured_feedback
        # Version 1 keeps this as a safe adapter boundary. A future implementation
        # must preserve the structured sections and must not invent new issues.
        return structured_feedback
