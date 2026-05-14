import { AxiosRequestConfig } from 'axios'
import { request } from './request'

export function list(params?: {}, options?: AxiosRequestConfig) {
  return request.get<{
    sessions: API.Session[]
  }>(`/get_sessions/`, {
    ...options,
    params,
  })
}

export function detail(
  params: {
    session_id: string
  },
  options?: AxiosRequestConfig,
) {
  return request.get<
    {
      created_at: string
      message_id: string
      session_id: string
      user_question: string
      model_answer: string
      think?: string
      documents?: string
      recommended_questions?: string[]
    }[]
  >(`/get_messages/`, {
    ...options,
    params,
  })
}

export function create(params?: {}, options?: AxiosRequestConfig) {
  return request.post<
    API.Result<{
      session_id: string
    }>
  >(`/create_session`, params, options)
}

export function chat(
  params: {
    id: string
    message: string
    web_search?: boolean
    deep_research?: boolean
    attachments?: string[]
    repository_id?: string
    repository_ids?: string[]
  },
  options?: AxiosRequestConfig,
) {
  const { id, deep_research, ..._params } = params
  if (deep_research) {
    return request.post<ReadableStream>(
      '/deep_research/',
      {
        ..._params,
      },
      {
        headers: {
          Accept: 'text/event-stream',
        },
        responseType: 'stream',
        adapter: 'fetch',
        loading: false,
        params: {
          session_id: id,
        },
      },
    )
  }
  return request.post<ReadableStream>(
    '/ai_search/',
    {
      ..._params,
    },
    {
      headers: {
        Accept: 'text/event-stream',
      },
      responseType: 'stream',
      adapter: 'fetch',
      loading: false,
      params: {
        session_id: id,
      },
      ...options,
    },
  )
}

export function upload(params: { files: File }, options?: AxiosRequestConfig) {
  const form = new FormData()
  form.append('files', params.files)
  return request.post<API.Result<{ file_id: string; url: string }>>(
    `/upload_files/`,
    form,
    {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      ...options,
    },
  )
}

export function uploadProjectArchive(
  params: { archive: File; session_id?: string },
  options?: AxiosRequestConfig,
) {
  const form = new FormData()
  form.append('archive', params.archive)
  return request.post<
    API.Result<{
      repo_name: string
      repo_root: string
      indexed_chunks: number
      archive_path: string
    }>
  >(`/upload_project_archive/`, form, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
    params: {
      session_id: params.session_id,
    },
    ...options,
  })
}

export function getRepositoryCandidates(
  params: {
    question: string
    session_id?: string
  },
  options?: AxiosRequestConfig,
) {
  return request.get<API.RepositoryCandidate[]>(`/get_repository_candidates/`, {
    ...options,
    params,
  })
}
