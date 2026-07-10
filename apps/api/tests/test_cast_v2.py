from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import echodraft_api.cast_discovery as cast_discovery_module
from echodraft_api.cast_v2 import ClusterMention, cluster_mentions, cosine_similarity
from echodraft_api.config import AppSettings


def _mention(
    mention_id: str,
    name: str,
    *,
    window: str,
    role: str = "mentioned",
    canonical: str | None = None,
) -> ClusterMention:
    return ClusterMention(
        id=mention_id,
        surface_name=name,
        canonical_guess=canonical,
        evidence_text=f"Evidence for {name}",
        window_id=window,
        role_in_scene=role,
    )


def test_cosine_similarity_is_safe_for_empty_and_orthogonal_vectors() -> None:
    assert cosine_similarity([], []) == 0.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine_similarity([1.0, 1.0], [1.0, 1.0]) == 1.0


def test_cluster_mentions_combines_string_and_embedding_aliases() -> None:
    mentions = [
        _mention("m1", "Captain Reyes", window="w1", role="speaker"),
        _mention("m2", "Reyes", window="w2", role="speaker"),
        _mention("m3", "the captain", window="w3"),
        _mention("m4", "Dr. Sen", window="w4", role="speaker"),
    ]
    embeddings = {
        "captain reyes": [1.0, 0.0, 0.0],
        "reyes": [0.98, 0.02, 0.0],
        "the captain": [0.96, 0.04, 0.0],
        "dr sen": [0.0, 1.0, 0.0],
    }

    result = cluster_mentions(mentions, embeddings=embeddings)

    assert [cluster.surface_forms for cluster in result.clusters] == [
        ["Captain Reyes", "Reyes", "the captain"],
        ["Dr. Sen"],
    ]
    assert result.embedding_used is True
    assert len(result.merges) == 2


def test_cluster_mentions_enforces_distinct_speaker_cannot_link_transitively() -> None:
    mentions = [
        _mention("m1", "Alex", window="shared", role="speaker"),
        _mention("m2", "Alec", window="shared", role="speaker"),
        _mention("m3", "Alexander", window="other", role="mentioned"),
    ]
    embeddings = {
        "alex": [1.0, 0.0],
        "alec": [0.99, 0.01],
        "alexander": [0.995, 0.005],
    }

    result = cluster_mentions(mentions, embeddings=embeddings)

    assert len(result.clusters) == 2
    assert not any(
        {"Alex", "Alec"} <= set(cluster.surface_forms) for cluster in result.clusters
    )
    assert ["alec", "alex"] in result.cannot_link_pairs


def test_cluster_mentions_respects_prior_rulings_and_string_only_fallback() -> None:
    mentions = [
        _mention("m1", "Liz", window="shared", role="speaker"),
        _mention("m2", "Elizabeth", window="shared", role="speaker"),
        _mention("m3", "Marian", window="w3", role="speaker"),
        _mention("m4", "Maria", window="w4", role="speaker"),
    ]

    result = cluster_mentions(
        mentions,
        confirmed_pairs={frozenset({"liz", "elizabeth"})},
        rejected_pairs={frozenset({"marian", "maria"})},
    )

    assert result.embedding_used is False
    assert any(
        {"Liz", "Elizabeth"} == set(cluster.surface_forms)
        for cluster in result.clusters
    )
    assert not any(
        {"Marian", "Maria"} <= set(cluster.surface_forms)
        for cluster in result.clusters
    )


def test_cluster_output_is_deterministic_for_reordered_mentions() -> None:
    mentions = [
        _mention("m2", "Reyes", window="w2"),
        _mention("m1", "Captain Reyes", window="w1"),
        _mention("m3", "Dr. Sen", window="w3"),
    ]

    forward = cluster_mentions(mentions)
    backward = cluster_mentions(list(reversed(mentions)))

    assert [cluster.id for cluster in forward.clusters] == [
        cluster.id for cluster in backward.clusters
    ]
    assert [cluster.mention_ids for cluster in forward.clusters] == [
        cluster.mention_ids for cluster in backward.clusters
    ]


def test_cast_v2_feature_flag_reads_both_environment_names(monkeypatch) -> None:
    monkeypatch.setenv("ECHODRAFT_CAST_V2_ENABLED", "true")
    assert AppSettings.from_environment().cast_v2_enabled is True

    monkeypatch.delenv("ECHODRAFT_CAST_V2_ENABLED")
    monkeypatch.setenv("ECHODRAFT_CAST_V2", "1")
    assert AppSettings.from_environment().cast_v2_enabled is True


