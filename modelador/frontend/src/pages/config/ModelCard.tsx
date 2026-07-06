import { StatusMessage } from '../../components/StatusMessage'
import { useModel } from '../../hooks/useModel'

type Props = { onSave?: () => void }

export function ModelCard({ onSave }: Props) {
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
      <h2>Modelo NGSI-LD</h2>

      <div className="form-grid">
        <label>
          URLs de JSON Schemas <span className="label-hint">(una por línea)</span>
          <textarea
            rows={3}
            value={schemaUrls}
            onChange={(e) => setSchemaUrls(e.target.value)}
            placeholder="http://localhost:8888/schemas/Building.json"
          />
        </label>
        <label>
          URL del contexto JSON-LD <span className="label-hint">(@context)</span>
          <input
            value={contextUrl}
            onChange={(e) => setContextUrl(e.target.value)}
            placeholder="http://localhost:8888/context/context.jsonld"
          />
        </label>
        <label>
          URL del descriptor <span className="label-hint">(opcional)</span>
          <input
            value={descriptorUrl}
            onChange={(e) => setDescriptorUrl(e.target.value)}
            placeholder="http://localhost:8888/context/relationships.json"
          />
        </label>
        <label>
          URLs de ejemplos <span className="label-hint">(opcional, una por línea)</span>
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
          {loadingUrls ? 'Cargando…' : 'Cargar desde URLs'}
        </button>
      </div>

      <div className="section-note">— o carga un paquete —</div>

      <div className="form-grid">
        <label>
          Archivo comprimido <span className="label-hint">(.zip, .tar.gz, .tar)</span>
          <input
            type="file"
            accept=".zip,.tar.gz,.tgz,.tar"
            onChange={(e) => setModelFile(e.target.files?.[0] ?? null)}
          />
        </label>
        <label>
          URL del contexto para Orion <span className="label-hint">(opcional)</span>
          <input
            value={packageContextUrl}
            onChange={(e) => setPackageContextUrl(e.target.value)}
            placeholder="http://static/context/context.jsonld"
          />
        </label>
      </div>

      <div className="actions-row">
        <button onClick={onUploadPackage} disabled={loadingPackage}>
          {loadingPackage ? 'Procesando…' : 'Cargar paquete'}
        </button>
        <button onClick={onClear} className="secondary">
          Limpiar modelo
        </button>
      </div>

      {modelStatus ? <StatusMessage message={modelStatus} /> : null}
    </div>
  )
}
