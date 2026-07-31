import { useForm } from 'react-hook-form'
import { z } from 'zod'
import { zodResolver } from '@hookform/resolvers/zod'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useParams, useNavigate } from 'react-router-dom'
import { useProviderStore } from '@/store/providerStore'
import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { testConnection, deleteModelById } from '@/services/model.ts'
import { ModelSelector } from '@/components/Form/modelForm/ModelSelector.tsx'
import { X } from 'lucide-react'
import { useModelStore } from '@/store/modelStore'

// ? Provider??schema
const ProviderSchema = z.object({
  name: z.string().min(2, '?????? 2 ???'),
  apiKey: z.string().min(1, '??? API Key'),
  baseUrl: z.string().url('????? URL'),
  type: z.string(),
})

type ProviderFormValues = z.infer<typeof ProviderSchema>

const getErrorMessage = (error: unknown) => {
  if (typeof error !== 'object' || error === null) return '????'
  const value = error as { msg?: unknown; data?: { msg?: unknown } }
  if (typeof value.msg === 'string') return value.msg
  if (typeof value.data?.msg === 'string') return value.data.msg
  return '????'
}

interface EnabledModel {
  id: number
  model_name: string
}
const ProviderForm = ({ isCreate = false }: { isCreate?: boolean }) => {
  const { id } = useParams()
  const navigate = useNavigate()
  const isEditMode = !isCreate

  const loadProviderById = useProviderStore(state => state.loadProviderById)
  const updateProvider = useProviderStore(state => state.updateProvider)
  const addNewProvider = useProviderStore(state => state.addNewProvider)
  const [loading, setLoading] = useState(true)
  const [testing, setTesting] = useState(false)
  const [savingProvider, setSavingProvider] = useState(false)
  const [isBuiltIn, setIsBuiltIn] = useState(false)
  const loadModelsById= useModelStore(state => state.loadModelsById)
  const [models, setModels] = useState<EnabledModel[]>([])

  const providerForm = useForm<ProviderFormValues>({
    resolver: zodResolver(ProviderSchema),
    defaultValues: {
      name: '',
      apiKey: '',
      baseUrl: '',
      type: 'custom',
    },
  })
  useEffect(() => {
    let active = true

    const load = async () => {
      if (isEditMode && id) {
        const data = await loadProviderById(id)
        if (!active) return
        providerForm.reset(data)
        setIsBuiltIn(data.type === 'built-in')

        const enabledModels = await loadModelsById(id)
        if (!active) return
        setModels(enabledModels)
      } else {
        providerForm.reset({
          name: '',
          apiKey: '',
          baseUrl: '',
          type: 'custom',
        })
        setIsBuiltIn(false)
        setModels([])
      }
      if (active) setLoading(false)
    }

    load().catch(error => {
      console.error('???????', error)
      if (active) setLoading(false)
    })

    return () => {
      active = false
    }
  }, [id, isEditMode, loadModelsById, loadProviderById, providerForm])

  const refreshEnabledModels = async (providerId: string) => {
    const enabledModels = await loadModelsById(providerId)
    setModels(enabledModels)
  }

  const handelDelete = async (modelId: number) => {
    if (!window.confirm('???????????')) return

    try {
      const res = await deleteModelById(modelId)
      console.log('?? ????:', res)

      toast.success('????')
      if (id) await refreshEnabledModels(id)

    } catch {
      toast.error('????')
    }
  }
  // ?????
  const handleTest = async () => {
    const values = providerForm.getValues()
    if (!values.apiKey || !values.baseUrl) {
      toast.error('??? API Key ? Base URL')
      return
    }
    try {
      if (!id){
        toast.error('?????????')
        return
      }
      setTesting(true)
     await testConnection({
             id
          })

        toast.success('??????? ??')

    } catch (error) {
      toast.error(`????: ${getErrorMessage(error)}`)
    } finally {
      setTesting(false)
    }
  }

  // ??Provider??
  const onProviderSubmit = async (values: ProviderFormValues) => {
    if (savingProvider) return
    setSavingProvider(true)
    try {
      if (isEditMode && id) {
        await updateProvider({ ...values, id })
        providerForm.reset(values)
        toast.success('???????')
      } else {
        const created = await addNewProvider(values)
        toast.success('???????')
        navigate(`/settings/model/${created.id}`, { replace: true })
      }
    } catch (error) {
      toast.error(getErrorMessage(error) || '???????')
    } finally {
      setSavingProvider(false)
    }
  }

  if (loading) return <div className="p-4">???...</div>

  return (
    <div className="flex flex-col gap-8 p-4">
      {/* Provider???? */}
      <Form {...providerForm}>
        <form
          onSubmit={providerForm.handleSubmit(onProviderSubmit)}
          className="flex max-w-xl flex-col gap-4"
        >
          <div className="text-lg font-bold">
            {isEditMode ? '???????' : '???????'}
          </div>
          {!isBuiltIn && (
            <div className="text-sm text-red-500 italic">
              ?????????????? OpenAI SDK
            </div>
          )}
          <FormField
            control={providerForm.control}
            name="name"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">??</FormLabel>
                <FormControl>
                  <Input {...field} disabled={isBuiltIn} className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="apiKey"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">API Key</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="baseUrl"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">API??</FormLabel>
                <FormControl>
                  <Input {...field} className="flex-1" />
                </FormControl>
                <Button type="button" onClick={handleTest} variant="ghost" disabled={testing}>
                  {testing ? '???...' : '?????'}
                </Button>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={providerForm.control}
            name="type"
            render={({ field }) => (
              <FormItem className="flex items-center gap-4">
                <FormLabel className="w-24 text-right">??</FormLabel>
                <FormControl>
                  <Input {...field} disabled className="flex-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <div className="pt-2">
            <Button type="submit" disabled={savingProvider || !providerForm.formState.isDirty}>
              {savingProvider ? '???...' : isEditMode ? '????' : '????'}
            </Button>
          </div>
        </form>
      </Form>

      {/* ?????? */}
      <div className="flex max-w-xl flex-col gap-4">
        <div className="flex flex-col gap-2">
          <span className="font-bold">????</span>
          <div className={'flex flex-col gap-2 rounded bg-[#FEF0F0] p-2.5'}>
            <h2 className={'font-bold'}>??!</h2>
            <span>????????????,?????????.</span>
          </div>
          {id ? (
            <ModelSelector
              providerId={id}
              onSaved={() => refreshEnabledModels(id)}
            />
          ) : (
            <div className="text-sm text-neutral-500">??????????????</div>
          )}

          {/*<datalist id="model-options">*/}
          {/*  {modelOptions.map(model => (*/}
          {/*    <option key={model.id + '1'} value={model.id} />*/}
          {/*  ))}*/}
          {/*</datalist>*/}
        </div>
        <div className="flex flex-col gap-2">
          <span className="font-bold">?????</span>
          <div className={'flex flex-wrap gap-2 rounded  p-2.5'}>
            {
              models && models.map(model => {
                return (
                  <span key={model.id} className="inline-flex items-center gap-1 rounded-md bg-blue-100 px-2 py-0.5 text-sm text-blue-700">
                    {model.model_name}
                    <button type="button" onClick={() => handelDelete(model.id)} className="hover:text-blue-900">
                      <X className="h-3 w-3" />
                    </button>
                  </span>

                )
              })
            }

          </div>
          {/*<ModelSelector providerId={id!} />*/}

          {/*<datalist id="model-options">*/}
          {/*  {modelOptions.map(model => (*/}
          {/*    <option key={model.id + '1'} value={model.id} />*/}
          {/*  ))}*/}
          {/*</datalist>*/}
        </div>
      </div>
    </div>
  )
}

export default ProviderForm
