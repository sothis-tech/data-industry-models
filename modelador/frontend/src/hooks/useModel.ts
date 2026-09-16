import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { clearTenantModel, saveTenantModel } from '../api/contextServer'
import { fetchManyViaProxy, fetchViaProxy, uploadModelPackage } from '../api/model'
import { activeTenant, getModelJson, setModelJson } from '../lib/modelStore'
import type { NgsiModel } from '../types/model'

function exampleKeyFromUrl(url: string, parsed: unknown): string | null {
  if (parsed && typeof parsed === 'object' && 'type' in parsed) {
    const ty = (parsed as { type?: unknown }).type
    if (typeof ty === 'string') {
      const last = ty.split('/').pop()
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

function readStoredModel(): Partial<NgsiModel> | null {
  try {
    const raw = getModelJson()
    return raw ? (JSON.parse(raw) as Partial<NgsiModel>) : null
  } catch {
    return null
  }
}

export function useModel(onSave?: () => void) {
  const { t } = useTranslation()
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

  const externalContextHint = t('config.model.status.externalContextHint')

  function persistNoteFor(tenant: string | null | undefined, persisted: boolean): string {
    return persisted && tenant
      ? t('config.model.status.persistedInTenant', { tenant })
      : t('config.model.status.persistedLocally')
  }

  function boolLabel(value: boolean): string {
    return value ? t('config.model.status.yes') : t('config.model.status.no')
  }

  async function onLoadUrls() {
    const urls = schemaUrls.trim().split(/\n+/).filter(Boolean)
    const ctx = contextUrl.trim()
    const desc = descriptorUrl.trim()
    const exUrls = exampleUrls.trim().split(/\n+/).filter(Boolean)
    if (!urls.length && !ctx && !desc && !exUrls.length) {
      setModelStatus(t('config.model.status.needUrl'))
      return
    }
    setLoadingUrls(true)
    setModelStatus(t('config.model.status.loading'))
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
          // ignora ejemplos individuales inválidos
        }
      }

      const tenant = activeTenant()
      if (tenant) {
        // Cada carga sustituye el tenant. Contexto por URL = solo meta.contextUrl
        // (no se materializa context/ en disco).
        await saveTenantModel(tenant, {
          schemas: loaded.schemas,
          context: null,
          descriptor: loaded.descriptor,
          examples: loaded.examples,
          packageName: loaded.packageName,
          contextUrl: loaded.contextUrl,
        })
      }
      setModelJson(JSON.stringify(loaded))
      setModelStatus(
        t('config.model.status.loaded', {
          schemas: loaded.schemas.length,
          context: boolLabel(!!loaded.context),
          descriptor: boolLabel(!!loaded.descriptor),
          examples: Object.keys(loaded.examples).length,
          persistNote: persistNoteFor(tenant, !!tenant),
          externalNote: ctx ? externalContextHint : '',
        }),
      )
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
    setModelStatus(t('config.model.status.processing', { file: modelFile.name }))
    try {
      const tenant = activeTenant()
      const externalCtx = packageContextUrl.trim()
      const result = await uploadModelPackage(
        modelFile,
        tenant ?? undefined,
        externalCtx || undefined,
      )
      const resolvedContextUrl = result.contextUrl ?? (externalCtx || null)
      const loaded: NgsiModel = {
        schemas: result.schemas ?? [],
        context: result.context ?? null,
        descriptor: result.descriptor ?? null,
        examples: result.examples ?? {},
        schemaUrls: [],
        contextUrl: resolvedContextUrl,
        descriptorUrl: null,
        exampleUrls: [],
        packageName: modelFile.name,
      }
      setModelJson(JSON.stringify(loaded))
      onSave?.()
      const s = result.summary
      setModelStatus(
        t('config.model.status.packageLoaded', {
          schemas: s.schemas,
          context: boolLabel(!!s.context),
          descriptor: boolLabel(!!s.descriptor),
          examples: s.examples,
          persistNote: persistNoteFor(tenant, !!result.persisted),
          stableNote:
            !externalCtx && resolvedContextUrl
              ? t('config.model.status.stableContextUrl', { url: resolvedContextUrl })
              : '',
          externalNote: externalCtx ? externalContextHint : '',
        }),
      )
    } catch (e) {
      setModelStatus(e instanceof Error ? e.message : t('config.model.status.processError'))
    } finally {
      setLoadingPackage(false)
    }
  }

  async function onClear() {
    const tenant = activeTenant()
    if (tenant) {
      try {
        await clearTenantModel(tenant)
      } catch (e) {
        setModelStatus(e instanceof Error ? e.message : t('config.model.status.clearError'))
        return
      }
    }
    setModelJson(null)
    setSchemaUrls('')
    setContextUrl('')
    setDescriptorUrl('')
    setExampleUrls('')
    setPackageContextUrl('')
    setModelFile(null)
    setModelStatus(t('config.model.status.cleared'))
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