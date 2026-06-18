## 1. Navigation and Routing

- [x] 1.1 Add a dedicated code generation route such as `/code-generation`.
- [x] 1.2 Add a left navigation item for code generation with a code-oriented icon and accessible title.
- [x] 1.3 Add active navigation styling for code generation, repository management, and Q&A routes.
- [x] 1.4 Verify direct browser navigation to `/code-generation` opens the standalone workflow.

## 2. Standalone Generation Workflow

- [x] 2.1 Create a standalone code generation page or page wrapper that reuses existing chat/sender/result components where practical.
- [x] 2.2 Initialize standalone generation with `useCodeGeneration=true`.
- [x] 2.3 Initialize a supported default target language, preferably Python unless product requirements specify otherwise.
- [x] 2.4 Ensure standalone generation can select a repository and pass the selected repository id to the generation request.
- [x] 2.5 Ensure standalone generation can submit requests without a repository and still render a useful response or backend error.

## 3. Embedded Q&A Generation Preservation

- [x] 3.1 Keep the code generation toggle and language selector available inside the codebase Q&A assistant.
- [x] 3.2 Ensure disabling code generation in Q&A returns requests to the normal `/ai_search/` flow.
- [x] 3.3 Ensure enabling code generation in Q&A sends requests through `/code_generation/`.
- [x] 3.4 Preserve active repository context when switching from Q&A to code generation within the same chat.

## 4. Shared Rendering and State

- [x] 4.1 Reuse the existing SSE parser for standalone and embedded code generation responses.
- [x] 4.2 Render generated code through the existing markdown/code block renderer.
- [x] 4.3 Render citations, repository context, generation language metadata, and errors consistently in both workflows.
- [x] 4.4 Avoid leaking standalone generation defaults into normal Q&A sessions unless the user explicitly enables generation.

## 5. UX and Layout

- [x] 5.1 Update standalone code generation copy/placeholders to focus on generating new code, tests, scaffolding, or implementation changes.
- [x] 5.2 Keep the first screen task-oriented and avoid adding a marketing landing page.
- [x] 5.3 Verify the left navigation remains usable and non-overlapping at common desktop and narrow viewport widths.
- [x] 5.4 Verify sender controls fit without text overlap when repository selection, code generation, language selection, and web search are visible.

## 6. Tests and Verification

- [x] 6.1 Add frontend coverage for the code generation navigation item and route.
- [x] 6.2 Add frontend coverage for standalone generation default mode and language selection.
- [x] 6.3 Add frontend coverage for embedded Q&A generation mode request routing.
- [x] 6.4 Add frontend coverage for repository id preservation in standalone and embedded generation requests.
- [x] 6.5 Run the frontend build/type check and address regressions.
- [ ] 6.6 Manually verify standalone generation and embedded Q&A generation against a running backend.
