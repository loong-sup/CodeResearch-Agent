## ADDED Requirements

### Requirement: Supported language selection
The system SHALL support code generation requests for exactly these target languages: C, C++, Python, TypeScript, and Java.

#### Scenario: Accepted target language
- **WHEN** a user submits a code generation request with target language `Python`
- **THEN** the system accepts the request and starts generating Python code

#### Scenario: Rejected unsupported language
- **WHEN** a user submits a code generation request with target language `Rust`
- **THEN** the system rejects the request with a clear unsupported-language error before invoking the model

### Requirement: Repository-aware generation
The system SHALL use selected repository context when generating code for a session with an available repository.

#### Scenario: Generate with selected repository
- **WHEN** a user submits a code generation request with a selected repository
- **THEN** the system retrieves relevant repository snippets and includes them in the generation context

#### Scenario: Selected repository unavailable
- **WHEN** a user submits a code generation request with a repository id that is unavailable to the session user
- **THEN** the system rejects the request with a clear repository-unavailable error

### Requirement: Generation output format
The system SHALL return generated code in markdown fenced code blocks using a syntax marker that matches the requested language.

#### Scenario: TypeScript output formatting
- **WHEN** a user requests TypeScript code generation
- **THEN** the generated answer includes a markdown code fence marked as `typescript`

#### Scenario: C++ output formatting
- **WHEN** a user requests C++ code generation
- **THEN** the generated answer includes a markdown code fence marked as `cpp`

### Requirement: Reviewable implementation guidance
The system SHALL include reviewable implementation guidance with generated code, including assumptions, suggested file locations when inferable, and repository citations for repository-specific claims.

#### Scenario: Repository-specific generated code
- **WHEN** generated code is based on retrieved repository snippets
- **THEN** the response includes citations for the repository-specific implementation details it uses

#### Scenario: Insufficient repository evidence
- **WHEN** retrieved repository snippets are insufficient to justify a repository-specific implementation
- **THEN** the response states the limitation and avoids presenting guessed project details as fact

### Requirement: Streaming generation response
The system SHALL stream code generation responses in a format compatible with the existing chat stream consumer.

#### Scenario: Streamed generation content
- **WHEN** a code generation request is accepted
- **THEN** the backend streams response chunks using `text/event-stream`

#### Scenario: Streamed references
- **WHEN** repository snippets are used for generation
- **THEN** the stream includes reference or citation metadata that the frontend can render with the generated answer

### Requirement: Frontend generation controls
The frontend SHALL provide a code generation mode with a target-language selector limited to C, C++, Python, TypeScript, and Java.

#### Scenario: User selects generation language
- **WHEN** a user enables code generation mode and selects `Java`
- **THEN** the frontend sends the request to the generation API with `language` set to `Java`

#### Scenario: Unsupported language not selectable
- **WHEN** a user opens the target-language selector
- **THEN** only C, C++, Python, TypeScript, and Java are available as options
