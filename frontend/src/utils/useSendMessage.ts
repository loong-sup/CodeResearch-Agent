import * as api from '@/api'
import { transportToChatEnter } from '@/pages/chat/shared'
import { sessionActions } from '@/store/session'
import { setPageTransport } from '@/utils'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'

export default function useSendMessage() {
  const navigate = useNavigate()

  return async (message: string) => {
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
      },
    })
    navigate(`/chat/${sessionId}`)
  }
}
