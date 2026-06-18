import * as api from '@/api'
import { transportToChatEnter } from '@/pages/chat/shared'
import { sessionActions } from '@/store/session'
import { setPageTransport } from '@/utils'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'

type SendMessageOptions = {
  mode?: 'chat' | 'code-generation'
  language?: API.CodeGenerationLanguage
  repository_id?: string
}

export default function useSendMessage() {
  const navigate = useNavigate()

  return async (
    message: string,
    optionsOrFiles?: SendMessageOptions | string[],
  ) => {
    const options = Array.isArray(optionsOrFiles) ? undefined : optionsOrFiles
    const { data } = await api.session.create()
    const sessionId = data.session_id

    sessionActions.add({
      session_id: sessionId,
      session_name: message,
      created_at: dayjs().format('YYYY-MM-DD HH:mm:ss'),
      updated_at: dayjs().format('YYYY-MM-DD HH:mm:ss'),
    })
    setPageTransport(transportToChatEnter, {
      data: {
        message,
        mode: options?.mode,
        language: options?.language,
        repository_id: options?.repository_id,
      },
    })
    navigate(`/chat/${sessionId}`)
  }
}
