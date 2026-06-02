from .rule_adapter import RuleBasedPronunciationAdapter


def build_rule_based_evidence(task, alignment):
    return RuleBasedPronunciationAdapter().build(task, alignment)
