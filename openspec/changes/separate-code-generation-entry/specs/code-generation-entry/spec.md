## ADDED Requirements

### Requirement: Dedicated code generation navigation
The frontend SHALL provide a dedicated left-side navigation button for code generation.

#### Scenario: Code generation button is visible
- **WHEN** a user views the application shell
- **THEN** the left navigation includes a code generation button separate from the codebase Q&A and repository buttons

#### Scenario: Code generation button opens standalone workflow
- **WHEN** a user clicks the code generation button
- **THEN** the application opens a standalone code generation workflow

### Requirement: Standalone generation defaults
The standalone code generation workflow SHALL default to code generation mode with a supported target language selected.

#### Scenario: Standalone entry defaults to generation mode
- **WHEN** a user opens the standalone code generation workflow
- **THEN** the sender is configured to submit requests through the code generation API by default

#### Scenario: Supported language is selected
- **WHEN** a user opens the standalone code generation workflow
- **THEN** the language selector shows one of the supported code generation languages

### Requirement: Embedded Q&A generation remains available
The codebase Q&A assistant SHALL continue to support code generation inside the existing chat workflow.

#### Scenario: User generates code from Q&A
- **WHEN** a user is in the codebase Q&A assistant
- **THEN** the user can enable code generation mode and submit a generation request without leaving the current chat

#### Scenario: Q&A mode remains available
- **WHEN** a user is in the codebase Q&A assistant
- **THEN** normal codebase Q&A remains available when code generation mode is disabled

### Requirement: Shared repository context
The standalone and embedded code generation workflows SHALL reuse repository selection and repository-aware generation behavior.

#### Scenario: Standalone generation with repository selected
- **WHEN** a user selects a repository in the standalone code generation workflow and submits a request
- **THEN** the request includes the selected repository id

#### Scenario: Embedded generation preserves repository context
- **WHEN** a user enables code generation in an existing repository Q&A chat
- **THEN** the generation request uses the active repository context when one is selected

### Requirement: Shared rendering and feedback
The standalone and embedded code generation workflows SHALL render streaming generated code, citations, repository context, and errors through the existing assistant response UI.

#### Scenario: Generated code streams in standalone workflow
- **WHEN** the backend streams a standalone code generation response
- **THEN** the frontend displays the generated content incrementally in the assistant answer area

#### Scenario: Generation errors are visible
- **WHEN** a code generation request fails
- **THEN** the frontend displays the error in the assistant answer area without leaving the page blank

### Requirement: Active navigation state
The frontend SHALL distinguish the active left navigation state for code generation, codebase Q&A, and repository management.

#### Scenario: Code generation route active state
- **WHEN** the user is on the standalone code generation workflow
- **THEN** the code generation navigation button is visually active

#### Scenario: Repository route active state
- **WHEN** the user is on the repository page
- **THEN** the repository navigation button is visually active
