## 1. Backend Contract

- [x] 1.1 Add a supported-language constant or enum for C, C++, Python, TypeScript, and Java with canonical markdown fence labels.
- [x] 1.2 Add a code generation request schema with `message`, `language`, optional `repository_id`, optional `repository_ids`, and optional generation controls.
- [x] 1.3 Add backend validation that rejects unsupported languages before repository retrieval or model invocation.

## 2. Backend Generation Flow

- [x] 2.1 Add a generation-specific prompt template that enforces code-first output, language-specific fenced code blocks, assumptions, file/path suggestions, and repository citations.
- [x] 2.2 Implement repository context resolution for generation requests, including explicit `repository_id`/`repository_ids` handling and session repository binding.
- [x] 2.3 Implement relevant code snippet retrieval for generation requests using the resolved repository context.
- [x] 2.4 Implement conversation history loading for generation requests so follow-up generation can use prior session context.
- [x] 2.5 Implement generation prompt construction that combines user intent, target language, retrieved snippets, repository context, conversation history, safety constraints, and output-format rules.
- [x] 2.6 Implement model streaming output for generation responses using the existing SSE event shape where possible.
- [x] 2.7 Add a dedicated code generation route that accepts the new request schema and returns `text/event-stream` responses compatible with the existing chat stream parser.
- [x] 2.8 Return clear stream or HTTP errors for unsupported languages and unavailable selected repositories.

## 3. Safety and Output Format

- [x] 3.1 Add generation safety constraints that prevent claiming code was compiled, tested, executed, or applied unless the system actually performed that action.
- [x] 3.2 Add prompt rules that require generated code to preserve repository-specific assumptions as review notes rather than silently inventing missing project details.
- [x] 3.3 Add output-format rules requiring generated code first, fenced code blocks with canonical language markers, concise explanation, assumptions, suggested file paths, and citations for repository-specific claims.
- [x] 3.4 Add error and limitation output rules for insufficient repository evidence, unsupported languages, and unavailable repositories.

## 4. Frontend Integration

- [x] 4.1 Add frontend API support for the code generation endpoint with typed request parameters.
- [x] 4.2 Add chat sender controls for enabling code generation mode and selecting C, C++, Python, TypeScript, or Java.
- [x] 4.3 Route generation-mode submissions through the new API while preserving selected repository behavior and existing streaming response handling.
- [x] 4.4 Render generation metadata or selected-language state in the chat UI without disrupting normal Q&A or deep research modes.

## 5. Tests and Verification

- [x] 5.1 Add backend tests for supported-language acceptance, unsupported-language rejection, and unavailable repository rejection.
- [x] 5.2 Add backend tests for repository context resolution, relevant snippet retrieval, conversation history loading, prompt construction, and model streaming handoff.
- [x] 5.3 Add backend tests for output-format rules, including language fence labels, assumptions, suggested file paths, limitation text, and repository citation requirements.
- [x] 5.4 Add backend tests for safety constraints, including no false claims about compilation, execution, testing, or applying code changes.
- [x] 5.5 Add frontend tests for generation mode request payloads and language selector options.
- [x] 5.6 Add end-to-end tests covering generation mode selection, repository selection, streaming response rendering, citations, and unsupported-language error handling.
- [ ] 5.7 Manually verify streaming generation for each supported language with and without a selected repository.
- [ ] 5.8 Run existing backend and frontend test/lint commands and address regressions.
