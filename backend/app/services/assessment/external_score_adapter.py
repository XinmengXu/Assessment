class ExternalScoreAdapter:
    """Placeholder for importing sentence, word, or issue-level scores later."""

    name = "external_score_csv"

    def __init__(self, rows=None):
        self.rows = rows or []

    def assess(self, participant_id, task_id, attempt_number):
        for row in self.rows:
            if row.get("participant_id") == participant_id and int(row.get("task_id", 0)) == int(task_id) and int(row.get("attempt_number", 0)) == int(attempt_number):
                return row
        return None
