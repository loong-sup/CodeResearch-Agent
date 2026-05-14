import HomeBanner from '@/components/home-banner'
import HotQuestions from '@/components/hot-questions'
import ComSender from '@/components/sender'
import useSendMessage from '@/utils/useSendMessage'
import styles from './index.module.scss'

export default function Index() {
  const send = useSendMessage()

  return (
    <div className={styles.container}>
      <HomeBanner />
      <ComSender className={styles.sender} onSend={send} />
      <HotQuestions />
    </div>
  )
}
