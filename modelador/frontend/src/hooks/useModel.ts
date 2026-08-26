import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { fetchManyViaProxy, uploadModelPackage } from '../api/model'

type ModelSummary = {
  schemas?: unknown[]
  context?: unknown
  descriptor?: unknown
  examples?: Record<string, unknown>
  summary: {
    schemas: number
    context: boolean
    descriptor: boolean
    examples: number
    unrecognized?: unknown[]
  }
}

function persistModel(model: ModelSummary): void {
  localStorage.setItem('ngsi_model', JSON.stringify(model))
  window.dispatchEvent(new Event('ngsi-model-updated'))
}

export function useModel(onSave?: () => void) {
  const { t } = useTranslation()
  const [schemaUrls, setSchemaUrls] = useState('')
  const [contextUrl, setContextUrl] = useState('')
  const [descriptorUrl, setDescriptorUrl] = useState('')
  const [exampleUrls, setExampleUrls] = useState('')
  const [packageContextUrl, setPackageContextUrl] = useState('')
  const [modelFile, setModelFile] = useState<File | null>(null)
  const [modelStatus, setModelStatus] = useState('')
  const [loadingUrls, setLoadingUrls] = useState(false)
  const [loadingPackage, setLoadingPackage] = useState(false)

  function summaryText(model: ModelSummary): string {
    const parts: string[] = []
    if (model.summary.schemas) parts.push(t('config.model.status.summarySchemas', { count: model.summary.schemas }))
    if (model.summary.context) parts.push(t('config.model.status.summaryContext'))
    if (model.summary.descriptor) parts.push(t('config.model.status.summaryDescriptor'))
    if (model.summary.examples) parts.push(t('config.model.status.summaryExamples', { count: model.summary.examples }))
    return t('config.model.status.loaded', { details: parts.join(', ') })
  }

  async function onLoadUrls() {
    const schemas = schemaUrls.split('\n').map((s) => s.trim()).filter(Boolean)
    const context = contextUrl.trim()
    const descriptor = descriptorUrl.trim()
    const examples = exampleUrls.split('\n').map((s) => s.trim()).filter(Boolean)
    if (!schemas.length && !context) {
      setModelStatus(t('config.model.status.needUrl'))
      return
    }
    setLoadingUrls(true)
    setModelStatus(t('config.model.status.loading'))
    try {
      const [schemaResults, contextResult, descriptorResult, exampleResults] = await Promise.all([
        schemas.length ? fetchManyViaProxy(schemas) : Promise.resolve([]),
        context ? fetchManyViaProxy([context]).then((r) => r[0]) : Promise.resolve(null),
        descriptor ? fetchManyViaProxy([descriptor]).then((r) => r[0]) : Promise.resolve(null),
        examples.length ? fetchManyViaProxy(examples) : Promise.resolve([]),
      ])
      const examplesMap: Record<string, unknown> = {}
      examples.forEach((url, i) => {
        const name = url.split('/').slice(-2).join('/')
        examplesMap[name] = exampleResults[i]
      })
      const model: ModelSummary = {
        schemas: schemaResults,
        context: contextResult,
        descriptor: descriptorResult,
        examples: examplesMap,
        summary: {
          schemas: schemaResults.length,
          context: !!contextResult,
          descriptor: !!descriptorResult,
          examples: Object.keys(examplesMap).length,
        },
      }
      persistModel(model)
      setModelStatus(summaryText(model))
      onSave?.()
    } catch (e) {
      setModelStatus(e instanceof Error ? e.message : t('config.model.status.loadError'))
    } finally {
      setLoadingUrls(false)
    }
  }

  async function onUploadPackage() {
    if (!modelFile) {
      setModelStatus(t('config.model.status.selectFile'))
      return
    }
    setLoadingPackage(true)
    setModelStatus(t('config.model.status.processing'))
    try {
      const model = await uploadModelPackage(modelFile)
      if (packageContextUrl.trim()) {
        model.context = packageContextUrl.trim()
      }
      persistModel(model)
      setModelStatus(summaryText(model))
      onSave?.()
    } catch (e) {
      setModelStatus(e instanceof Error ? e.message : t('config.model.status.processError'))
    } finally {
      setLoadingPackage(false)
    }
  }

  function onClear() {
    localStorage.removeItem('ngsi_model')
    window.dispatchEvent(new Event('ngsi-model-updated'))
    setSchemaUrls('')
    setContextUrl('')
    setDescriptorUrl('')
    setExampleUrls('')
    setPackageContextUrl('')
    setModelFile(null)
    setModelStatus(t('config.model.status.cleared'))
    onSave?.()
  }

  return {
    schemaUrls, setSchemaUrls,
    contextUrl, setContextUrl,
    descriptorUrl, setDescriptorUrl,
    exampleUrls, setExampleUrls,
    packageContextUrl, setPackageContextUrl,
    modelFile, setModelFile,
    modelStatus,
    loadingUrls,
    loadingPackage,
    onLoadUrls,
    onUploadPackage,
    onClear,
  }
}
