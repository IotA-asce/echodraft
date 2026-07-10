# UI Virtualization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Virtualize the segment editor, chapter timeline, and transcript review lists without changing their data or interaction contracts.

**Architecture:** Use `@tanstack/react-virtual` against each existing bounded scroll container, with dynamic row measurement for editor/transcript content and React 19-compatible `useFlushSync: false`. Keep full arrays in memory and preserve stable domain IDs as virtual item keys; only visible rows plus overscan are mounted.

**Tech Stack:** React 19, Next.js 16, TanStack Virtual 3.14, Playwright.

---

1. Add the pinned virtualizer dependency while staging only W7.2 lockfile hunks.
2. Virtualize `SegmentList` with dynamic measurement, stable keys, and overscan.
3. Virtualize `ChapterTimeline` and `ChapterTranscriptReview` inside their existing bounded scrollers.
4. Add a 6,000-row smoke fixture asserting mounted row counts stay bounded and distant rows become reachable by scrolling.
5. Run frontend lint, typecheck, smoke, and production build.
6. Update W7.2 roadmap evidence, commit, merge, and push.
