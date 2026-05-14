import classNames from 'classnames'
import { PropsWithChildren, ReactNode } from 'react'
import style from './index.module.scss'

export default function ComPageLayout(
  props: PropsWithChildren<{
    className?: string
    right?: ReactNode
    sender?: ReactNode
  }>,
) {
  const { children, className, right, sender, ...rest } = props
  return (
    <div className={classNames(style['com-page'], className)} {...rest}>
      <div className={style['com-page__main']}>
        <div className={style['com-page__main-content']}>{children}</div>

        <div className={style['com-page__sender']}>{sender}</div>
      </div>
      {right ? <div className={style['com-page__right']}>{right}</div> : null}
    </div>
  )
}
