import IconNewChat from '@/assets/layout/newchat.svg'
import StoreImage from '@/assets/layout/store.svg'
import { Avatar } from 'antd'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import './nav.scss'

export function Nav() {
  const list = useMemo(
    () => [
      {
        key: '1',
        label: '新对话',
        icon: IconNewChat,
        href: '/',
      },
      {
        key: '2',
        label: '文档',
        icon: StoreImage,
        href: '/repository',
      },
    ],
    [],
  )

  return (
    <div className="base-layout-nav">
      {list.map((item) => (
        <Link
          className="base-layout-nav__item"
          key={item.key}
          title={item.label}
          to={item.href ?? '#'}
        >
          <img src={item.icon} alt={item.label} />
        </Link>
      ))}

      <Avatar>W</Avatar>
    </div>
  )
}