def test_cast_v2_service_writes_profiles_and_cluster_diagnostics(
    client, monkeypatch
) -> None:
    container = client.app.state.container
    container.settings = replace(container.settings, cast_v2_enabled=True)
    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_local_llm_ready",
        lambda _self: False,
    )

    def fake_embeddings(_self, mentions):
        keys = {cast_discovery_module._name_key(mention.surface_name) for mention in mentions}
        return (
            {
                key: ([1.0, 0.0] if "reyes" in key or key == "the captain" else [0.0, 1.0])
                for key in keys
                if key
            },
            [],
        )

    monkeypatch.setattr(
        cast_discovery_module.CastDiscoveryService,
        "_cast_embeddings",
        fake_embeddings,
    )
    project = client.post(
        "/api/v1/projects",
        json={"title": "Cast v2", "rightsStatus": "declared"},
    ).json()["id"]
    import_job = client.post(
        f"/api/v1/projects/{project}/source/import",
        files={
            "file": (
                "book.txt",
                b"Chapter 1\n\nCaptain Reyes: Hold.\n\nReyes: Move.\n\nDr. Sen: Wait.",
                "text/plain",
            )
        },
        data={"rightsAcknowledged": "true"},
    ).json()
    assert _wait_for_job(client, import_job["id"])["status"] == "succeeded"
    extract_job = client.post(
        f"/api/v1/projects/{project}/structure/extract",
        json={"maxSegmentChars": 120},
    ).json()
    assert _wait_for_job(client, extract_job["id"])["status"] == "succeeded"

    project_record = container.projects.get(project)
    assert project_record is not None
    manifest_path = Path(project_record.artifact_path) / "manifests" / "casting_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["manifestVersion"] == "cast-v2"
    assert manifest["payload"]["castV2"]["embeddingUsed"] is True
    assert manifest["payload"]["clusters"]
    assert manifest["payload"]["clusterDiagnostics"] is not None
    assert manifest["payload"]["profiles"]
    assert all(profile["characterId"] for profile in manifest["payload"]["profiles"])
    active_names = {
        character["displayName"]
        for character in client.get(f"/api/v1/projects/{project}/characters").json()
        if not character["mergedIntoCharacterId"]
    }
    assert "Dr. Sen" in active_names
    assert len([name for name in active_names if "Reyes" in name]) == 1


def test_profile_synthesis_updates_existing_character_fields(client, monkeypatch) -> None:
    service = cast_discovery_module.CastDiscoveryService(client.app.state.container)
    candidate = cast_discovery_module.CharacterCandidate(
        display_name="Captain Reyes",
        canonical_name="Elena Reyes",
        aliases=["Reyes"],
        first_seen_segment_id="seg_1",
        first_seen_chapter_id="ch_1",
        evidence=["{}"],
        role_guess="supporting",
        confidence=0.82,
        source="cast_v2_cluster",
        mention_evidence=["evidence"],
        window_ids=["win_1"],
    )
    observed_tasks: list[str] = []

    def fake_extract(_self, _project_id, request, _job_id=None):
        observed_tasks.append(request.task)
        return SimpleNamespace(
            run=SimpleNamespace(id="llm_profile_1"),
            result={
                "profile": {
                    "displayName": "Elena Reyes",
                    "role": "protagonist",
                    "gender": "feminine",
                    "ageBand": "adult",
                    "traits": ["authoritative", "dry-humored"],
                    "speechStyle": {
                        "register": "formal",
                        "verbosity": "terse",
                        "accentHint": "none",
                        "tics": ["clipped commands"],
                    },
                    "relationships": [],
                    "confidence": 0.94,
                },
                "warnings": [],
            },
        )

    monkeypatch.setattr(cast_discovery_module.LocalLlmService, "extract", fake_extract)
    updated, profile = service._profile_candidate(
        "project_1", candidate, use_local_llm=True
    )

    assert observed_tasks == ["cast_profile_synthesis"]
    assert updated.role_guess == "protagonist"
    assert {"gender:feminine", "age:adult", "authoritative"} <= set(updated.traits)
    assert {"register:formal", "verbosity:terse", "clipped commands"} <= set(
        updated.speaking_style
    )
    assert profile["llmRunId"] == "llm_profile_1"


def test_cluster_reconciliation_is_one_call_for_the_pooled_candidate(
    client, monkeypatch
) -> None:
    service = cast_discovery_module.CastDiscoveryService(client.app.state.container)
    candidate = cast_discovery_module.CharacterCandidate(
        display_name="Captain Reyes",
        canonical_name="Elena Reyes",
        aliases=["Reyes", "the captain"],
        first_seen_segment_id="seg_1",
        first_seen_chapter_id="ch_1",
        evidence=["{}"],
        role_guess="supporting",
        confidence=0.91,
        source="cast_v2_cluster",
        mention_evidence=["one", "two", "three"],
        window_ids=["win_1", "win_2"],
    )
    calls: list[tuple[str, list[str]]] = []

    def fake_reconcile(_project_id, pooled, shortlist, *, task):
        calls.append((task, pooled.aliases))
        return cast_discovery_module.MergeDecision(
            id="decision_1",
            action="new",
            target_character_id=None,
            target_name=None,
            aliases=[],
            confidence=0.93,
            reason="Cluster evidence describes one new character.",
            evidence_segment_ids=["seg_1"],
        )

    monkeypatch.setattr(service, "_llm_merge_decision", fake_reconcile)
    decision = service._decision_for_cluster(
        "project_1",
        candidate,
        cast_discovery_module.CharacterIndex(characters=[]),
        use_local_llm=True,
    )

    assert calls == [("cast_cluster_reconcile", ["Reyes", "the captain"])]
    assert decision.action == "new"
    assert decision.metadata["reconcileMode"] == "cluster"


def _wait_for_job(client, job_id: str) -> dict[str, object]:
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"succeeded", "failed"}:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not finish")
