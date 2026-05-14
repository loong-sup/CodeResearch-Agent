import axios, { AxiosRequestConfig } from 'axios'
import { errorToastPlugin } from './plugins/error-toast'
import { loadingPlugin } from './plugins/loading'
import { installPlugins } from './plugins/plugin'
import { repeatPlugin } from './plugins/repeat'
import { servicePlugin } from './plugins/service'

export function createRequest(configs: AxiosRequestConfig = {}) {
  const instance = axios.create(configs)

  installPlugins(instance, [
    servicePlugin,
    loadingPlugin,
    repeatPlugin,
    errorToastPlugin,
  ])

  return instance
}
