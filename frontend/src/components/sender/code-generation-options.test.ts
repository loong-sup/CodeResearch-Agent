import {
  CODE_GENERATION_LANGUAGE_OPTIONS,
  isCodeGenerationLanguage,
} from './code-generation-options'

const expectedLanguages: API.CodeGenerationLanguage[] = [
  'C',
  'C++',
  'Python',
  'TypeScript',
  'Java',
]

const actualLanguages = CODE_GENERATION_LANGUAGE_OPTIONS.map((option) => option.value)

if (actualLanguages.join('|') !== expectedLanguages.join('|')) {
  throw new Error('Code generation language options changed unexpectedly.')
}

if (isCodeGenerationLanguage('Rust')) {
  throw new Error('Unsupported language must not be accepted by frontend helper.')
}

if (!isCodeGenerationLanguage('Java')) {
  throw new Error('Supported language must be accepted by frontend helper.')
}
