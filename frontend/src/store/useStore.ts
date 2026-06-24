import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { Camera, Telemetry, Alert } from '@/types'
import { generateId } from '@/lib/utils'

type AppPhase = 'splash' | 'setup' | 'dashboard'
type GridSize = 1 | 2 | 3 | 4

interface StoreState {
  // UI state
  appPhase: AppPhase
  setAppPhase: (phase: AppPhase) => void

  // Cameras
  cameras: Camera[]
  selectedCameraId: string | null
  spotlightCameraId: string | null
  setCameras: (cameras: Camera[]) => void
  addCamera: (camera: Camera) => void
  removeCamera: (id: string) => void
  updateCamera: (id: string, updates: Partial<Camera>) => void
  selectCamera: (id: string | null) => void
  setSpotlight: (id: string | null) => void

  // Telemetry
  telemetry: Record<string, Telemetry>
  updateTelemetry: (data: Telemetry) => void

  // Alerts
  alerts: Alert[]
  addAlert: (alert: Omit<Alert, 'id'>) => void
  clearAlerts: () => void

  // Global settings
  gridSize: GridSize
  setGridSize: (size: GridSize) => void
  backendUrl: string
  setBackendUrl: (url: string) => void
}

export const useStore = create<StoreState>()(
  persist(
    (set) => ({
      // UI state
      appPhase: 'splash',
      setAppPhase: (phase) => set({ appPhase: phase }),

      // Cameras
      cameras: [],
      selectedCameraId: null,
      spotlightCameraId: null,
      setCameras: (cameras) => set({ cameras }),
      addCamera: (camera) =>
        set((state) => ({ cameras: [...state.cameras, camera] })),
      removeCamera: (id) =>
        set((state) => ({
          cameras: state.cameras.filter((c) => c.id !== id),
          selectedCameraId:
            state.selectedCameraId === id ? null : state.selectedCameraId,
          spotlightCameraId:
            state.spotlightCameraId === id ? null : state.spotlightCameraId,
        })),
      updateCamera: (id, updates) =>
        set((state) => ({
          cameras: state.cameras.map((c) =>
            c.id === id ? { ...c, ...updates } : c
          ),
        })),
      selectCamera: (id) => set({ selectedCameraId: id }),
      setSpotlight: (id) => set({ spotlightCameraId: id }),

      // Telemetry
      telemetry: {},
      updateTelemetry: (data) =>
        set((state) => ({
          telemetry: { ...state.telemetry, [data.cam_id]: data },
        })),

      // Alerts
      alerts: [],
      addAlert: (alert) =>
        set((state) => {
          const newAlert: Alert = { ...alert, id: generateId() }
          const alerts = [newAlert, ...state.alerts].slice(0, 100)
          return { alerts }
        }),
      clearAlerts: () => set({ alerts: [] }),

      // Global settings
      gridSize: 2,
      setGridSize: (size) => set({ gridSize: size }),
      backendUrl: 'http://localhost:8000',
      setBackendUrl: (url) => set({ backendUrl: url }),
    }),
    {
      name: 'visionsense-store',
      partialize: (state) => ({
        backendUrl: state.backendUrl,
        gridSize: state.gridSize,
      }),
    }
  )
)
