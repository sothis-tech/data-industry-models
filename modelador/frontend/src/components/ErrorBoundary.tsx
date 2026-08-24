import { Component, type ErrorInfo, type ReactNode } from 'react'
import i18n from '../lib/i18n'
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
          <h2>{i18n.t('errorBoundary.title')}</h2>
          <p>{i18n.t('errorBoundary.message')}</p>
          <pre className="error-boundary__detail">
            {this.state.error.message}
          </pre>
          <div className="error-boundary__actions">
            <button
              type="button"
              onClick={() => this.setState({ error: null })}
            >
              {i18n.t('errorBoundary.retry')}
            </button>
            <button
              type="button"
              className="secondary"
              onClick={() => { window.location.href = '/' }}
            >
              {i18n.t('errorBoundary.backToConfig')}
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
