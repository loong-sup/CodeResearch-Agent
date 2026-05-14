import * as api from '@/api'
import ComPageLayout from '@/components/page-layout'
import ComSender from '@/components/sender'
import { ChatRole, ChatType } from '@/configs'
import { deviceActions } from '@/store/device'
import { sessionState } from '@/store/session'
import { usePageTransport } from '@/utils'
import { useMount, useRequest, useUnmount } from 'ahooks'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { proxy, useSnapshot } from 'valtio'
import ChatMessage from './component/chat-message'
import styles from './index.module.scss'
import { createChatId, transportToChatEnter } from './shared'

function buildCitationsFromDocuments(documents: API.Document[] = []): API.Citation[] {
  return documents
    .filter((item) => item.citation)
    .map((item) => ({
      id: item.id,
      chunk_id: item.chunk_id,
      citation: item.citation!,
      citation_display: item.citation_display || `[${item.citation}]`,
      file_path: item.file_path,
      start_line: item.start_line,
      end_line: item.end_line,
      symbol: item.symbol,
      language: item.language,
      chunk_kind: item.chunk_kind,
      preview: item.content_with_weight?.slice(0, 240),
    }))
}

// 滚动到页面底部的辅助函数，当距离底部小于阈值时自动滚动
async function scrollToBottom() {
  await new Promise((resolve) => setTimeout(resolve))

  const threshold = 200
  const distanceToBottom =
    document.documentElement.scrollHeight -
    document.documentElement.scrollTop -
    document.documentElement.clientHeight

  if (distanceToBottom <= threshold) {
    window.scrollTo({
      top: document.documentElement.scrollHeight,
      behavior: 'smooth',
    })
  }
}

