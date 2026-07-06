export interface RagConfig {
  enabled: boolean
  max_mb: number
  allowed_extensions: string[]
  chroma_db: string
}

export type UploadStatus = 'idle' | 'uploading' | 'success' | 'error'

export interface RagUploadResult {
  ok: boolean
  status: number
  filename: string
  tenant?: string
  collection?: string
  error?: string
  detail?: unknown
}

export interface DocInfo {
  chunks: number
  pages: number
}

export interface RagDocuments {
  tenant: string
  total_chunks: number
  indexed: Record<string, DocInfo>
  disk_files: string[]
  not_indexed: string[]
}
