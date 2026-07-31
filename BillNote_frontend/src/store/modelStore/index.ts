import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
  fetchModels,
  addModel,
  fetchEnableModels,
  fetchEnableModelById,
  deleteModelById
} from '@/services/model'

interface IModel {
  id: string
  created: number
  object: string
  owned_by: string
  permission: string
  root: string
}

interface IModelListItem {
  id: number
  provider_id: string
  model_name: string
  created_at?: string
}

type RemoteModelsResponse = {
  models?: IModel[] | { data?: IModel[] }
}

interface ModelStore {
  models: IModel[]
  modelList: IModelListItem[]
  loading: boolean
  selectedModel: string

  loadModels: (providerId: string) => Promise<void>
  loadModelsById: (providerId: string) => Promise<IModelListItem[]>
  loadEnabledModels: () => Promise<void>
  addNewModel: (providerId: string, modelId: string) => Promise<void>
  deleteModel: (modelId: number) => Promise<void>
  setSelectedModel: (modelId: string) => void
  clearModels: () => void
}

export const useModelStore = create<ModelStore>()(
  devtools((set, get) => ({
    models: [],
    modelList: [],
    loading: false,
    selectedModel: '',

    //  ???????? (????????)
    loadEnabledModels: async () => {
      try {
        set({ loading: true })
        const list = await fetchEnableModels() as unknown as IModelListItem[]
        set({ modelList: list })
      } catch (error) {
        set({ modelList: [] })
        console.error('????????', error)
      } finally {
        set({ loading: false })
      }
    },

    //  ?? provider ???????????
    loadModels: async (providerId: string) => {
      if (!providerId) {
        set({ models: [] })
        return
      }
      try {
        set({ loading: true })
        const res = await fetchModels(providerId) as unknown as RemoteModelsResponse

        let models: IModel[] = []

        // ?? SyncPage ?????????????
        if (Array.isArray(res.models)) {
          models = res.models
        } else if (res.models?.data && Array.isArray(res.models.data)) {
          models = res.models.data
        }

        set({ models })
      } catch (error) {
        set({ models: [] })
        console.error('????????', error)
      } finally {
        set({ loading: false })
      }
    },

    //  ???????????????
    loadModelsById: async (providerId: string) => {
      if (!providerId) return []
      try {
        const models = await fetchEnableModelById(providerId) as unknown as IModelListItem[]
        console.log('?????????:', models)
        return models
      } catch (error) {
        console.error('?????????', error)
        return []
      }
    },

    //  ??????
    addNewModel: async (providerId: string, modelId: string) => {
      if (!providerId || !modelId) throw new Error('??????????')
      try {
        // request ????????????? data ????????????
        await addModel({ provider_id: providerId, model_name: modelId })
        console.log('??????:', modelId)
        await get().loadModels(providerId)
      } catch (error) {
        console.error('??????', error)
        throw error
      }
    },

    //  ????
    deleteModel: async (modelId: number) => {
      try {
        await deleteModelById(modelId)
        //  ?????????????
        set((state) => ({
          models: state.models.filter((model) => model.id !== modelId.toString())
        }))
      } catch (error) {
        console.error('??????', error)
      }
    },

    //  ??????
    setSelectedModel: (modelId: string) => set({ selectedModel: modelId }),

    //  ??
    clearModels: () => set({ models: [], selectedModel: '', modelList: [] }),
  }))
)
