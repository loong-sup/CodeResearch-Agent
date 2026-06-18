## Why

The current frontend exposes code generation as a mode inside the codebase Q&A assistant, which makes the feature easy to miss and blurs two different user intents: asking about existing code and creating new code. A dedicated left-side code generation entry gives users a clear path for generating new implementation while preserving the ability to generate code from within repository Q&A when context naturally starts there.

## What Changes

- Add a dedicated left-side navigation button for code generation.
- Add a code generation page or route that opens directly into the code generation workflow.
- Keep code generation available inside the existing codebase Q&A assistant so users can ask about a repository and then request new code in the same context.
- Share repository selection, target language selection, streaming response rendering, citations, and generation metadata between the standalone entry and the embedded Q&A mode.
- Make the active left navigation state distinguish codebase Q&A from code generation.
- Preserve the existing codebase Q&A first screen and normal Q&A behavior.

## Capabilities

### New Capabilities

- `code-generation-entry`: Provide a dedicated frontend entry and workflow for code generation while retaining embedded generation inside codebase Q&A.

### Modified Capabilities

- None.

## Impact

- Frontend routing, left navigation, page composition, sender controls, and chat state initialization.
- Reuse of existing repository selection, code generation API client, streaming parser, markdown rendering, citations, and session state.
- Potential updates to page transport/session creation so starting from the new code generation entry defaults into generation mode without removing the Q&A mode.
- Frontend tests or type checks for navigation, default mode, API request payloads, and regression coverage for embedded Q&A code generation.
