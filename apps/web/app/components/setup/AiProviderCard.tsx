"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getLlmSettings,
  testLlmConnection,
  updateLlmSettings,
  type LlmConnectionTest,
} from "../../api";

const XAI_DEFAULT_BASE_URL = "https://api.x.ai/v1";
const XAI_DEFAULT_MODEL = "grok-4.5";

export function AiProviderCard() {
  const queryClient = useQueryClient();
  const settings = useQuery({ queryKey: ["llm-settings"], queryFn: getLlmSettings });
  const [draft, setDraft] = useState<{
    provider: string;
    baseUrl: string;
    model: string;
    apiKey: string;
    cloudConsent: boolean;
  } | null>(null);
  const [testResult, setTestResult] = useState<LlmConnectionTest | null>(null);

  const save = useMutation({
    mutationFn: updateLlmSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(["llm-settings"], data);
      setDraft(null);
      setTestResult(null);
    },
  });
  const test = useMutation({ mutationFn: testLlmConnection, onSuccess: setTestResult });

  if (settings.isPending) return <article className="studio-card">Loading AI provider…</article>;
  if (settings.isError) {
    return <article className="studio-card">AI provider settings unavailable.</article>;
  }
  const current = settings.data;
  const form = draft ?? {
    provider: current.provider,
    baseUrl: current.baseUrl ?? XAI_DEFAULT_BASE_URL,
    model: current.model ?? XAI_DEFAULT_MODEL,
    apiKey: "",
    cloudConsent: current.cloudConsent,
  };
  const isCloud = form.provider === "openai_compat";
  const canSave =
    !save.isPending &&
    (!isCloud ||
      (form.cloudConsent &&
        (form.apiKey !== "" || current.hasApiKey) &&
        form.baseUrl.trim() !== "" &&
        form.model.trim() !== ""));

  return (
    <article className="studio-card ai-provider-card">
      <div className="model-card-heading">
        <div>
          <strong>AI Provider</strong>
          <small>Book understanding: structure, characters, attribution, direction</small>
        </div>
        <span className={`model-badge ${current.provider === "ollama" ? "ready" : "info"}`}>
          {current.provider === "ollama" ? "local · ollama" : `cloud · ${current.model ?? "?"}`}
        </span>
      </div>
      {current.envOverrides.length > 0 ? (
        <small>Environment overrides active: {current.envOverrides.join(", ")}</small>
      ) : null}
      <label>
        Provider
        <select
          value={form.provider}
          onChange={(e) => setDraft({ ...form, provider: e.target.value })}
        >
          <option value="ollama">Local (Ollama)</option>
          <option value="openai_compat">Cloud (OpenAI-compatible, e.g. xAI)</option>
        </select>
      </label>
      {isCloud ? (
        <>
          <label>
            Base URL
            <input
              type="text"
              value={form.baseUrl}
              onChange={(e) => setDraft({ ...form, baseUrl: e.target.value })}
            />
          </label>
          <label>
            Model
            <input
              type="text"
              value={form.model}
              onChange={(e) => setDraft({ ...form, model: e.target.value })}
            />
          </label>
          <label>
            API key {current.hasApiKey ? <small>(saved — leave blank to keep)</small> : null}
            <input
              type="password"
              value={form.apiKey}
              placeholder={current.hasApiKey ? "••••••••" : "xai-…"}
              onChange={(e) => setDraft({ ...form, apiKey: e.target.value })}
            />
          </label>
          <label className="rights-check">
            <input
              type="checkbox"
              checked={form.cloudConsent}
              onChange={(e) => setDraft({ ...form, cloudConsent: e.target.checked })}
            />
            <span>
              I understand manuscript text will be sent to this provider&apos;s servers.
              Echodraft remains local-first; this is strictly opt-in.
            </span>
          </label>
          <div className="model-actions">
            <button
              type="button"
              className="small-button"
              disabled={test.isPending || !form.baseUrl}
              onClick={() =>
                test.mutate({
                  baseUrl: form.baseUrl,
                  ...(form.apiKey ? { apiKey: form.apiKey } : {}),
                  ...(form.model ? { model: form.model } : {}),
                })
              }
            >
              Test connection
            </button>
          </div>
          {testResult ? (
            <small role="status">
              {testResult.ok
                ? `Connected. ${testResult.models.length} models${
                    testResult.modelFound === false ? ` — ${form.model} NOT found` : ""
                  }${testResult.modelFound ? ` — ${form.model} available` : ""}`
                : `Connection failed: ${testResult.error}`}
            </small>
          ) : null}
        </>
      ) : null}
      <div className="model-actions">
        <button
          type="button"
          className="small-button"
          disabled={!canSave}
          onClick={() =>
            save.mutate({
              provider: form.provider,
              baseUrl: isCloud ? form.baseUrl : null,
              model: isCloud ? form.model : null,
              ...(form.apiKey !== "" ? { apiKey: form.apiKey } : {}),
              cloudConsent: isCloud ? form.cloudConsent : false,
            })
          }
        >
          {save.isPending ? "Saving…" : "Save provider"}
        </button>
        {save.isError ? <small role="alert">{String(save.error)}</small> : null}
      </div>
    </article>
  );
}
