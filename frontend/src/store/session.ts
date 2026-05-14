import { proxy } from 'valtio'

const state = proxy({
  list: [] as API.Session[],
  useWeb: true,
  useDeep: true,
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
}

export const sessionState = state
export const sessionActions = actions
