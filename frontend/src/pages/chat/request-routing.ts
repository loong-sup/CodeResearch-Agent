export type ChatRequestRoutingInput = {
  useCodeGeneration: boolean
  codeGenerationLanguage: API.CodeGenerationLanguage
  useWeb: boolean
  useDeep: boolean
  repositoryId?: string
}

export type ChatRequestRoutingResult =
  | {
      endpoint: 'code_generation'
      payload: {
        language: API.CodeGenerationLanguage
        repository_id?: string
      }
    }
  | {
      endpoint: 'ai_search'
      payload: {
        web_search: boolean
        deep_research: boolean
        repository_id?: string
      }
    }

export function resolveChatRequestRouting(
  input: ChatRequestRoutingInput,
): ChatRequestRoutingResult {
  if (input.useCodeGeneration) {
    return {
      endpoint: 'code_generation',
      payload: {
        language: input.codeGenerationLanguage,
        repository_id: input.repositoryId,
      },
    }
  }

  return {
    endpoint: 'ai_search',
    payload: {
      web_search: input.useWeb,
      deep_research: input.useDeep,
      repository_id: input.repositoryId,
    },
  }
}
