import { useState } from 'react'
import { fetchManyViaProxy, fetchViaProxy, uploadModelPackage } from '../api/model'
import type { NgsiModel } from '../types/model'

const MODEL_KEY = 'ngsi_model'

function readStoredModel(): Partial<NgsiModel> | null {
  try {
    const raw = localStorage.getItem(MODEL_KEY)
    return raw ? (JSON.parse(raw) as Partial<NgsiModel>) : null
  } catch {
    return null
  }
}

function exampleKeyFromUrl(url: string, parsed: unknown): string | null {
  if (parsed && typeof parsed === 'object' && 'type' in parsed) {
    const t = (parsed as { type?: unknown }).type
    if (typeof t === 'string') {
      const last = t.split('/').pop()
      if (last && /^[A-Z]/.test(last)) return last
    }
  }
  try {
    const parts = new URL(url).pathname.split('/').filter(Boolean)
    if (parts.length >= 2) {
      const parent = parts[parts.length - 2]
      if (/^[A-Z]/.test(parent)) return parent
    }
    return parts[parts.length - 1].replace(/\.json$/i, '')
  } catch {
    return null
  }
}

export function useModel(onSave?: () => void) {
  const stored = readStoredModel()
  const [schemaUrls, setSchemaUrls] = useState(stored?.schemaUrls?.join('\n') ?? '')
  const [contextUrl, setContextUrl] = useState(stored?.contextUrl ?? '')
  const [descriptorUrl, setDescriptorUrl] = useState(stored?.descriptorUrl ?? '')
  const [exampleUrls, setExampleUrls] = useState(stored?.exampleUrls?.join('\n') ?? '')
  const [packageContextUrl, setPackageContextUrl] = useState('')
  const [modelFile, setModelFile] = useState<File | null>(null)
  const [modelStatus, setModelStatus] = useState<string | null>(null)
  const [loadingUrls, setLoadingUrls] = useState(false)
  const [loadingPackage, setLoadingPackage] = useState(false)

  async function onLoadUrls() {
    const urls = schemaUrls.trim().split(/\n+/).filter(Boolean)
    const ctx = contextUrl.trim()
    const desc = descriptorUrl.trim()
    const exUrls = exampleUrls.trim().split(/\n+/).filter(Boolean)
    if (!urls.length && !ctx && !desc && !exUrls.length) {
      setModelStatus('Indica al menos una URL (schema, contexto, descriptor o ejemplos).')
      return
    }
    setLoadingUrls(true)
    setModelStatus('Cargando...')
    try {
      const loaded: NgsiModel = {
        schemas: [],
        context: null,
        descriptor: null,
        examples: {},
        schemaUrls: urls,
        contextUrl: ctx || null,
        descriptorUrl: desc || null,
        exampleUrls: exUrls,
      }
      if (urls.length) loaded.schemas = await fetchManyViaProxy(urls)
      if (ctx) loaded.context = await fetchViaProxy(ctx)
      if (desc) loaded.descriptor = await fetchViaProxy(desc)
      for (const exUrl of exUrls) {
        try {
          const exJson = await fetchViaProxy(exUrl)
          const key = exampleKeyFromUrl(exUrl, exJson)
          if (key && !(key in loaded.examples)) loaded.examples[key] = exJson
        } catch {
          // ignora ejemplos individuales inválidos, mismo comportamiento que legacy
        }
      }
      localStorage.setItem(MODEL_KEY, JSON.stringify(loaded))
      setModelStatus(
        `Modelo cargado — ${loaded.schemas.length} schemas, contexto: ${loaded.context ? 'sí' : 'no'}, descriptor: ${loaded.descriptor ? 'sí' : 'no'}, ${Object.keys(loaded.examples).length} ejemplos`,
      )
      onSave?.()
    } catch (e) {
      setModelStatus(e instanceof Error ? e.message : 'Error al cargar modelo.')
    } finally {
      setLoadingUrls(false)
    }
  }

  async function onUploadPackage() {
    if (!modelFile) {
      setModelStatus('Selecciona un archivo comprimido primero.')
      return
    }
    setLoadingPackage(true)
    setModelStatus(`Procesando ${modelFile.name}...`)
    try {
      const result = await uploadModelPackage(modelFile)
      const loaded: NgsiModel = {
        schemas: result.schemas ?? [],
        context: result.context ?? null,
        descriptor: result.descriptor ?? null,
        examples: result.examples ?? {},
        schemaUrls: [],
        contextUrl: packageContextUrl.trim() || null,
        descriptorUrl: null,
        exampleUrls: [],
        packageName: modelFile.name,
      }
      localStorage.setItem(MODEL_KEY, JSON.stringify(loaded))
      onSave?.()
      const s = result.summary
      setModelStatus(
        `Paquete cargado — ${s.schemas} schemas, contexto: ${s.context ? 'sí' : 'no'}, descriptor: ${s.descriptor ? 'sí' : 'no'}, ${s.examples} ejemplos`,
      )
    } catch (e) {
      setModelStatus(e instanceof Error ? e.message : 'Error al procesar el paquete.')
    } finally {
      setLoadingPackage(false)
    }
  }

  function onClear() {
    localStorage.removeItem(MODEL_KEY)
    setSchemaUrls('')
    setContextUrl('')
    setDescriptorUrl('')
    setExampleUrls('')
    setPackageContextUrl('')
    setModelFile(null)
    setModelStatus('Modelo eliminado correctamente.')
  }

  return {
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
    modelFile,
    setModelFile,
    modelStatus,
    loadingUrls,
    loadingPackage,
    onLoadUrls,
    onUploadPackage,
    onClear,
  }
}
