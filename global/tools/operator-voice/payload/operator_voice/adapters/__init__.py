"""Source adapters — build plan v3 §4/§6: "Adapters implement scan(registration, cursor) ->
ObservationCandidate[]; only the application service invokes them." Every adapter here parses
ONLY its declared format, canonicalizes paths before reading, enforces file/record/byte limits,
and emits :class:`~operator_voice.domain.models.ObservationCandidate` with authoritative
role/author metadata straight from the source format — it never infers authorship from text
content (that decision belongs solely to ``kernel.authorship``) and never writes persistence.
"""
