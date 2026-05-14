import IconAnswer from '@/assets/chat/answer.svg'
import IconCopy from '@/assets/chat/copy.svg'
import IconImage from '@/assets/chat/image.svg'
import IconLike from '@/assets/chat/like.svg'
import IconPlay from '@/assets/chat/play.svg'
import IconRefresh from '@/assets/chat/refresh.svg'
import IconRelated from '@/assets/chat/related.svg'
import IconRemove from '@/assets/chat/remove.svg'
import IconShare from '@/assets/chat/share.svg'
import IconSource from '@/assets/chat/source.svg'
import IconVideo from '@/assets/chat/video.svg'
import Markdown from '@/components/markdown'
import { PlusOutlined } from '@ant-design/icons'
import { Button, Dropdown } from 'antd'
import classNames from 'classnames'
import { TokenizerAndRendererExtension } from 'marked'
import { MouseEvent, useMemo } from 'react'
import styles from './result.module.scss'

const Section = (props: {
  title: string
  icon: string
  children: React.ReactNode
}) => {
  return (
    <div className={styles['chat-message-result-section']}>
      <div className={styles['chat-message-result-section__title']}>
        <img className={styles.icon} src={props.icon} />
        <span className={styles.title}>{props.title}</span>
      </div>
      {props.children}
    </div>
  )
}

const 答案 = (props: { item: API.ChatItem }) => {
  const { item } = props

  /* markdown */
  const extensions = useMemo<TokenizerAndRendererExtension[]>(
    () => [
      {
        name: 'reference',
        level: 'inline',
        start(src) {
          return src.match(/##\d+\$\$/)?.index
        },
        tokenizer(src) {
          const match = /^##(\d+?)\$\$/.exec(src)
          if (match) {
            const [raw, index] = match
            return {
              type: 'reference',
              raw,
              index: this.lexer.inlineTokens(index),
              tokens: [],
            }
          }
        },
        renderer(token) {
          const index = this.parser.parseInline(token.index)
          return `<span class="refrence-token" data-refrence-index="${index}">[${Number(index) + 1}]</span>`
        },
      },
      {
        name: 'codeCitation',
        level: 'inline',
        start(src) {
          return src.match(/\[[^\[\]]+:\d+-\d+\]/)?.index
        },
        tokenizer(src) {
          const match = /^\[([^\[\]]+:\d+-\d+)\]/.exec(src)
          if (match) {
            const [raw, citation] = match
            return {
              type: 'codeCitation',
              raw,
              citation,
              citationKey: encodeURIComponent(citation),
              tokens: [],
            }
          }
        },
        renderer(token) {
          return `<span class="citation-token" data-citation="${token.citation}" data-citation-key="${token.citationKey}">${token.raw}</span>`
        },
      },
    ],
    [],
  )

  const handleCitationClick = async (event: MouseEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement
    const citationNode = target.closest('[data-citation-key]') as HTMLElement | null
    if (!citationNode) return

    const citation = citationNode.dataset.citation
    const citationKey = citationNode.dataset.citationKey
    if (!citationKey) return

    const sourceNode = document.querySelector(
      `[data-citation-source="${citationKey}"]`,
    ) as HTMLElement | null

    if (sourceNode) {
      sourceNode.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }

    if (citation && navigator.clipboard) {
      try {
        await navigator.clipboard.writeText(citation)
        window.$app?.message?.success?.('引用已复制')
      } catch (error) {
        console.debug(error)
      }
    }
  }

  return (
    <Section title="答案" icon={IconAnswer}>
      {item.think ? (
        <Markdown
          className={classNames(
            styles['chat-message-result__think'],
            styles['chat-message-result__md'],
          )}
          value={item.think}
          extensions={extensions}
          onClick={handleCitationClick}
        />
      ) : null}

      {item.content ? (
        <Markdown
          className={styles['chat-message-result__md']}
          value={item.content}
          extensions={extensions}
          onClick={handleCitationClick}
        />
      ) : null}

      {item.error ? (
        <div className={styles['chat-message-result__error']}>{item.error}</div>
      ) : null}
    </Section>
  )
}

const 来源 = (props: { item: API.ChatItem }) => {
  const { item } = props

  if (!item.citations?.length) return null
  return (
    <Section title="引用来源" icon={IconSource}>
      <div className={styles['chat-message-result__source']}>
        {item.citations.map((item) => (
          <div
            key={item.citation}
            className={styles.item}
            data-citation-source={encodeURIComponent(item.citation)}
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(item.citation)
                window.$app?.message?.success?.('引用已复制')
              } catch (error) {
                console.debug(error)
              }
            }}
          >
            <div className={styles.header}>
              <div className={styles.url}>{item.citation_display}</div>
            </div>
            {item.symbol ? (
              <div className={styles.title}>
                {item.symbol}
                {item.chunk_kind ? ` · ${item.chunk_kind}` : ''}
              </div>
            ) : item.file_path ? (
              <div className={styles.title}>{item.file_path}</div>
            ) : null}
            <div className={styles.content}>{item.preview}</div>
          </div>
        ))}
      </div>
    </Section>
  )
}

