import * as api from '@/api'
import ComSender from '@/components/sender'
import { sessionActions, sessionState } from '@/store/session'
import useSendMessage from '@/utils/useSendMessage'
import { useMount, useRequest } from 'ahooks'
import { useCallback, useEffect, useMemo, useState } from 'react'
import styles from './index.module.scss'

export default function CodeGeneration() {
  const sendMessage = useSendMessage()
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<string>()
  const [activeRepositoryContext, setActiveRepositoryContext] = useState<
    API.RepositoryContext[]
  >([])

  const repositories = useRequest(
    async () => {
      const { data } = await api.repository.list(undefined, {
        loading: false,
      })
      return data || []
    },
    {
      manual: true,
    },
  )

  const repositoryOptions = useMemo(() => {
    return (repositories.data || [])
      .filter((item) => item.repository_id && item.status !== 'error')
      .map((item) => ({
        label: item.file_name,
        value: item.repository_id!,
        description: [
          item.repository_type,
          item.indexed_chunks ? `${item.indexed_chunks} chunks` : '',
        ]
          .filter(Boolean)
          .join(' · '),
      }))
  }, [repositories.data])

  const updateActiveRepositoryContext = useCallback(
    (repositoryId?: string) => {
      if (!repositoryId) {
        setActiveRepositoryContext([])
        return
      }

      const repository = (repositories.data || []).find(
        (item) => item.repository_id === repositoryId,
      )
      if (!repository) return

      setActiveRepositoryContext([
        {
          repository_id: repository.repository_id!,
          repository_name: repository.file_name,
          repository_type: repository.repository_type,
          status: repository.status,
        },
      ])
    },
    [repositories.data],
  )

  const handleRepositoryChange = useCallback(
    (repositoryId?: string) => {
      setSelectedRepositoryId(repositoryId)
      updateActiveRepositoryContext(repositoryId)
    },
    [updateActiveRepositoryContext],
  )

  const refreshRepositories = useCallback(async () => {
    await repositories.runAsync()
  }, [repositories])

  useMount(async () => {
    sessionActions.setUseCodeGeneration(true)
    sessionActions.setCodeGenerationLanguage('Python')
    await repositories.runAsync()
  })

  useEffect(() => {
    if (!selectedRepositoryId) return
    updateActiveRepositoryContext(selectedRepositoryId)
  }, [selectedRepositoryId, updateActiveRepositoryContext])

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1 className={styles.title}>代码生成</h1>
        <p className={styles.subtitle}>
          生成新功能、测试、脚手架或实现片段，可选择代码库上下文让结果贴合项目结构。
        </p>
      </div>

      <ComSender
        className={styles.sender}
        placeholder="例如：为当前项目生成一个用户登录接口、补充单元测试、创建 TypeScript API 客户端。按 Enter 发送，Shift + Enter 换行"
        onSend={(message) =>
          sendMessage(message, {
            mode: 'code-generation',
            language: sessionState.codeGenerationLanguage,
            repository_id: selectedRepositoryId,
          })
        }
        repositoryOptions={repositoryOptions}
        selectedRepositoryId={selectedRepositoryId}
        repositoryLoading={repositories.loading}
        repositoryContext={activeRepositoryContext}
        onRepositoryChange={handleRepositoryChange}
        onRepositoryRefresh={refreshRepositories}
        onRecommendRepository={async (message) => {
          const { data } = await api.session.getRepositoryCandidates({
            question: message,
          })
          const candidate = (data || [])[0]
          if (!candidate?.repository_id) {
            window.$app.message.info('暂未找到匹配的代码库')
            return
          }
          handleRepositoryChange(candidate.repository_id)
          window.$app.message.success(`已推荐代码库：${candidate.repository_name}`)
        }}
      />
    </div>
  )
}
