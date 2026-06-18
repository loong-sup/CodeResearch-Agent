export const CODE_GENERATION_LANGUAGE_OPTIONS: {
  label: API.CodeGenerationLanguage
  value: API.CodeGenerationLanguage
}[] = [
  { label: 'C', value: 'C' },
  { label: 'C++', value: 'C++' },
  { label: 'Python', value: 'Python' },
  { label: 'TypeScript', value: 'TypeScript' },
  { label: 'Java', value: 'Java' },
]

export function isCodeGenerationLanguage(
  value: string,
): value is API.CodeGenerationLanguage {
  return CODE_GENERATION_LANGUAGE_OPTIONS.some((option) => option.value === value)
}