const 代码库上下文 = (props: { item: API.ChatItem }) => {
  const { item } = props

  if (!item.repository_context?.length) return null

  return (
    <Section title="当前代码库" icon={IconSource}>
      <div className={styles['chat-message-result__source']}>
        {item.repository_context.map((context) => (
          <div key={context.repository_id} className={styles.item}>
            <div className={styles.header}>
              <div className={styles.url}>{context.repository_name}</div>
            </div>
            <div className={styles.content}>
              {[context.repository_type, context.status].filter(Boolean).join(' · ')}
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

const 笔记 = (props: { item: API.ChatItem }) => {
  const { item } = props
  console.log(item)

  // 后端暂未实现，使用假数据代替
  return (
    <Section title="笔记" icon={IconImage}>
      <div className={styles['chat-message-result__xhs']}>
        {Array.from({ length: 4 }).map((_) => (
          <div className={styles.item}>
            <div className={styles.header}>
              <img className={styles.cover} src={IconShare} />
            </div>

            <div className={styles.footer}>
              <div className={styles.title}>
                如何培养孩子的兴趣？家长学会这三点，孩子受益匪浅 - Classover
              </div>

              <div className={styles.user}>
                <img className={styles.avatar} src={IconShare} />
                <div className={styles.name}>Classover</div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

const 图像 = (props: { item: API.ChatItem }) => {
  const { item } = props

  return (
    <Section title="图像" icon={IconImage}>
      <div className={styles['chat-message-result__images']}>
        {item.image_results?.images?.map((item, index) => (
          <div
            className={styles.item}
            key={index}
            onClick={() => window.open(item.link, '_blank')}
          >
            <div className={styles.box}>
              <img className={styles.cover} src={item.thumbnailUrl} />
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

const 视频 = (props: { item: API.ChatItem }) => {
  const { item } = props

  return (
    <Section title="视频" icon={IconVideo}>
      <div className={styles['chat-message-result__videos']}>
        {item.video_results?.videos?.map((item, index) => (
          <div
            className={styles.item}
            key={index}
            onClick={() => window.open(item.link, '_blank')}
          >
            <div className={styles.box}>
              <img className={styles.cover} src={item.imageUrl} />

              <img className={styles.play} src={IconPlay} />
            </div>
          </div>
        ))}
      </div>
    </Section>
  )
}

const 相关 = (props: {
  item: API.ChatItem
  onSend?: (text: string) => void
}) => {
  const { item, onSend } = props

  if (
    !item.recommended_questions?.length ||
    item.recommended_questions.filter((q) => q).length === 0
  )
    return null

  return (
    <Section title="继续追问" icon={IconRelated}>
      <div className={styles['chat-message-result__quick-reply']}>
        {item.recommended_questions?.map((item, index) => (
          <div
            className={styles['item']}
            key={index}
            onClick={() => onSend?.(item)}
          >
            <span className={styles['text']}>
              {index + 1}．{item}
            </span>
            <PlusOutlined className={styles['arrow']} />
          </div>
        ))}
      </div>
    </Section>
  )
}

export function Result(props: {
  item: API.ChatItem
  isEnd?: boolean
  onSend?: (text: string) => void
}) {
  const { item, isEnd, onSend } = props

  const shareMenu = useMemo(() => {
    return [
      {
        key: 'pdf',
        label: 'Export as txt',
        onClick: async () => {
          const url = `data:text/plain;charset=utf-8,${encodeURIComponent(item.content ?? '')}`
          const a = document.createElement('a')
          a.href = url
          a.download = 'output.txt'
          a.click()
        },
      },
      {
        key: 'email',
        label: 'Send report via email',
      },
    ]
  }, [item.content])

  return (
    <div className={styles['chat-message-result']}>
      {item.think || item.content || item.error ? <答案 item={item} /> : null}

      {item.loading ? null : (
        <div className={styles['chat-message-result__actions']}>
          <Button variant="filled" color="default" shape="circle">
            <img src={IconCopy} />
          </Button>

          <Button variant="filled" color="default" shape="circle">
            <img src={IconRefresh} />
          </Button>

          <Button variant="filled" color="default" shape="circle">
            <img src={IconLike} />
          </Button>

          <Button variant="filled" color="default" shape="circle">
            <img src={IconRemove} />
          </Button>

          <Dropdown menu={{ items: shareMenu }}>
            <Button variant="filled" color="default" shape="circle">
              <img src={IconShare} />
            </Button>
          </Dropdown>
        </div>
      )}

      {item.repository_context?.length ? <代码库上下文 item={item} /> : null}

      {item.citations?.length ? <来源 item={item} /> : null}

      {false ? <笔记 item={item} /> : null}

      {item.image_results?.images?.length ? <图像 item={item} /> : null}

      {item.video_results?.videos?.length ? <视频 item={item} /> : null}

      {!item.loading && isEnd && item.recommended_questions?.length ? (
        <相关 item={item} onSend={onSend} />
      ) : null}
    </div>
  )
}
