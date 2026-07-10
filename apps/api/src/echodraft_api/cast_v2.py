from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

CAST_V2_VERSION = "cast-v2-clustering-0.1.0"
DEFAULT_CLUSTER_THRESHOLD = 0.78
HONORIFICS = {
    "capt",
    "captain",
    "doctor",
    "dr",
    "lady",
    "mr",
    "mrs",
    "ms",
    "prof",
    "professor",
    "sir",
}


@dataclass(frozen=True)
class ClusterMention:
    id: str
    surface_name: str
    canonical_guess: str | None
    evidence_text: str
    window_id: str
    role_in_scene: str


@dataclass(frozen=True)
class MentionCluster:
    id: str
    mention_ids: list[str]
    normalized_keys: list[str]
    surface_forms: list[str]
    confidence: float


@dataclass(frozen=True)
class ClusterMerge:
    left_key: str
    right_key: str
    score: float
    reason: str


@dataclass(frozen=True)
class ClusterResult:
    clusters: list[MentionCluster]
    merges: list[ClusterMerge]
    cannot_link_pairs: list[list[str]]
    embedding_used: bool
    threshold: float
    diagnostics: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _Form:
    key: str
    surface_forms: set[str] = field(default_factory=set)
    mention_ids: set[str] = field(default_factory=set)
    canonical_keys: set[str] = field(default_factory=set)
    windows_as_speaker: set[str] = field(default_factory=set)


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )
    if math.isclose(similarity, 1.0, abs_tol=1e-12):
        return 1.0
    if math.isclose(similarity, -1.0, abs_tol=1e-12):
        return -1.0
    return max(-1.0, min(1.0, similarity))


def cluster_mentions(
    mentions: list[ClusterMention],
    *,
    embeddings: dict[str, list[float]] | None = None,
    confirmed_pairs: set[frozenset[str]] | None = None,
    rejected_pairs: set[frozenset[str]] | None = None,
    threshold: float = DEFAULT_CLUSTER_THRESHOLD,
) -> ClusterResult:
    forms = _aggregate_forms(mentions)
    normalized_embeddings = {
        normalize_name(key): vector for key, vector in (embeddings or {}).items() if vector
    }
    confirmed = _normalize_pairs(confirmed_pairs or set())
    rejected = _normalize_pairs(rejected_pairs or set())
    cannot_link = (_cannot_link_pairs(forms) | rejected) - confirmed
    clusters: list[set[str]] = [{key} for key in sorted(forms)]
    merges: list[ClusterMerge] = []

    while True:
        best: tuple[float, str, str, int, int, str] | None = None
        for left_index, left_cluster in enumerate(clusters):
            for right_index in range(left_index + 1, len(clusters)):
                right_cluster = clusters[right_index]
                if _clusters_conflict(left_cluster, right_cluster, cannot_link):
                    continue
                score, reason, left_key, right_key = _cluster_pair_score(
                    left_cluster,
                    right_cluster,
                    forms,
                    normalized_embeddings,
                    confirmed,
                )
                if score < threshold:
                    continue
                candidate = (score, left_key, right_key, left_index, right_index, reason)
                if best is None or candidate[:3] > best[:3]:
                    best = candidate
        if best is None:
            break
        score, left_key, right_key, left_index, right_index, reason = best
        clusters[left_index] |= clusters[right_index]
        del clusters[right_index]
        merges.append(
            ClusterMerge(
                left_key=left_key,
                right_key=right_key,
                score=round(score, 6),
                reason=reason,
            )
        )

    output = [_cluster_payload(cluster, forms, normalized_embeddings) for cluster in clusters]
    output.sort(key=lambda item: tuple(name.casefold() for name in item.surface_forms))
    diagnostics: list[dict[str, object]] = []
    if mentions and not normalized_embeddings:
        diagnostics.append(
            {
                "severity": "info",
                "type": "embedding_fallback",
                "message": "Cast v2 clustered with string features because embeddings were unavailable.",
            }
        )
    return ClusterResult(
        clusters=output,
        merges=merges,
        cannot_link_pairs=[sorted(pair) for pair in sorted(cannot_link, key=lambda item: sorted(item))],
        embedding_used=bool(normalized_embeddings),
        threshold=threshold,
        diagnostics=diagnostics,
    )


def _aggregate_forms(mentions: list[ClusterMention]) -> dict[str, _Form]:
    forms: dict[str, _Form] = {}
    for mention in sorted(mentions, key=lambda item: (normalize_name(item.surface_name), item.id)):
        key = normalize_name(mention.surface_name)
        if not key:
            continue
        form = forms.setdefault(key, _Form(key=key))
        form.surface_forms.add(mention.surface_name.strip())
        form.mention_ids.add(mention.id)
        canonical_key = normalize_name(mention.canonical_guess)
        if canonical_key:
            form.canonical_keys.add(canonical_key)
        if mention.role_in_scene.casefold() == "speaker":
            form.windows_as_speaker.add(mention.window_id)
    return forms


