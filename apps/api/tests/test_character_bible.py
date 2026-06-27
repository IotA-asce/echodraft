def test_character_bible_update_voice_split_and_merge(client) -> None:
    project = client.post(
        "/api/v1/projects", json={"title": "Character Bible", "rightsStatus": "declared"}
    ).json()["id"]
    voice = client.post(
        f"/api/v1/projects/{project}/voices",
        json={"name": "Mara voice", "backend": "mock", "providerVoiceId": "mock-mara"},
    ).json()

    created = client.post(
        f"/api/v1/projects/{project}/characters",
        json={
            "displayName": "Mara Vale",
            "canonicalName": "Mara",
            "aliases": ["Captain Vale", "Mara"],
            "traits": ["dry", "observant"],
            "firstSeenSourceId": "src_1",
            "roleType": "major",
            "notes": "Primary viewpoint.",
        },
    )
    assert created.status_code == 201
    character = created.json()
    assert character["canonicalName"] == "Mara"
    assert character["aliases"] == ["Captain Vale", "Mara"]
    assert character["traits"] == ["dry", "observant"]
    assert character["voiceProfileId"] is None

    updated = client.patch(
        f"/api/v1/characters/{character['id']}",
        json={
            "canonicalName": "Mara Vale",
            "traits": ["dry", "observant", "guarded"],
            "userLocked": True,
            "lockReason": "Approved by editor.",
            "voiceProfileId": voice["id"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["voiceProfileId"] == voice["id"]
    assert updated.json()["userLocked"] is True
    assert updated.json()["traits"] == ["dry", "observant", "guarded"]

    split = client.post(
        f"/api/v1/characters/{character['id']}/split",
        json={
            "displayName": "Mara in disguise",
            "aliases": ["The courier"],
            "traits": ["guarded"],
            "reason": "Disguise has separate attribution evidence.",
        },
    )
    assert split.status_code == 201
    split_character = split.json()
    assert split_character["splitHistory"][0]["sourceCharacterId"] == character["id"]

    merged = client.post(
        f"/api/v1/characters/{character['id']}/merge",
        json={
            "sourceCharacterId": split_character["id"],
            "reason": "Reviewed and confirmed as the same speaker.",
        },
    )
    assert merged.status_code == 200
    merged_character = merged.json()
    assert "Mara in disguise" in merged_character["aliases"]
    assert merged_character["voiceProfileId"] == voice["id"]
    assert merged_character["mergeHistory"][0]["sourceCharacterId"] == split_character["id"]

    listed = client.get(f"/api/v1/projects/{project}/characters").json()
    source_record = next(item for item in listed if item["id"] == split_character["id"])
    assert source_record["mergedIntoCharacterId"] == character["id"]
    assert source_record["userLocked"] is True
    assert "Mara Vale" in {item["displayName"] for item in listed}
