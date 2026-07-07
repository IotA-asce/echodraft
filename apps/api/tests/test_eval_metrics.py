from echodraft_api.eval.metrics import (
    AttributionGold,
    AttributionPrediction,
    CastGoldCharacter,
    CastPredictedCluster,
    attribution_metrics,
    cast_metrics,
    flag_metrics,
)


def test_attribution_metrics_score_accuracy_precision_recall_and_ambiguity() -> None:
    gold = [
        AttributionGold(id="a", gold_speaker="Elizabeth Bennet", agreement="unanimous"),
        AttributionGold(id="b", gold_speaker="Fitzwilliam Darcy", agreement="resolved"),
        AttributionGold(id="c", gold_speaker=None, ambiguous=True, agreement="disagreement"),
    ]
    predictions = [
        AttributionPrediction(id="a", predicted_speaker="Elizabeth Bennet", confidence=0.95),
        AttributionPrediction(id="b", predicted_speaker="Unknown", confidence=0.45),
        AttributionPrediction(id="c", predicted_speaker="Darcy", confidence=0.2),
    ]

    metrics = attribution_metrics(gold, predictions, high_threshold=0.85, mid_threshold=0.55)

    assert metrics.evaluated_rows == 2
    assert metrics.accuracy == 0.5
    assert metrics.auto_accept_precision == 1.0
    assert metrics.auto_accept_rows == 1
    assert metrics.recall_of_attributable_dialogue == 0.5
    assert metrics.ambiguity_recall == 1.0
    assert metrics.human_agreement_rate == 1 / 3
    assert 0.0 <= metrics.expected_calibration_error <= 1.0


def test_cast_metrics_report_roster_and_dedupe_errors() -> None:
    gold = [
        CastGoldCharacter("Mary Hail", aliases=("Mary", "Mrs. Hail")),
        CastGoldCharacter("Grace", aliases=("Dr. Grace",)),
        CastGoldCharacter("Rocky", aliases=("Amaze",)),
    ]
    predicted = [
        CastPredictedCluster(("Mary", "Mrs. Hail")),
        CastPredictedCluster(("Dr. Grace", "Amaze")),
        CastPredictedCluster(("Mary Hail",)),
    ]

    metrics = cast_metrics(gold, predicted)

    assert metrics.true_positives == 2
    assert metrics.false_positives == 1
    assert metrics.false_negatives == 1
    assert metrics.roster_precision == 2 / 3
    assert metrics.roster_recall == 2 / 3
    assert metrics.merge_error_rate == 1 / 3
    assert metrics.split_error_rate == 1 / 3
    assert 0.0 <= metrics.alias_cluster_purity <= 1.0


def test_flag_metrics_count_by_book_and_severity() -> None:
    metrics = flag_metrics(
        "pride-and-prejudice",
        [
            {"severity": "warning"},
            {"severity": "blocking"},
            {"severity": "warning"},
            {},
        ],
        pages=200,
    )

    assert metrics.book_slug == "pride-and-prejudice"
    assert metrics.flag_count == 4
    assert metrics.flags_per_100_pages == 2.0
    assert metrics.by_severity == {"blocking": 1, "unknown": 1, "warning": 2}
