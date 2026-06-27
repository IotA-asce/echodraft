# README dashboard assets

These assets are real screenshots of the current `apps/web` dashboard captured with Playwright against deterministic mocked API responses. They do not contain private manuscripts, generated audiobook audio, local `.echodraft` data, or production artifacts.

## Regenerate

From the repository root:

```bash
node docs/assets/capture-readme-assets.mjs
```

The script starts the Next.js dashboard on `127.0.0.1:3100`, intercepts browser API requests with representative local-first audiobook data, captures the dashboard states, and assembles the GIF with ImageMagick. Set `ECHODRAFT_CAPTURE_PORT` to use a different port.

If a Next dev server is already running for `apps/web`, reuse it instead:

```bash
ECHODRAFT_CAPTURE_BASE_URL=http://127.0.0.1:3000 node docs/assets/capture-readme-assets.mjs
```

ImageMagick must provide the `magick` command. Playwright browsers must already be installed for the web test environment.

## Assets

| File | Represents |
| --- | --- |
| `dashboard-projects.png` | The landing dashboard with the project creation card and local project library. |
| `manuscript-import.png` | The manuscript intake section with a normalized parser preview. |
| `voice-setup.png` | Managed Kokoro setup and narrator voice selection. |
| `segment-editor.png` | Chapter structure browsing with the inline segment revision editor open. |
| `review-patch-export.gif` | Review, issue discussion/patching context, and export packaging sections. |

The capture data is intentionally small and fictional. If the dashboard UI changes, regenerate these files and update this README if the represented states change.
