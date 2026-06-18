## Context

CodeResearch-Agent currently supports repository upload/indexing, repository-aware Q&A through `/ai_search/`, deeper agentic analysis through `/deep_research/`, and a React chat UI that streams SSE responses. The generation feature should reuse the existing repository resolution, retrieval, history, model streaming, and frontend chat rendering patterns while adding a clearer contract for code-output requests.

The supported generation languages are intentionally limited to C, C++, Python, TypeScript, and Java. This keeps prompt policy, syntax highlighting, validation, and tests bounded.

## Goals / Non-Goals

**Goals:**

- Provide a repository-aware code generation workflow for C, C++, Python, TypeScript, and Java.
- Validate the target language before model invocation.
- Reuse existing repository selection, retrieval, session history, and SSE streaming behavior where practical.
- Return generated code in fenced markdown blocks with language-specific syntax markers and actionable file/path guidance.
- Preserve source references used to shape the generated code so users can review assumptions.
- Expose generation from the frontend as a deliberate chat mode with target-language selection.

**Non-Goals:**

- Automatically modifying uploaded repositories or applying patches to user projects.
- Compiling, running, linting, or sandbox-executing generated code.
- Supporting languages beyond C, C++, Python, TypeScript, and Java in this change.
- Replacing the existing Q&A and deep research flows.

## Decisions

### Add a dedicated code generation request contract

Use a new backend request schema, for example `CodeGenerationRequest`, with `message`, `language`, optional `repository_id`/`repository_ids`, and optional generation controls. The route can be implemented as `/code_generation/` or an equivalent clearly named endpoint.

Rationale: a dedicated contract makes language validation and generation-specific prompt behavior explicit. Overloading `ChatRequest` with a loosely typed mode flag would make unsupported-language handling harder to enforce and test.

Alternative considered: adding `generation_language` to `/ai_search/`. This minimizes route count, but it couples normal Q&A and code-generation semantics and makes frontend state harder to reason about.

### Reuse retrieval and session plumbing

The code generation route should resolve repositories through `resolve_repository_context`, bind the selected repository to the session as existing chat does, retrieve relevant snippets with `retrieve_content`, and include `get_user_history_questions` in prompt construction.

Rationale: generated code must fit the selected project when repository context exists, and users should not have to reselect context separately from normal chat.

Alternative considered: generation without retrieval. This is simpler, but it would produce generic snippets and miss the core product value.

### Add a generation-specific prompt template

Add a prompt template such as `CodeGenerationPrompt` near the existing prompt definitions. It should require:

- generated code first when code is requested;
- fenced code blocks using the selected language marker;
- concise explanation and assumptions after the code;
- file/path suggestions when repository context implies likely locations;
- citations for repository-specific claims using the existing citation format;
- no claims of compilation or runtime validation unless those checks were actually performed.

Rationale: normal answer prompts optimize for explanation. Generation needs stricter output shape and explicit handling of assumptions.

Alternative considered: reuse `CodebaseAnswerPrompt`. It already handles code questions, but it does not enforce target-language selection or generation-specific output.

### Keep generation streaming compatible with existing frontend parsing

Return `text/event-stream` events with the same basic fields the chat UI already parses: `content`, `documents`, `citations`, `repository_context`, and error payloads. Add `generation_language` metadata if useful for UI badges or rendering.

Rationale: this avoids a separate stream parser and lets generated code render through the existing markdown component.

Alternative considered: return a complete JSON response. This is easier to test but loses consistency with long-running model responses in the current product.

### Frontend exposes generation as an explicit mode

Extend the sender/chat controls with a code generation mode and a language selector for C, C++, Python, TypeScript, and Java. When enabled, the frontend calls the generation endpoint and passes the selected language plus repository selection.

Rationale: users need to intentionally ask for generated code in a specific language, and unsupported values should be impossible from normal UI controls.

Alternative considered: infer language solely from the user prompt. Inference can still help default selection, but the final request should carry an explicit language.

## Risks / Trade-offs

- Ambiguous generation requests may produce code that does not fit the project structure -> prompt the model to state assumptions and include file/path suggestions rather than silently guessing.
- Retrieved snippets may be insufficient or irrelevant -> surface references and require the response to call out insufficient evidence when repository-specific code cannot be justified.
- Users may expect generated code to be applied automatically -> UI and response copy should make clear this feature generates reviewable code, not repository edits.
- Streaming model output can produce malformed markdown while still in progress -> rely on existing incremental markdown rendering and ensure final output uses complete fenced blocks.
- Multi-language support increases prompt and UI test surface -> centralize supported-language constants in backend and mirror them in frontend types/config.

## Migration Plan

1. Add backend schema, supported-language enum/constant, route, prompt template, and service function.
2. Add frontend API method and sender controls for generation mode and language selection.
3. Add tests for validation, prompt construction, stream metadata, frontend request payloads, and UI mode behavior.
4. Deploy with the feature available only through the new explicit mode. Existing `/ai_search/` and `/deep_research/` requests continue unchanged.
5. Roll back by hiding the frontend mode and disabling/removing the generation route; no data migration is required.

## Open Questions

- Should the product default to Python when no language is selected, or require an explicit language every time?
- Should web search be available for generation requests, or should generation rely only on repository context and model knowledge in the first version?
- Should generated output include a machine-readable patch format in addition to markdown code blocks in a later change?
