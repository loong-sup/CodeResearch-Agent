import { CODE_GENERATION_LANGUAGE_OPTIONS } from '@/components/sender/code-generation-options'
import { getActiveNavKey } from '@/layout/base/nav-config'

const defaultLanguage: API.CodeGenerationLanguage = 'Python'

if (!CODE_GENERATION_LANGUAGE_OPTIONS.some((item) => item.value === defaultLanguage)) {
  throw new Error('Standalone code generation default language must be supported.')
}

if (getActiveNavKey('/code-generation') !== 'code-generation') {
  throw new Error('Standalone code generation route must have an active nav item.')
}
