import { useTranslation } from 'react-i18next'
import { StatusMessage } from '../../components/StatusMessage'
import { useModel } from '../../hooks/useModel'
type Props = { onSave?: () => void }
export function ModelCard({ onSave }: Props) {
  const { t } = useTranslation()
  const {
    schemaUrls,
    setSchemaUrls,
    contextUrl,
    setContextUrl,
    descriptorUrl,
    setDescriptorUrl,
    exampleUrls,
    setExampleUrls,
    packageContextUrl,
    setPackageContextUrl,
    setModelFile,
    modelStatus,
    loadingUrls,
    loadingPackage,
    onLoadUrls,
    onUploadPackage,
    onClear,
  } = useModel(onSave)
  return (
    <div className="config-card">
      <h2>{t('config.model.title')}</h2>
      <div className="form-grid">
        <label>
          {t('config.model.schemaUrls')} <span className="label-hint">{t('config.model.schemaUrlsHint')}</span>
          <textarea
            rows={3}
            value={schemaUrls}
            onChange={(e) => setSchemaUrls(e.target.value)}
            placeholder="http://localhost:8888/schemas/Building.json"
          />
        </label>
        <label>
          {t('config.model.contextUrl')} <span className="label-hint">{t('config.model.contextUrlHint')}</span>
          <input
            value={contextUrl}
            onChange={(e) => setContextUrl(e.target.value)}
            placeholder="http://localhost:8888/context/context.jsonld"
          />
        </label>
        <label>
          {t('config.model.descriptorUrl')} <span className="label-hint">{t('config.model.optional')}</span>
          <input
            value={descriptorUrl}
            onChange={(e) => setDescriptorUrl(e.target.value)}
            placeholder="http://localhost:8888/context/relationships.json"
          />
        </label>
        <label>
          {t('config.model.exampleUrls')} <span className="label-hint">{t('config.model.exampleUrlsHint')}</span>
          <textarea
            rows={2}
            value={exampleUrls}
            onChange={(e) => setExampleUrls(e.target.value)}
            placeholder="http://localhost:8888/examples/Building/example.json"
          />
        </label>
      </div>
      <div className="actions-row">
        <button onClick={onLoadUrls} disabled={loadingUrls}>
          {loadingUrls ? t('common.loading') : t('config.model.loadFromUrls')}
        </button>
      </div>
      <div className="section-note">{t('config.model.orLoadPackage')}</div>
      <div className="form-grid">
        <label>
          {t('config.model.archiveFile')} <span className="label-hint">{t('config.model.archiveFileHint')}</span>
          <input
            type="file"
            accept=".zip,.tar.gz,.tgz,.tar"
            onChange={(e) => setModelFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          {t('config.model.orionContextUrl')} <span className="label-hint">{t('config.model.optional')}</span>
          <input
            value={packageContextUrl}
            onChange={(e) => setPackageContextUrl(e.target.value)}
            placeholder="http://static/context/context.jsonld"
          />
        </label>
      </div>
      <div className="actions-row">
        <button onClick={onUploadPackage} disabled={loadingPackage}>
          {loadingPackage ? t('common.processing') : t('config.model.loadPackage')}
        </button>
        <button onClick={onClear} className="secondary">
          {t('config.model.clearModel')}
        </button>
      </div>
      {modelStatus ? <StatusMessage message={modelStatus} /> : null}
    </div>
  )
}
