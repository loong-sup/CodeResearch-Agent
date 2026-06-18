## Context

The current frontend uses a base layout with a compact left navigation (`frontend/src/layout/base/nav.tsx`) and routes for the home page, chat page, and repository page. Code generation currently lives as a mode inside the chat sender, which is useful during repository Q&A but does not give code generation a clear first-class entry in the product.

This change is primarily frontend-focused. It should build on the code generation API and streaming behavior introduced by the `add-code-generation` change, while keeping the existing codebase Q&A assistant intact.

## Goals / Non-Goals

**Goals:**

- Add a dedicated left navigation button for code generation.
- Add a standalone code generation entry route or page that defaults to code generation mode.
- Preserve code generation inside the codebase Q&A assistant for follow-up implementation requests after repository exploration.
- Reuse repository selection, language selection, API request logic, SSE parsing, markdown code rendering, citations, and generation metadata wherever practical.
- Keep active navigation state clear so users can distinguish repository Q&A, repository management, and standalone code generation.
- Keep the first screen usable and task-oriented rather than adding a marketing/landing page.

**Non-Goals:**

- Creating a separate backend code generation API if the existing generation API is already available.
- Removing the code generation control from the Q&A assistant.
- Automatically applying generated code to uploaded repositories.
- Redesigning repository upload/indexing workflows.

## Decisions

### Add a dedicated code generation route

Add a route such as `/code-generation` that opens a focused generation page. The page can reuse the existing chat page components or compose the same sender/result components, but it should initialize generation mode and language selection by default.

Rationale: a route makes the left navigation entry stable, bookmarkable, and easy to test. It also avoids overloading the existing home page with too many default modes.

Alternative considered: make the left nav button simply toggle code generation mode on the existing home page. That is simpler but creates unclear navigation state and makes browser history less predictable.

### Reuse chat/session flow with explicit generation defaults

The standalone entry should create or open a chat session in the same way the current home-to-chat flow works, but pass metadata that initializes `useCodeGeneration=true` and a default language such as Python. The chat page should still allow users to disable generation mode if they intentionally want normal Q&A.

Rationale: reusing session history and stream parsing avoids duplicate state and keeps generated outputs available in the existing chat history model.

Alternative considered: a fully separate generation state store and result page. That would isolate UX but duplicate streaming, citations, repository context, and history behavior.

### Keep embedded Q&A code generation

The codebase Q&A sender should retain the code generation toggle and language selector. Users often discover implementation requirements while asking about existing code, so forcing them to leave the Q&A context would add friction and lose repository context.

Rationale: standalone and embedded generation serve different entry points, not different backend capabilities.

Alternative considered: remove the code generation toggle from Q&A and rely only on the left nav entry. That makes the new feature more prominent but weakens repository-aware follow-up workflows.

### Add an explicit left navigation item and active state

Add a code generation item to `Nav`, with a code-oriented icon and title. Navigation styling should indicate the active route for `/`, `/chat/:id`, `/repository`, and `/code-generation` where feasible.

Rationale: the new entry must be visible and understandable from anywhere in the app.

Alternative considered: only add a button on the home page. That would not satisfy the requirement for a left-side dedicated button.

## Risks / Trade-offs

- Users may expect the standalone code generation page to operate without a repository -> allow generation without a repository, but clearly preserve repository selection when available.
- Reusing chat page state may leak previous mode defaults between Q&A and standalone generation -> initialize mode from route/transport explicitly and reset only the intended mode fields.
- Adding another nav button may crowd the compact sidebar -> use an icon-sized button with tooltip/title consistent with existing nav items.
- Existing code generation mode has runtime dependencies on the backend generation API -> show stream/API errors in the existing assistant answer area rather than failing silently.

## Migration Plan

1. Add the code generation route and left navigation item.
2. Add transport/session metadata for starting chat in generation mode.
3. Update chat page initialization so standalone generation defaults to `useCodeGeneration=true` while normal Q&A keeps its current defaults.
4. Reuse existing sender controls and result rendering for both standalone and embedded generation.
5. Add frontend verification for navigation, default mode, language selection, repository preservation, and embedded Q&A generation.

## Open Questions

- Should the standalone generation page start from a new session every time, or offer a recent generation session list later?
- Should the default language be Python because it is common and already visible in the screenshot, or should the route require explicit language selection before sending?
