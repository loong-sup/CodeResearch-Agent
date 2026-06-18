import IconNewChat from '@/assets/layout/newchat.svg'
import StoreImage from '@/assets/layout/store.svg'
import { CodeOutlined } from '@ant-design/icons'
import type { ReactNode } from 'react'

export type NavItem = {
  key: 'chat' | 'code-generation' | 'repository'
  label: string
  href: string
  icon: string | ReactNode
  match: (pathname: string) => boolean
}

export const NAV_ITEMS: NavItem[] = [
  {
    key: 'chat',
    label: '代码库问答',
    icon: IconNewChat,
    href: '/',
    match: (pathname) => pathname === '/' || pathname.startsWith('/chat/'),
  },
  {
    key: 'code-generation',
    label: '代码生成',
    icon: <CodeOutlined />,
    href: '/code-generation',
    match: (pathname) => pathname === '/code-generation',
  },
  {
    key: 'repository',
    label: '文档',
    icon: StoreImage,
    href: '/repository',
    match: (pathname) => pathname === '/repository',
  },
]

export function getActiveNavKey(pathname: string) {
  return NAV_ITEMS.find((item) => item.match(pathname))?.key
}
