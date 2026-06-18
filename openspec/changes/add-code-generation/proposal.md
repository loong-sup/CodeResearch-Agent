## Why

CodeResearch-Agent can answer questions about uploaded codebases, but users often need the next step: generating code changes, snippets, tests, or scaffolding that fit the repository they are researching. Adding code generation turns retrieved project context into actionable implementation output while keeping language support explicit and bounded.

## What Changes

- Add a code generation capability that accepts a user request, relevant repository context, and a target language.
- Support generation for C, C++, Python, TypeScript, and Java.
- Return generated code with enough surrounding explanation, file/path suggestions, and caveats for the user to review and apply.
- Validate target language selection and reject unsupported languages with a clear error.
- Integrate generation into the existing backend AI workflow so it can reuse uploaded repository indexes, conversation/session state, and retrieved references.
- Expose the capability through the frontend with controls for selecting generation mode and supported language.
- Add observability and tests around request validation, prompt construction, streaming/non-streaming responses, and frontend behavior.

## Capabilities

### New Capabilities

- `code-generation`: Generate repository-aware code output for C, C++, Python, TypeScript, and Java from user prompts and retrieved project context.

### Modified Capabilities

- None.

## Impact

- Backend FastAPI routes, schemas, and AI service/prompt orchestration for a new code generation request path.
- Retrieval/session services used to supply repository context to generation prompts.
- Frontend chat or tool UI for selecting code generation and target language.
- Configuration for model behavior, token limits, and generation-specific prompt templates.
- Tests for backend validation/service behavior and frontend request construction and rendering.