def _normalize_pairs(pairs: set[frozenset[str]]) -> set[frozenset[str]]:
    normalized: set[frozenset[str]] = set()
    for pair in pairs:
        keys = {normalize_name(value) for value in pair if normalize_name(value)}
        if len(keys) == 2:
            normalized.add(frozenset(keys))
    return normalized


def _cannot_link_pairs(forms: dict[str, _Form]) -> set[frozenset[str]]:
    by_window: dict[str, set[str]] = {}
    for key, form in forms.items():
        for window_id in form.windows_as_speaker:
            by_window.setdefault(window_id, set()).add(key)
    pairs: set[frozenset[str]] = set()
    for keys in by_window.values():
        ordered = sorted(keys)
        for left_index, left in enumerate(ordered):
            for right in ordered[left_index + 1 :]:
                pairs.add(frozenset({left, right}))
    return pairs


def _clusters_conflict(
    left: set[str], right: set[str], cannot_link: set[frozenset[str]]
) -> bool:
    return any(frozenset({left_key, right_key}) in cannot_link for left_key in left for right_key in right)


def _cluster_pair_score(
    left_cluster: set[str],
    right_cluster: set[str],
    forms: dict[str, _Form],
    embeddings: dict[str, list[float]],
    confirmed_pairs: set[frozenset[str]],
) -> tuple[float, str, str, str]:
    best = (0.0, "none", min(left_cluster), min(right_cluster))
    for left_key in sorted(left_cluster):
        for right_key in sorted(right_cluster):
            score, reason = _form_pair_score(
                forms[left_key], forms[right_key], embeddings, confirmed_pairs
            )
            candidate = (score, reason, left_key, right_key)
            if candidate[0] > best[0] or (
                candidate[0] == best[0] and candidate[2:] < best[2:]
            ):
                best = candidate
    return best


def _form_pair_score(
    left: _Form,
    right: _Form,
    embeddings: dict[str, list[float]],
    confirmed_pairs: set[frozenset[str]],
) -> tuple[float, str]:
    pair = frozenset({left.key, right.key})
    if pair in confirmed_pairs:
        return 1.0, "prior_confirmed"
    if left.canonical_keys & ({right.key} | right.canonical_keys):
        return 0.99, "canonical_match"
    if right.canonical_keys & ({left.key} | left.canonical_keys):
        return 0.99, "canonical_match"

    string_score, string_reason = _string_similarity(left.key, right.key)
    embedding_score = cosine_similarity(
        embeddings.get(left.key, []), embeddings.get(right.key, [])
    )
    boosted_embedding = embedding_score * 0.9 if embedding_score >= 0.84 else 0.0
    if boosted_embedding > string_score:
        return boosted_embedding, "embedding"
    return string_score, string_reason


def _string_similarity(left: str, right: str) -> tuple[float, str]:
    if left == right:
        return 1.0, "normalized_exact"
    left_tokens = left.split()
    right_tokens = right.split()
    left_stripped = _strip_honorific(left_tokens)
    right_stripped = _strip_honorific(right_tokens)
    if left_stripped and left_stripped == right_stripped:
        return 0.98, "honorific_stripped"
    if left_tokens and right_tokens and left_tokens[-1] == right_tokens[-1]:
        if _initials_compatible(left_tokens, right_tokens):
            return 0.9, "surname_initial"
    ratio = SequenceMatcher(None, left, right).ratio()
    if max(len(left), len(right)) >= 6 and ratio >= 0.88:
        return min(0.89, ratio), "spelling_variant"
    return 0.0, "none"


def _strip_honorific(tokens: list[str]) -> str:
    if tokens and tokens[0] in HONORIFICS:
        return " ".join(tokens[1:])
    return " ".join(tokens)


def _initials_compatible(left: list[str], right: list[str]) -> bool:
    if len(left) == 1 or len(right) == 1:
        return True
    return left[0][0] == right[0][0]


def _cluster_payload(
    keys: set[str], forms: dict[str, _Form], embeddings: dict[str, list[float]]
) -> MentionCluster:
    ordered_keys = sorted(keys)
    mention_ids = sorted({mention_id for key in keys for mention_id in forms[key].mention_ids})
    surface_forms = sorted(
        {surface for key in keys for surface in forms[key].surface_forms},
        key=lambda item: item.casefold(),
    )
    digest = hashlib.sha256("\0".join(ordered_keys).encode("utf-8")).hexdigest()[:12]
    confidence = 1.0 if len(keys) == 1 else _cluster_confidence(ordered_keys, embeddings)
    return MentionCluster(
        id=f"castcluster_{digest}",
        mention_ids=mention_ids,
        normalized_keys=ordered_keys,
        surface_forms=surface_forms,
        confidence=round(confidence, 6),
    )


def _cluster_confidence(keys: list[str], embeddings: dict[str, list[float]]) -> float:
    similarities = [
        cosine_similarity(embeddings.get(left, []), embeddings.get(right, []))
        for left_index, left in enumerate(keys)
        for right in keys[left_index + 1 :]
        if embeddings.get(left) and embeddings.get(right)
    ]
    if similarities:
        return max(0.0, min(1.0, sum(similarities) / len(similarities)))
    return 0.85
