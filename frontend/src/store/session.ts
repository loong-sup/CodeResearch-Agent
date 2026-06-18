import { proxy } from 'valtio'

const state = proxy({
  list: [] as API.Session[],
  useWeb: true,
  useDeep: true,
  useCodeGeneration: false,
  codeGenerationLanguage: 'Python' as API.CodeGenerationLanguage,
})

const actions = {
  setList(list: API.Session[]) {
    state.list = list
  },
  add(item: API.Session) {
    state.list.push(item)
  },
  setUseWeb(useWeb: boolean) {
    state.useWeb = useWeb
  },

  setUseDeep(useDeep: boolean) {
    state.useDeep = useDeep
  },

  setUseCodeGeneration(useCodeGeneration: boolean) {
    state.useCodeGeneration = useCodeGeneration
    if (useCodeGeneration) {
      state.useDeep = false
    }
  },

  setCodeGenerationLanguage(language: API.CodeGenerationLanguage) {
    state.codeGenerationLanguage = language
  },
}

export const sessionState = state
export const sessionActions = actions
