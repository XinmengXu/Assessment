from ...config import PRONUNCIATION_PROVIDER, RESEARCH_MODE
from .azure_provider import AzurePronunciationAssessmentProvider
from .disabled_provider import DisabledPronunciationAssessmentProvider
from .external_import_provider import ExternalImportPronunciationAssessmentProvider
from .mock_provider import MockPronunciationAssessmentProvider


def get_pronunciation_provider(db=None, provider_name=None):
    name = (provider_name or PRONUNCIATION_PROVIDER or "mock").strip().lower()
    if name == "azure_pronunciation":
        return AzurePronunciationAssessmentProvider()
    if name == "external_import":
        return ExternalImportPronunciationAssessmentProvider(db=db)
    if name == "disabled":
        return DisabledPronunciationAssessmentProvider()
    if name == "mock":
        return MockPronunciationAssessmentProvider()
    if RESEARCH_MODE:
        return DisabledPronunciationAssessmentProvider()
    return MockPronunciationAssessmentProvider()


def provider_status(db=None):
    provider = get_pronunciation_provider(db=db)
    return provider.status()
