declare namespace API {
  type Repository = {
    created_at: string
    file_name: string
    updated_at: string
    user_id: string
    repository_id?: string
    repository_type?: string
    status?: string
    indexed_chunks?: number
  }
}
