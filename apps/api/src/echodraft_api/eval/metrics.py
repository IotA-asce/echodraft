from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class AttributionGold:
    id: str
    gold_speaker: str | None
    ambiguous: bool = False
    agreement: str | None = None


@dataclass(frozen=True)
class AttributionPrediction:
    id: str
    predicted_speaker: str | None
    confidence: float


@dataclass(frozen=True)
class AttributionMetrics:
    accuracy: float
    auto_accept_precision: float
    recall_of_attributable_dialogue: float
    ambiguity_recall: float
    expected_calibration_error: float
    human_agreement_rate: float
    evaluated_rows: int
    auto_accept_rows: int


@dataclass(frozen=True)
class CastGoldCharacter:
    canonical_name: str
    aliases: tuple[str, ...] = ()

    @property
    def surfaces(self) -> set[str]:
        return {_name_key(self.canonical_name), *{_name_key(alias) for alias in self.aliases}} - {""}


@dataclass(frozen=True)
class CastPredictedCluster:
    surfaces: tuple[str, ...]

    @property
    def surface_keys(self) -> set[str]:
        return {_name_key(surface) for surface in self.surfaces} - {""}


@dataclass(frozen=True)
class CastMetrics:
    roster_precision: float
    roster_recall: float
    roster_f1: float
    merge_error_rate: float
    split_error_rate: float
    alias_cluster_purity: float
    true_positives: int
    false_positives: int
    false_negatives: int


@dataclass(frozen=True)
class FlagMetrics:
    book_slug: str
    flag_count: int
    pages: int | None = None
    flags_per_100_pages: float | None = None
    by_severity: dict[str, int] = field(default_factory=dict)


def attribution_metrics(
    gold_rows: Iterable[AttributionGold],
    predictions: Iterable[AttributionPrediction],
    *,
    high_threshold: float = 0.85,
    mid_threshold: float = 0.55,
    ece_bins: int = 10,
) -> AttributionMetrics:
    gold = list(gold_rows)
    predicted_by_id = {row.id: row for row in predictions}
    joined = [(row, predicted_by_id.get(row.id)) for row in gold]
    non_ambiguous = [(row, pred) for row, pred in joined if not row.ambiguous and row.gold_speaker]
    correct = [
        _same_speaker(pred.predicted_speaker if pred else None, row.gold_speaker)
        for row, pred in non_ambiguous
    ]
    auto_accept = [
        (row, pred)
        for row, pred in joined
        if pred is not None and pred.confidence >= high_threshold
    ]
    auto_correct = [
        _same_speaker(pred.predicted_speaker, row.gold_speaker)
        for row, pred in auto_accept
        if row.gold_speaker is not None
    ]
    attributable = [
        pred is not None and _name_key(pred.predicted_speaker) not in {"", "unknown"}
        for row, pred in non_ambiguous
        if row.gold_speaker is not None
    ]
    ambiguous_rows = [(row, pred) for row, pred in joined if row.ambiguous or row.gold_speaker is None]
    ambiguity_hits = [
        pred is None or pred.confidence < mid_threshold or _name_key(pred.predicted_speaker) == "unknown"
        for _row, pred in ambiguous_rows
    ]
    unanimous = [row.agreement == "unanimous" for row in gold if row.agreement is not None]

    return AttributionMetrics(
        accuracy=_ratio(sum(correct), len(correct)),
        auto_accept_precision=_ratio(sum(auto_correct), len(auto_accept)),
        recall_of_attributable_dialogue=_ratio(sum(attributable), len(attributable)),
        ambiguity_recall=_ratio(sum(ambiguity_hits), len(ambiguity_hits)),
        expected_calibration_error=_expected_calibration_error(non_ambiguous, ece_bins),
        human_agreement_rate=_ratio(sum(unanimous), len(unanimous)),
        evaluated_rows=len(non_ambiguous),
        auto_accept_rows=len(auto_accept),
    )


