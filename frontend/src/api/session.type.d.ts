declare namespace API {
  interface RepositoryContext {
    repository_id: string
    repository_name: string
    repository_type?: string
    status?: string
  }

  interface RepositoryCandidate {
    repository_id: string
    repository_name: string
    repository_type: string
    score: number
    reason: string
  }

  interface Session {
    created_at: string
    session_id: string
    session_name: string
    updated_at: string
    // user_id: string
  }

  interface ChatItem {
    id: number
    role: import('@/configs').ChatRole
    type: import('@/configs').ChatType
    loading?: boolean
    error?: string
    content?: string
    think?: string

    documents?: Document[]
    reference?: Document[]
    citations?: Citation[]
    repository_context?: RepositoryContext[]
    web_search?: WebSearchResult[]
    web_search_status?: WebSearchStatus
    recommended_questions?: string[]
    image_results?: {
      images?: {
        title: string
        imageUrl: string
        thumbnailUrl: string
        source: string
        link: string
        googleUrl: string
      }[]
    }
    video_results?: {
      videos?: {
        title: string
        link: string
        imageUrl: string
      }[]
    }
  }

  interface Document {
    id?: number
    chunk_id?: string
    document_id: string
    document_name: string
    content_with_weight: string
    repository_id?: string
    repository_name?: string
    repository_type?: string
    file_path?: string
    start_line?: number
    end_line?: number
    language?: string
    symbol?: string
    chunk_kind?: string
    citation?: string
    citation_display?: string
    citation_key?: string
  }

  interface Citation {
    id?: number
    chunk_id?: string
    citation: string
    citation_display: string
    file_path?: string
    start_line?: number
    end_line?: number
    symbol?: string
    language?: string
    chunk_kind?: string
    repository_id?: string
    preview?: string
  }

  interface WebSearchResult {
    title: string
    url: string
    content: string
    query?: string
  }

  interface WebSearchStatus {
    enabled?: boolean
    queries?: string[]
    result_count?: number
    error?: string
  }
}
