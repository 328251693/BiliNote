import { create } from 'zustand'
import { IProvider } from '@/types'
import {
  addProvider,
  getProviderById,
  getProviderList,
  updateProviderById,
} from '@/services/model.ts'

type BackendProvider = {
  id: string
  name: string
  logo?: string
  api_key?: string
  base_url?: string
  type: string
  enabled?: number
}

interface ProviderStore {
  provider: IProvider[]
  setProvider: (provider: IProvider) => void
  setAllProviders: (providers: IProvider[]) => void
  getProviderById: (id: string) => IProvider | undefined
  getProviderList: () => IProvider[]
  fetchProviderList: () => Promise<void>
  loadProviderById: (id: string) => Promise<IProvider>
  addNewProvider: (provider: Pick<IProvider, 'name' | 'apiKey' | 'baseUrl' | 'type'>) => Promise<IProvider>
  updateProvider: (provider: Pick<IProvider, 'id'> & Partial<Omit<IProvider, 'id'>>) => Promise<void>
}

export const useProviderStore = create<ProviderStore>((set, get) => ({
  provider: [],

  // ??????? provider
  setProvider: newProvider =>
    set(state => {
      const exists = state.provider.find(p => p.id === newProvider.id)
      if (exists) {
        return {
          provider: state.provider.map(p => (p.id === newProvider.id ? newProvider : p)),
        }
      } else {
        return { provider: [...state.provider, newProvider] }
      }
    }),

  // ???? provider ??
  setAllProviders: providers => set({ provider: providers }),
  loadProviderById: async (id: string) => {
    const item = await getProviderById(id) as unknown as BackendProvider
    return {
      id: item.id,
      name: item.name,
      logo: item.logo ?? 'custom',
      apiKey: item.api_key ?? '',
      baseUrl: item.base_url ?? '',
      type: item.type,
      enabled: item.enabled ?? 1,
    }
  },
  addNewProvider: async (provider) => {
    const payload = {
      ...provider,
      api_key: provider.apiKey,
      base_url: provider.baseUrl,
    }
    try {
      // request ?????? { code, msg, data } ??? data?
      // add_provider ? data ????? ID?????? Axios ???
      const created = await addProvider(payload) as unknown as string | { id?: string }
      const id = typeof created === 'string' ? created : created.id
      if (!id) throw new Error('??????????? ID')

      await get().fetchProviderList()
      return {
        id,
        name: provider.name,
        logo: 'custom',
        apiKey: provider.apiKey,
        baseUrl: provider.baseUrl,
        type: provider.type,
        enabled: 1,
      }
    } catch (error) {
      console.error('Error fetching provider:', error)
      throw error
    }
  },
  // ? id ???? provider
  getProviderById: id => get().provider.find(p => p.id === id),
  updateProvider: async (provider) => {
    try {
      const existing = get().provider.find(p => p.id === provider.id)
      const merged = { ...existing, ...provider }

      const data = {
        ...merged,
        api_key: merged.apiKey,
        base_url: merged.baseUrl,
      }
      // ?????????????? data ??
      await updateProviderById(data)
      await get().fetchProviderList()
    } catch (error) {
      console.error('Error updating provider:', error)
    }
  },
  getProviderList: () => get().provider,
  fetchProviderList: async () => {
    try {
      const res = await getProviderList() as unknown as BackendProvider[]

        set({
          provider: res.map(
            (item: BackendProvider) => {
              return {
                id: item.id,
                name: item.name,
                logo: item.logo ?? 'custom',
                apiKey: item.api_key ?? '',
                baseUrl: item.base_url ?? '',
                type: item.type,
                enabled: item.enabled ?? 1,
              }
            }
          ),
        })
    } catch (error) {
      console.error('Error fetching provider list:', error)
    }
  },
}))
