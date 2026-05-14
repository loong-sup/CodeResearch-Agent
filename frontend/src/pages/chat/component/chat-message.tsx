/* eslint-disable @typescript-eslint/no-unused-expressions */
import { ChatRole, ChatType } from '@/configs'
import { SyncOutlined } from '@ant-design/icons'
import classNames from 'classnames'
import { useMemo } from 'react'
import { createChatIdText } from '../shared'
import styles from './chat-message.module.css'
import { Result } from './result'

// 用户消息组件，渲染用户发送的消息
function UserMessage(props: { item: API.ChatItem }) {
  const { item } = props

  return (
    <div
      className={classNames(
        styles['chat-message-item'],
        styles['chat-message-item--user'],
      )}
    >
      {item.content}
    </div>
  )
}

function ResearchLoading(props: {
  status: 'processing' | 'success' | 'failed'
}) {
  const { status } = props
  if (status === 'success') return null

  return (
    <div className={styles['chat-status']}>
      {status === 'processing' ? (
        <>
          深度探索中
          <SyncOutlined spin style={{ marginLeft: 8 }} />
        </>
      ) : (
        '失败'
      )}
    </div>
  )
}

// AI助手消息组件，渲染AI回复的消息
function AssistantMessage(props: {
  item: API.ChatItem
  isEnd?: boolean
  onSend?: (text: string) => void
}) {
  const { item, isEnd, onSend } = props

  // 为文档类型消息生成唯一ID，用于定位和滚动
  const id = useMemo(() => {
    if (item.type === ChatType.Document) {
      return createChatIdText(item.id)
    }
  }, [item.id, item.type])

  return (
    <div id={id} className={classNames(styles['chat-message-item'])}>
      <Result item={item} isEnd={isEnd} onSend={onSend} />
    </div>
  )
}

// 聊天消息列表组件，根据消息类型渲染不同的消息组件
export default function ChatMessage(props: {
  list: API.ChatItem[]
  loading?: boolean
  deepResearch?: boolean
  onSend?: (text: string) => void
}) {
  const { list, onSend } = props

  return (
    <div className={styles['chat-message']}>
      {list.map((item, index) => {
        if (item.role === ChatRole.User) {
          const status: Parameters<typeof ResearchLoading>[0]['status'] =
            props.loading ? 'processing' : 'success'
          return (
            <div className={styles['user-message--wrapper']} key={item.id}>
              <UserMessage item={item} />
              {props.deepResearch && <ResearchLoading status={status} />}
            </div>
          )
        }

        return (
          <AssistantMessage
            key={item.id}
            item={item}
            isEnd={list.length - 1 === index}
            onSend={onSend}
          />
        )
      })}
    </div>
  )
}
