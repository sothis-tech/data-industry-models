type Variant = 'info' | 'success' | 'error'

const variantClass: Record<Variant, string> = {
  info: 'status-msg status-msg--info',
  success: 'status-msg status-msg--success',
  error: 'status-msg status-msg--error',
}

type Props = {
  message: string
  variant?: Variant
}

export function StatusMessage({ message, variant = 'info' }: Props) {
  return <p className={variantClass[variant]}>{message}</p>
}
