"""Shared reference handling and evaluation for native repository records."""

from ..clients.repository_client import evaluation_response
from ..utils.references import extract_doi, parse_url
from ..utils.translation_checks import EvaluationContext, evaluate_translation, load_translation


def local_value(reference, slug):
    reference = reference.strip()
    prefix = slug + ":"
    return reference[len(prefix):].strip() if reference.casefold().startswith(prefix.casefold()) else reference


def record_url(reference, hosts):
    reference = reference.strip()
    if reference.partition("/")[0].casefold() in hosts:
        reference = "https://" + reference
    url = parse_url(reference)
    return url if url and url.hostname in hosts else None


def finish_record(record, *, profile_path, display_name, source_url, reference, expected_id,
                  namespace, level, doi=None, on_event=None):
    profile = load_translation(profile_path)
    context = EvaluationContext(
        reference=reference, expected_identifier=extract_doi(reference),
        expected_record_id=expected_id, expected_namespace=namespace,
        requested_level=level, source_url=source_url,
    )
    checks = evaluate_translation(record, profile, context=context, on_event=on_event)
    return evaluation_response(
        repository=profile["repository"], display_name=display_name, source_url=source_url,
        repository_response=record, record_checks=checks, doi=doi, on_event=on_event,
    )
