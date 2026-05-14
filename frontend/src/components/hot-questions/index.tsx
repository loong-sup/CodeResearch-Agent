import useSendMessage from '@/utils/useSendMessage'
import { debounce } from 'throttle-debounce'
import styles from './index.module.scss'

interface HotQuestion {
  emoji: string
  title: string
}

interface HotQuestionsProps {
  list?: HotQuestion[]
}

const list: HotQuestion[] = [
  {
    emoji: '📍',
    title: '这个功能在哪里实现？',
  },
  {
    emoji: '🧭',
    title: '某个接口的请求入口和处理流程是什么？',
  },
  {
    emoji: '🔗',
    title: 'AuthService 在哪里定义，又在哪里被调用？',
  },
  {
    emoji: '⚙️',
    title: '这个配置项是从哪里读取并生效的？',
  },
  {
    emoji: '🐞',
    title: '这个错误信息是从哪段代码抛出来的？',
  },
]

export default function HotQuestions(props: HotQuestionsProps) {
  const sendMessage = useSendMessage()
  const questions = props.list?.length ? props.list : list
  // 使用防抖处理点击事件，300ms内只触发一次
  const handleClick = debounce(300, (question: HotQuestion) => {
    sendMessage(question.title)
  })

  return (
    <div className={styles.hotQuestions}>
      {questions.map((question) => (
        <div
          key={question.title}
          className={styles.hotQuestion}
          onClick={() => handleClick(question)}
        >
          <span className={styles.emoji}>{question.emoji}</span>
          <span className={styles.title}>{question.title}</span>
        </div>
      ))}
    </div>
  )
}
