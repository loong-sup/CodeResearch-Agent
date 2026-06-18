import { Avatar } from 'antd'
import classNames from 'classnames'
import { Link, useLocation } from 'react-router-dom'
import { NAV_ITEMS, getActiveNavKey } from './nav-config'
import './nav.scss'

export function Nav() {
  const location = useLocation()
  const activeKey = getActiveNavKey(location.pathname)

  return (
    <div className="base-layout-nav">
      {NAV_ITEMS.map((item) => (
        <Link
          className={classNames('base-layout-nav__item', {
            'base-layout-nav__item--active': item.key === activeKey,
          })}
          key={item.key}
          title={item.label}
          to={item.href ?? '#'}
        >
          {typeof item.icon === 'string' ? (
            <img src={item.icon} alt={item.label} />
          ) : (
            <span className="base-layout-nav__icon" aria-hidden="true">
              {item.icon}
            </span>
          )}
        </Link>
      ))}

      <Avatar>W</Avatar>
    </div>
  )
}
