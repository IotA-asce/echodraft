# Design System Primitives Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Establish Echodraft's monochrome token layer and accessible Button, Select, Range, Modal, Drawer, and Toast primitives, then replace the current raw select/range chrome without changing workflow behavior.

**Architecture:** Keep global design decisions in `app/design-system/tokens.css` and isolate component visuals in a CSS Module. Client primitives own their WAI-ARIA keyboard/focus behavior; existing feature components receive the same values and callbacks through the new controlled APIs, leaving data fetching and domain logic untouched.

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript 5.8, CSS Modules, Playwright.

---

### Task 1: Add tokens and primitive contracts

**Files:**
- Create: `apps/web/app/design-system/tokens.css`
- Create: `apps/web/app/design-system/primitives.module.css`
- Create: `apps/web/app/design-system/Button.tsx`
- Create: `apps/web/app/design-system/Select.tsx`
- Create: `apps/web/app/design-system/Range.tsx`
- Create: `apps/web/app/design-system/overlays.tsx`
- Create: `apps/web/app/design-system/index.ts`
- Modify: `apps/web/app/layout.tsx`

**Steps:**
1. Export the documented neutral ramp, semantic light/dark roles, typography, spacing, elevation, z-index, motion, and reduced-motion values.
2. Implement controlled Button, custom listbox Select, and styled semantic Range primitives with focus-visible and disabled states.
3. Implement portal-based Modal/Drawer focus containment and a polite, capped Toast provider.
4. Run `npm run web:typecheck` and fix all primitive contract errors.

### Task 2: Migrate current browser chrome

**Files:**
- Modify: feature components under `apps/web/app/components/`
- Modify: `apps/web/app/project-dashboard.tsx`
- Modify: `apps/web/app/globals.css`

**Steps:**
1. Replace every raw `<select>` with the controlled Select primitive.
2. Replace every raw range input with the Range primitive.
3. Replace inline destructive confirmation with the Modal primitive and raw evidence disclosure with a Drawer.
4. Bridge legacy palette variables to semantic neutral tokens so unmigrated surfaces remain functional but monochrome.
5. Confirm `rg '<select|type="range"|<details|<summary' apps/web/app -g '*.tsx'` returns no primary-UI occurrences.

### Task 3: Verify and deliver

**Files:**
- Modify: `apps/web/tests/foundations.spec.ts`
- Modify: `docs/plans/v2-implementation-roadmap.md`
- Modify: `docs/progress-tracker.md`

**Steps:**
1. Update smoke interactions for the custom combobox keyboard/click contract and add primitive accessibility coverage.
2. Run `npm run web:lint`, `npm run web:typecheck`, `npm run web:test:smoke`, and `npm run --workspace @echodraft/web build`.
3. Mark W7.1 complete only after verification passes.
4. Commit `feat: add monochrome design system primitives`, merge to `main`, and push both refs.