export default function Index() {
  const { id } = useParams()
  const { data: ctx } = usePageTransport(transportToChatEnter)
  const sessionStore = useSnapshot(sessionState)
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>()
  const [activeRepositoryContext, setActiveRepositoryContext] = useState<
    API.RepositoryContext[]
  >([])

  // 使用valtio管理聊天消息列表状态
  const [chat] = useState(() => {
    return proxy({
      list: [] as API.ChatItem[],
    })
  })
  const { list } = useSnapshot(chat) as { list: API.ChatItem[] }

  // 加载聊天历史记录
  const history = useRequest(
    async () => {
      const { data } = await api.session.detail({
        session_id: id!,
      })
      return data
    },
    {
      manual: true,
      onSuccess(data) {
        let latestRepositoryContext: API.RepositoryContext[] = []
        data.forEach((item) => {
          if (item.user_question) {
            chat.list.push({
              id: createChatId(),
              role: ChatRole.User,
              type: ChatType.Text,
              content: item.user_question,
            })
          }

          if (item.model_answer) {
            let reference: API.Document[] = []
            let recommended_questions: string[] = []

            if (item.documents) {
              try {
                reference = JSON.parse(item.documents) as API.Document[]
              } catch (error) {
                console.error(error)
              }
            }

            if (item.recommended_questions) {
              try {
                // 后端返回的最后一条内容的最前面有多余字符`"`，需要去掉
                recommended_questions = (item.recommended_questions || []).map(
                  (q) => q.replace(/^"/, ''),
                )
              } catch (error) {
                console.error(error)
              }
            }

            const repositoryContext = reference.length
              ? Array.from(
                  new Map(
                    reference
                      .filter((doc) => doc.repository_id && doc.repository_name)
                      .map((doc) => [
                        doc.repository_id!,
                        {
                          repository_id: doc.repository_id!,
                          repository_name: doc.repository_name!,
                          repository_type: doc.repository_type,
                        },
                      ]),
                  ).values(),
                )
              : undefined

            chat.list.push({
              id: createChatId(),
              role: ChatRole.Assistant,
              type: ChatType.Document,
              content: item.model_answer,
              think: item.think,
              reference: reference,
              citations: buildCitationsFromDocuments(reference),
              repository_context: repositoryContext,
              recommended_questions: recommended_questions?.length
                ? recommended_questions
                : undefined,
            })
            if (repositoryContext?.length) {
              latestRepositoryContext = repositoryContext
            }
          }
        })

        if (latestRepositoryContext.length) {
          setActiveRepositoryContext(latestRepositoryContext)
          setSelectedRepositoryId(latestRepositoryContext[0]?.repository_id)
        }

        setTimeout(() => {
          window.scrollTo({
            top: document.documentElement.scrollHeight,
          })
        })
      },
    },
  )

  const repositories = useRequest(
    async () => {
      const { data } = await api.repository.list()
      return data || []
    },
    {
      manual: true,
    },
  )

  const repositoryOptions = useMemo(() => {
    return (repositories.data || [])
      .filter((item) => item.repository_id)
      .map((item) => ({
        label: item.file_name,
        value: item.repository_id!,
        description: [item.repository_type, item.indexed_chunks ? `${item.indexed_chunks} chunks` : '']
          .filter(Boolean)
          .join(' · '),
      }))
  }, [repositories.data])

  useEffect(() => {
    if (!repositoryOptions.length) return
    if (
      selectedRepositoryId &&
      repositoryOptions.some((item) => item.value === selectedRepositoryId)
    ) {
      return
    }
    setSelectedRepositoryId(repositoryOptions[0].value)
  }, [repositoryOptions, selectedRepositoryId])

  const loading = useMemo(() => {
    return list.some((o) => o.loading) || history.loading
  }, [list, history.loading])
  const loadingRef = useRef(loading)
  loadingRef.current = loading
  useEffect(() => {
    deviceActions.setChatting(loading)
  }, [loading])
  useUnmount(() => {
    deviceActions.setChatting(false)
  })

  // 发送聊天消息并处理流式响应
  const sendChat = useCallback(
    async (target: API.ChatItem, message: string, attachments?: string[]) => {
      target.loading = true
      try {
        const repositoryId = await resolveRepositoryForMessage(message)
        const res = await api.session.chat({
          id: id!,
          message,
          web_search: sessionStore.useWeb,
          deep_research: sessionStore.useDeep,
          attachments: attachments,
          repository_id: repositoryId,
        })

        // 获取流式响应的reader
        const reader = res.data.getReader()
        if (!reader) return

        await read(reader)
      } catch (error: unknown) {
        target.error = (error as Error)?.message ?? 'Unknown error'
        throw error
      } finally {
        target.loading = false
      }

      // 读取流式响应数据
      async function read(
        reader: ReadableStreamDefaultReader<AllowSharedBufferSource>,
      ) {
        let temp = ''
        const decoder = new TextDecoder('utf-8')
        while (true) {
          const { value, done } = await reader.read()
          temp += decoder.decode(value)

          // 按行解析SSE数据
          while (true) {
            const index = temp.indexOf('\n')
            if (index === -1) break

            const slice = temp.slice(0, index)
            temp = temp.slice(index + 1)

            if (slice.startsWith('data: ')) {
              parseData(slice)
              scrollToBottom()
            }
          }

          if (done) {
            console.debug('数据接受完毕', temp)
            target.loading = false
            break
          }
        }
      }

      // 解析SSE数据并更新聊天消息
      function parseData(slice: string) {
        try {
          const str = slice
            .trim()
            .replace(/^data: /, '')
            .trim()
          if (str === '[DONE]') {
            return
          }

          const json = JSON.parse(str)
          // 处理内容更新，区分思考内容和回答内容
          if (json?.content) {
            if (json.thinking) {
              target.think = `${target.think || ''}${json.content || ''}`
            } else {
              target.content = `${target.content || ''}${json.content || ''}`
            }
          }

          // 处理参考文档
          if (json?.documents?.length) {
            target.reference = json.documents
            if (!target.citations?.length) {
              target.citations = buildCitationsFromDocuments(json.documents)
            }
          }

          if (json?.citations?.length) {
            target.citations = json.citations
          }

          if (json?.repository_context?.length) {
            target.repository_context = json.repository_context
            setActiveRepositoryContext(json.repository_context)
            const resolvedRepositoryId = json.repository_context[0]?.repository_id
            if (resolvedRepositoryId) {
              setSelectedRepositoryId(resolvedRepositoryId)
            }
          }

          // 处理推荐问题
          if (json?.recommended_questions?.length) {
            target.recommended_questions = json.recommended_questions
          }

          // 处理图片结果
          if (json?.image_results) {
            target.image_results = json.image_results
          }

          // 处理视频结果
          if (json?.video_results) {
            target.video_results = json.video_results
          }
        } catch {
          console.debug('解析失败')
          console.debug(slice)
        }
      }

      async function resolveRepositoryForMessage(message: string) {
        if (selectedRepositoryId) return selectedRepositoryId
        if (repositoryOptions.length === 1) {
          const onlyRepositoryId = repositoryOptions[0].value
          setSelectedRepositoryId(onlyRepositoryId)
          return onlyRepositoryId
        }
        if (!message.trim() || !repositoryOptions.length) return undefined
        try {
          const { data } = await api.session.getRepositoryCandidates({
            question: message,
            session_id: id,
          })
          const candidate = (data || []).find((item) =>
            repositoryOptions.some((option) => option.value === item.repository_id),
          )
          if (candidate?.repository_id) {
            setSelectedRepositoryId(candidate.repository_id)
            window.$app.message.success(`已自动选择代码库：${candidate.repository_name}`)
            return candidate.repository_id
          }
        } catch (error) {
          console.debug(error)
        }
        return undefined
      }
    },
    [chat, id, repositoryOptions, selectedRepositoryId, sessionStore.useDeep, sessionStore.useWeb],
  )

  // 发送消息的主函数，处理用户输入并创建对话项
  const send = useCallback(
    async (message: string, attachments?: string[]) => {
      if (loadingRef.current) return
      if (!message) return

      if (chat.list.length === 0) {
        // 首次发送消息，创建用户消息和AI回复占位
        chat.list.push({
          id: createChatId(),
          role: ChatRole.User,
          type: ChatType.Text,
          content: message,
        })

        chat.list.push({
          id: createChatId(),
          role: ChatRole.Assistant,
          type: ChatType.Document,
          documents: [],
        })

        const target = chat.list[chat.list.length - 1]

        await sendChat(target, message!, attachments)
      } else {
        // 非首次发送，添加新的对话项
        chat.list.push({
          id: createChatId(),
          role: ChatRole.User,
          type: ChatType.Text,
          content: message,
        })

        chat.list.push({
          id: createChatId(),
          role: ChatRole.Assistant,
          type: ChatType.Document,
          content: '',
        })
        scrollToBottom()

        const target = chat.list[chat.list.length - 1]

        await sendChat(target, message!, attachments)
      }
    },
    [chat, sendChat],
  )
  // 组件挂载时，处理页面间传递的消息或加载历史记录
  useMount(async () => {
    repositories.run()
    if (ctx?.data.message) {
      send(ctx.data.message)
    } else {
      history.run()
    }
  })

  return (
    <ComPageLayout
      sender={
        <ComSender
          loading={loading}
          onSend={send}
          repositoryOptions={repositoryOptions}
          selectedRepositoryId={selectedRepositoryId}
          repositoryLoading={repositories.loading}
          repositoryContext={activeRepositoryContext}
          onRepositoryChange={setSelectedRepositoryId}
          onRecommendRepository={async (message) => {
            const { data } = await api.session.getRepositoryCandidates({
              question: message,
              session_id: id,
            })
            const candidate = (data || [])[0]
            if (!candidate?.repository_id) {
              window.$app.message.info('暂未找到匹配的代码库')
              return
            }
            setSelectedRepositoryId(candidate.repository_id)
            window.$app.message.success(`已推荐代码库：${candidate.repository_name}`)
          }}
        />
      }
    >
      <div className={styles['chat-page']}>
        {activeRepositoryContext.length ? (
          <div className={styles['chat-page__repository-context']}>
            当前代码库：
            {activeRepositoryContext.map((item) => item.repository_name).join(' / ')}
          </div>
        ) : null}
        <ChatMessage
          list={list}
          loading={loading}
          deepResearch={sessionStore.useDeep}
          onSend={send}
        />
      </div>
    </ComPageLayout>
  )
}
