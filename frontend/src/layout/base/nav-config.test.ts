import { NAV_ITEMS, getActiveNavKey } from './nav-config'

const codeGenerationNav = NAV_ITEMS.find((item) => item.key === 'code-generation')
const repositoryNav = NAV_ITEMS.find((item) => item.key === 'repository')
const chatNav = NAV_ITEMS.find((item) => item.key === 'chat')

if (!codeGenerationNav || codeGenerationNav.href !== '/code-generation') {
  throw new Error('Code generation nav item must point to /code-generation.')
}

if (!repositoryNav || repositoryNav.href !== '/repository') {
  throw new Error('Repository nav item must point to /repository.')
}

if (!chatNav || chatNav.href !== '/') {
  throw new Error('Chat nav item must point to /.')
}

if (getActiveNavKey('/code-generation') !== 'code-generation') {
  throw new Error('Code generation route must activate the code generation nav item.')
}

if (getActiveNavKey('/repository') !== 'repository') {
  throw new Error('Repository route must activate the repository nav item.')
}

if (getActiveNavKey('/chat/session-id') !== 'chat') {
  throw new Error('Chat route must activate the Q&A nav item.')
}
