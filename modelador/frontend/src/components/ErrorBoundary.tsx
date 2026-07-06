import { Component, type ErrorInfo, type ReactNode } from 'react'

type Props = { children: ReactNode }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ModeladorErrorBoundary]', error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="error-boundary">
          <h2>Algo ha ido mal</h2>
          <p>Se ha producido un error inesperado en la aplicación.</p>
          <pre className="error-boundary__detail">
            {this.state.error.message}
          </pre>
          <div className="error-boundary__actions">
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
            >
              Intentar de nuevo
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => { window.location.href = '/' }}
            >
              Volver a Configuración
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