def cast_metrics(
    gold_characters: Iterable[CastGoldCharacter],
    predicted_clusters: Iterable[CastPredictedCluster],
) -> CastMetrics:
    gold = list(gold_characters)
    predicted = list(predicted_clusters)
    weights: dict[tuple[int, int], float] = {}
    for predicted_index, cluster in enumerate(predicted):
        for gold_index, character in enumerate(gold):
            weights[(predicted_index, gold_index)] = _jaccard(cluster.surface_keys, character.surfaces)

    predicted_best = {
        pred_i: _best_index(
            ((gold_i, weights[(pred_i, gold_i)]) for gold_i in range(len(gold))),
        )
        for pred_i in range(len(predicted))
    }
    gold_best = {
        gold_i: _best_index(
            ((pred_i, weights[(pred_i, gold_i)]) for pred_i in range(len(predicted))),
        )
        for gold_i in range(len(gold))
    }
    mutual_matches = {
        (pred_i, gold_i)
        for pred_i, gold_i in predicted_best.items()
        if gold_i is not None and gold_best.get(gold_i) == pred_i
    }
    true_positives = len(mutual_matches)
    false_positives = max(0, len(predicted) - true_positives)
    false_negatives = max(0, len(gold) - true_positives)
    precision = _ratio(true_positives, true_positives + false_positives)
    recall = _ratio(true_positives, true_positives + false_negatives)

    gold_by_surface = {
        surface: index
        for index, character in enumerate(gold)
        for surface in character.surfaces
    }
    cluster_gold_sets = [
        {gold_by_surface[surface] for surface in cluster.surface_keys if surface in gold_by_surface}
        for cluster in predicted
    ]
    merge_errors = sum(1 for gold_set in cluster_gold_sets if len(gold_set) >= 2)
    clusters_by_gold: dict[int, set[int]] = defaultdict(set)
    for cluster_index, cluster in enumerate(predicted):
        for surface in cluster.surface_keys:
            matched_gold_index = gold_by_surface.get(surface)
            if matched_gold_index is not None:
                clusters_by_gold[matched_gold_index].add(cluster_index)
    split_errors = sum(1 for cluster_indexes in clusters_by_gold.values() if len(cluster_indexes) >= 2)

    return CastMetrics(
        roster_precision=precision,
        roster_recall=recall,
        roster_f1=_f1(precision, recall),
        merge_error_rate=_ratio(merge_errors, len(gold)),
        split_error_rate=_ratio(split_errors, len(gold)),
        alias_cluster_purity=_v_measure(cluster_gold_sets),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
    )


def flag_metrics(
    book_slug: str,
    flags: Iterable[dict[str, object]],
    *,
    pages: int | None = None,
) -> FlagMetrics:
    severities = Counter(str(flag.get("severity") or "unknown") for flag in flags)
    flag_count = sum(severities.values())
    return FlagMetrics(
        book_slug=book_slug,
        flag_count=flag_count,
        pages=pages,
        flags_per_100_pages=_ratio(flag_count * 100, pages) if pages else None,
        by_severity=dict(sorted(severities.items())),
    )


def _expected_calibration_error(
    rows: list[tuple[AttributionGold, AttributionPrediction | None]],
    bins: int,
) -> float:
    scored = [(row, pred) for row, pred in rows if pred is not None]
    if not scored or bins <= 0:
        return 0.0
    total = len(scored)
    error = 0.0
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            (row, pred)
            for row, pred in scored
            if _in_confidence_bucket(pred.confidence, lower, upper, is_last=index == bins - 1)
        ]
        if not bucket:
            continue
        confidence = sum(pred.confidence for _row, pred in bucket) / len(bucket)
        accuracy = sum(
            _same_speaker(pred.predicted_speaker, row.gold_speaker)
            for row, pred in bucket
        ) / len(bucket)
        error += (len(bucket) / total) * abs(accuracy - confidence)
    return error


def _in_confidence_bucket(
    confidence: float,
    lower: float,
    upper: float,
    *,
    is_last: bool,
) -> bool:
    return lower <= confidence <= upper if is_last else lower <= confidence < upper


def _best_index(candidates: Iterable[tuple[int, float]]) -> int | None:
    best: tuple[int, float] | None = None
    for index, score in candidates:
        if score <= 0:
            continue
        if best is None or score > best[1]:
            best = (index, score)
    return best[0] if best else None


def _v_measure(cluster_gold_sets: list[set[int]]) -> float:
    labels: list[tuple[int, int]] = []
    for cluster_index, gold_set in enumerate(cluster_gold_sets):
        for gold_index in gold_set:
            labels.append((cluster_index, gold_index))
    if not labels:
        return 0.0
    cluster_counts = Counter(cluster for cluster, _gold in labels)
    gold_counts = Counter(gold for _cluster, gold in labels)
    joint_counts = Counter(labels)
    total = len(labels)
    homogeneity = _conditional_score(joint_counts, cluster_counts, gold_counts, total)
    completeness = _conditional_score(
        Counter((gold, cluster) for cluster, gold in labels),
        gold_counts,
        cluster_counts,
        total,
    )
    return _ratio(2 * homogeneity * completeness, homogeneity + completeness)


def _conditional_score(
    joint_counts: Counter[tuple[int, int]],
    outer_counts: Counter[int],
    inner_counts: Counter[int],
    total: int,
) -> float:
    entropy = -sum((count / total) * math.log(count / total) for count in inner_counts.values())
    if entropy == 0:
        return 1.0
    conditional = 0.0
    for (outer, inner), count in joint_counts.items():
        conditional -= (count / total) * math.log(count / outer_counts[outer])
    return 1.0 - (conditional / entropy)


def _same_speaker(left: str | None, right: str | None) -> bool:
    return _name_key(left) == _name_key(right) and _name_key(left) != ""


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _ratio(numerator: float | int, denominator: float | int) -> float:
    return 0.0 if denominator == 0 else float(numerator) / float(denominator)


def _f1(precision: float, recall: float) -> float:
    return _ratio(2 * precision * recall, precision + recall)
