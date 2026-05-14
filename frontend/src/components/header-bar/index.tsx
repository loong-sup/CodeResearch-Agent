import logo from '../../assets/logo_with_en_name.png'
import styles from './index.module.scss'

export default function HeaderBar(props: { className?: string }) {
  return (
    <header className={`${styles['header-bar']} ${props.className || ''}`}>
      <img src={logo} alt="Logo" className={styles.logo} />{' '}
      {/* 使用 logo 样式 */}
      <span>{import.meta.env.VITE_TITLE}</span> {/* 添加文字 */}
    </header>
  )
}
