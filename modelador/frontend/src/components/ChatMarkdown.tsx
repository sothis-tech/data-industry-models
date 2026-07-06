import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Props = {
  /** Contenido Markdown (GFM) proveniente del LLM */
  content: string
  className?: string
}

/**
 * Renderiza respuestas del asistente con Markdown seguro (sin HTML crudo).
 */
export function ChatMarkdown({ content, className = 'chat-md' }: Props) {
  const trimmed = content.trim()
  if (!trimmed) return null
  return (
    <div className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{trimmed}</ReactMarkdown>
    </div>
  )
}
