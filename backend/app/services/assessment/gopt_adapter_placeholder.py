class GOPTAdapterPlaceholder:
    """Research-ready placeholder for a future GOPT-style pronunciation model."""

    name = "gopt_placeholder"

    def assess(self, target_text, transcript, features):
        return {
            "available": False,
            "message": "GOPT-style pronunciation assessment is not enabled in the lightweight prototype.",
        }
