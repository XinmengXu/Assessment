class BaseAssessmentAdapter:
    name = "base"

    def assess(self, target_text, transcript, features):
        raise NotImplementedError
