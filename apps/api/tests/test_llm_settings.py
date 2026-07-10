from echodraft_db import Database, LlmSettingsRepository


def test_llm_settings_defaults_to_local_ollama(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    row = repo.get()

    assert row.provider == "ollama"
    assert row.base_url is None
    assert row.model is None
    assert row.api_key is None
    assert row.cloud_consent is False


def test_llm_settings_update_round_trips(tmp_path) -> None:
    database = Database(f"sqlite:///{tmp_path}/settings.db")
    database.create_schema()
    repo = LlmSettingsRepository(database)

    repo.update(
        provider="openai_compat",
        base_url="https://api.x.ai/v1",
        model="grok-4.5",
        api_key="xai-secret",
        cloud_consent=True,
    )
    row = repo.get()

    assert row.provider == "openai_compat"
    assert row.base_url == "https://api.x.ai/v1"
    assert row.model == "grok-4.5"
    assert row.api_key == "xai-secret"
    assert row.cloud_consent is True
    assert row.updated_at is not None
