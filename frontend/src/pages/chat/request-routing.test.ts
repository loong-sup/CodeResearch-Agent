import { resolveChatRequestRouting } from './request-routing'

const generationRoute = resolveChatRequestRouting({
  useCodeGeneration: true,
  codeGenerationLanguage: 'Java',
  useWeb: true,
  useDeep: false,
  repositoryId: 'repo-1',
})

if (generationRoute.endpoint !== 'code_generation') {
  throw new Error('Code generation mode must use the code generation endpoint.')
}

if (generationRoute.payload.repository_id !== 'repo-1') {
  throw new Error('Code generation routing must preserve selected repository id.')
}

const qaRoute = resolveChatRequestRouting({
  useCodeGeneration: false,
  codeGenerationLanguage: 'Python',
  useWeb: true,
  useDeep: false,
  repositoryId: 'repo-2',
})

if (qaRoute.endpoint !== 'ai_search') {
  throw new Error('Disabled code generation mode must use the Q&A endpoint.')
}

if (qaRoute.payload.repository_id !== 'repo-2') {
  throw new Error('Q&A routing must preserve selected repository id.')
}
