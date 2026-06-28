# Direction Studio

Direction Studio stores delivery controls per segment without changing canonical manuscript text.

## Controls

- controlled emotion: `neutral`, `warm`, `tense`, `quiet`, `urgent`, `somber`, `bright`, `fearful`, `angry`
- pace from `0.5` to `2.0`
- intensity from `0.0` to `1.0`
- pause before and after in milliseconds
- emphasis and whisper flags
- optional style prompt

## Inference

`POST /api/v1/projects/{projectId}/directions/infer` runs deterministic local inference across project segments. It uses text cues such as exclamation marks, questions, whisper words, and somber terms. Locked rows are preserved.

## Production Resolution

Direction resolution follows this order:

1. legacy segment production override direction
2. Segment Direction record
3. project default direction
4. neutral segment default

The resolved direction payload is part of the segment render fingerprint, so changing a segment direction marks only affected segment renders stale.

## API

- `GET /api/v1/projects/{projectId}/segment-directions`
- `GET /api/v1/projects/{projectId}/segments/{segmentId}/direction`
- `PUT /api/v1/projects/{projectId}/segments/{segmentId}/direction`
- `POST /api/v1/projects/{projectId}/directions/infer`
