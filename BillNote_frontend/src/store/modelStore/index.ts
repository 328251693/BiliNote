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

    //  获取所有可用模型 (全局可用模型列表)
    loadEnabledModels: async () => {
      try {
        set({ loading: true })
        const list = await fetchEnableModels() as unknown as IModelListItem[]
        set({ modelList: list })
      } catch (error) {
        set({ modelList: [] })
        console.error('加载可用模型失败', error)
      } finally {
        set({ loading: false })
      }
    },

    //  通过 provider 获取该供应商的模型列表
    loadModels: async (providerId: string) => {
      if (!providerId) {
        set({ models: [] })
        return
      }
      try {
        set({ loading: true })
        const res = await fetchModels(providerId) as unknown as RemoteModelsResponse

        let models: IModel[] = []

        // 兼容 SyncPage 分页对象与普通数组两种格式
        if (Array.isArray(res.models)) {
          models = res.models
        } else if (res.models?.data && Array.isArray(res.models.data)) {
          models = res.models.data
        }

        set({ models })
      } catch (error) {
        set({ models: [] })
        console.error('加载模型列表失败', error)
      } finally {
        set({ loading: false })
      }
    },

    //  单独获取某个供应商下已启用模型
    loadModelsById: async (providerId: string) => {
      if (!providerId) return []
      try {
        const models = await fetchEnableModelById(providerId) as unknown as IModelListItem[]
        console.log('获取供应商模型成功:', models)
        return models
      } catch (error) {
        console.error('加载供应商模型失败', error)
        return []
      }
    },

    //  新增模型逻辑
    addNewModel: async (providerId: string, modelId: string) => {
      if (!providerId || !modelId) throw new Error('供应商和模型不能为空')
      try {
        // request 拦截器已经解包响应；成功时 data 为空，失败会直接抛异常。
        await addModel({ provider_id: providerId, model_name: modelId })
        console.log('新增模型成功:', modelId)
        await get().loadModels(providerId)
      } catch (error) {
        console.error('添加模型出错', error)
        throw error
      }
    },

    //  删除模型
    deleteModel: async (modelId: number) => {
      try {
        await deleteModelById(modelId)
        //  删除后更新本地状态（可选）
        set((state) => ({
          models: state.models.filter((model) => model.id !== modelId.toString())
        }))
      } catch (error) {
        console.error('删除模型失败', error)
      }
    },

    //  切换选中模型
    setSelectedModel: (modelId: string) => set({ selectedModel: modelId }),

    //  清空
    clearModels: () => set({ models: [], selectedModel: '', modelList: [] }),
  }))
)
