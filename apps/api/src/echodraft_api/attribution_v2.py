from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace

ATTRIBUTION_V2_VERSION = "attribution-v2-window-vote-reduce-0.1.0"
ATTRIBUTION_MID_CONFIDENCE = 0.8
ATTRIBUTION_VOTE_SAMPLES = 3
# Self-consistency voting resamples the attribution MAP at a mildly stochastic
# temperature so the k samples are genuinely independent draws rather than
# near-identical deterministic ones. See docs/architecture/extraction-pipeline-v2.md
# (§S4 self-consistency voting at temperature ~= 0.4).
ATTRIBUTION_VOTE_TEMPERATURE = 0.4


@dataclass(frozen=True)
class AttributionVote:
    segment_id: str
    character_key: str
    speaker_name: str
    confidence: float
    rationale: str


@dataclass(frozen=True)
class AttributionDecision(AttributionVote):
    method: str = "llm"
    tally: dict[str, int] | None = None


@dataclass(frozen=True)
class ConversationState:
    last_speaker: str | None = None
    turn_parity: int = 0
    open_addressee: str | None = None
    active_roster: tuple[str, ...] = ()

    def advance(
        self, speaker_name: str | None, *, open_addressee: str | None = None
    ) -> ConversationState:
        return replace(
            self,
            last_speaker=speaker_name or self.last_speaker,
            turn_parity=self.turn_parity + (1 if speaker_name else 0),
            open_addressee=open_addressee or self.open_addressee,
        )

    def as_prompt_payload(self) -> dict[str, object]:
        return {
            "lastSpeaker": self.last_speaker,
            "turnParity": self.turn_parity,
            "openAddressee": self.open_addressee,
            "activeRoster": list(self.active_roster),
        }


@dataclass(frozen=True)
class ResolvedTurn:
    segment_id: str
    scene_id: str
    speaker_name: str
    confidence: float
    user_locked: bool = False
    character_key: str | None = None
    method: str = "llm"


def majority_vote(segment_id: str, votes: list[AttributionVote]) -> AttributionDecision:
    eligible = [vote for vote in votes if vote.segment_id == segment_id and vote.character_key]
    if not eligible:
        return AttributionDecision(
            segment_id=segment_id,
            character_key="unknown",
            speaker_name="Unknown",
            confidence=0.0,
            rationale="No valid attribution votes were returned.",
        )
    base = eligible[0]
    tally = Counter(vote.character_key for vote in eligible)
    leaders = [key for key, count in tally.items() if count == max(tally.values())]
    if len(leaders) != 1:
        return AttributionDecision(
            **base.__dict__,
            method="llm",
            tally=dict(sorted(tally.items())),
        )
    winner = leaders[0]
    winning_votes = [vote for vote in eligible if vote.character_key == winner]
    representative = max(winning_votes, key=lambda item: item.confidence)
    agreement = len(winning_votes) / len(eligible)
    return AttributionDecision(
        segment_id=segment_id,
        character_key=winner,
        speaker_name=representative.speaker_name,
        confidence=round(agreement, 6),
        rationale=representative.rationale,
        method="vote" if len(eligible) > 1 else "llm",
        tally=dict(sorted(tally.items())),
    )


def alternation_repairs(
    turns: list[ResolvedTurn],
    scene_rosters: dict[str, tuple[str, str]],
    *,
    confidence_threshold: float = ATTRIBUTION_MID_CONFIDENCE,
) -> list[ResolvedTurn]:
    repairs: list[ResolvedTurn] = []
    by_scene: dict[str, list[ResolvedTurn]] = {}
    for turn in turns:
        by_scene.setdefault(turn.scene_id, []).append(turn)
    for scene_id, scene_turns in by_scene.items():
        roster = scene_rosters.get(scene_id)
        if not roster or len(scene_turns) < 3:
            continue
        previous_speaker: str | None = None
        established = False
        for turn in scene_turns:
            if turn.speaker_name not in roster:
                previous_speaker = None
                established = False
                continue
            if previous_speaker is None:
                previous_speaker = turn.speaker_name
                continue
            expected = roster[1] if previous_speaker == roster[0] else roster[0]
            if not established:
                if turn.speaker_name == expected:
                    established = True
                previous_speaker = turn.speaker_name
                continue
            if (
                turn.speaker_name != expected
                and turn.confidence < confidence_threshold
                and not turn.user_locked
            ):
                repaired = replace(
                    turn,
                    speaker_name=expected,
                    character_key=expected,
                    confidence=0.82,
                    method="reduce_repair",
                )
                repairs.append(repaired)
                previous_speaker = expected
            else:
                previous_speaker = turn.speaker_name
    return repairs
