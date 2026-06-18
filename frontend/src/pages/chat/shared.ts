import { PageTransportKey } from '@/utils'

export type ChatEnterData = {
  message: string
  mode?: 'chat' | 'code-generation'
  language?: API.CodeGenerationLanguage
  repository_id?: string
}

export const transportToChatEnter = Symbol() as PageTransportKey<{
  data: ChatEnterData
}>

let id = 0

export const createChatId = () => {
  return ++id
}

export function createChatIdText(id: number) {
  return `chat-item-${id}`
}
