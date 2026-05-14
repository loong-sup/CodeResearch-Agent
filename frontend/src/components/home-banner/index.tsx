import decImg from '../../assets/home_banner_dec.png'
import portraitImg from '../../assets/home_banner_portrait.png'
import styles from './index.module.scss'

export default function HomeBanner() {
  return (
    <div className={styles.banner}>
      <div className={styles.content}>
        <h1 className={styles.title}>代码库问答助手</h1>
        <p className={styles.subtitle}>
          基于仓库索引回答实现位置、调用关系、配置来源与模块职责。
        </p>
      </div>
      <div className={styles.decoration}>
        <img src={portraitImg} alt="代码助手" className={styles.portrait} />
        <img src={decImg} alt="装饰背景" className={styles.decImage} />
      </div>
    </div>
  )
}
