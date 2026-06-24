import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, ChevronLeft, ChevronRight, LoaderCircle, Plus } from 'lucide-react'
import { useStore } from '@/store/useStore'
import * as api from '@/lib/api'
import { CameraFeed } from './CameraFeed'
import { AddCameraDialog } from './AddCameraDialog'

export function CameraGrid() {
  const {
    cameras, selectedCameraId, spotlightCameraId, selectCamera, setSpotlight,
    cameraPage: page, setCameraPage: setPage, updateCamera,
  } = useStore()
  const [isSwitching, setIsSwitching] = useState(false)

  const pageSize = 2
  const pageCount = Math.max(1, Math.ceil(cameras.length / pageSize))
  const visibleCameras = cameras.slice(page * pageSize, (page + 1) * pageSize)
  const visibleIds = useMemo(
    () => visibleCameras.map((camera) => camera.id),
    [visibleCameras]
  )
  const visibleIdsKey = visibleIds.join(',')
  const cells = Array.from({ length: pageSize })

  useEffect(() => {
    if (page >= pageCount) setPage(pageCount - 1)
  }, [page, pageCount, setPage])

  useEffect(() => {
    if (visibleIds.length === 0) return
    let cancelled = false
    setIsSwitching(true)
    setSpotlight(null)

    const visibleSet = new Set(visibleIds)
    const currentCameras = useStore.getState().cameras
    currentCameras.forEach((camera) => {
      updateCamera(camera.id, {
        status: visibleSet.has(camera.id) ? 'connecting' : 'stopped',
      })
    })

    void api.activateCameras(visibleIds)
      .then((activeCameras) => {
        if (cancelled) return
        activeCameras.forEach((camera) => updateCamera(camera.id, camera))
      })
      .catch(() => {
        if (cancelled) return
        visibleIds.forEach((id) => updateCamera(id, {
          status: 'error',
          error_message: 'Failed to activate camera page',
        }))
      })
      .finally(() => {
        if (!cancelled) setIsSwitching(false)
      })

    return () => {
      cancelled = true
    }
  }, [visibleIdsKey, setSpotlight, updateCamera])

  useEffect(() => {
    if (!spotlightCameraId) return
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSpotlight(null)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [spotlightCameraId, setSpotlight])

  // If spotlight mode, show single full-screen camera
  if (spotlightCameraId) {
    const cam = cameras.find((c) => c.id === spotlightCameraId)
    if (cam) {
      return (
        <div className="relative w-full h-full p-1">
          <button
            type="button"
            onClick={() => setSpotlight(null)}
            className="absolute top-3 left-3 z-20 h-8 px-3 rounded-md bg-black/70 text-white text-xs flex items-center gap-1.5 hover:bg-black/85 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to all cameras
          </button>
          <CameraFeed
            camera={cam}
            isSelected={false}
            isSpotlight
            onSelect={() => {}}
            onDoubleClick={() => setSpotlight(null)}
          />
          <p className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 rounded bg-black/60 px-2 py-1 text-xs text-white/80">
            Press Esc or double-click to exit
          </p>
        </div>
      )
    }
  }

  if (cameras.length === 0) {
    return (
      <div className="w-full h-full flex items-center justify-center">
        <div className="text-center space-y-4">
          <div className="w-20 h-20 rounded-full bg-secondary/50 flex items-center justify-center mx-auto border border-border">
            <Plus className="w-10 h-10 text-muted-foreground" />
          </div>
          <div>
            <p className="text-foreground font-medium">No cameras connected</p>
            <p className="text-sm text-muted-foreground mt-1">Add a camera to start monitoring</p>
          </div>
          <AddCameraDialog />
        </div>
      </div>
    )
  }

  return (
    <div className="relative w-full h-full">
      <div className="w-full h-full grid grid-cols-2 gap-1.5 p-1.5">
      {cells.map((_, i) => {
        const camera = visibleCameras[i]
        if (camera) {
          return (
            <CameraFeed
              key={camera.id}
              camera={camera}
              isSelected={selectedCameraId === camera.id}
              isSpotlight={spotlightCameraId === camera.id}
              onSelect={() => selectCamera(camera.id)}
              onDoubleClick={() => setSpotlight(camera.id)}
            />
          )
        }

        return (
          <div
            key={`empty-${i}`}
            className="rounded-lg border-2 border-dashed border-border/40 bg-secondary/10 flex items-center justify-center group hover:border-primary/30 hover:bg-primary/5 transition-all duration-200 cursor-pointer"
          >
            <AddCameraDialog
              trigger={
                <div className="flex flex-col items-center gap-2 text-muted-foreground group-hover:text-foreground transition-colors">
                  <div className="w-10 h-10 rounded-full bg-secondary/60 flex items-center justify-center group-hover:bg-primary/10 transition-colors">
                    <Plus className="w-5 h-5" />
                  </div>
                  <span className="text-xs font-medium">Add Camera</span>
                </div>
              }
            />
          </div>
        )
      })}
      </div>
      {isSwitching && (
        <div className="absolute inset-0 z-30 flex items-center justify-center bg-background/55 backdrop-blur-sm pointer-events-none">
          <div className="flex items-center gap-2 rounded-lg border border-border bg-card px-4 py-2 text-sm shadow-xl">
            <LoaderCircle className="w-4 h-4 animate-spin" />
            Loading cameras {page * pageSize + 1}–{Math.min((page + 1) * pageSize, cameras.length)}…
          </div>
        </div>
      )}
      {pageCount > 1 && (
        <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 rounded-lg border border-border/60 bg-card/95 p-1 shadow-lg backdrop-blur">
          <button
            type="button"
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-30"
            aria-label="Previous camera page"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="min-w-16 text-center text-xs tabular-nums text-muted-foreground">
            {page + 1} / {pageCount}
          </span>
          <button
            type="button"
            onClick={() => setPage(Math.min(pageCount - 1, page + 1))}
            disabled={page >= pageCount - 1}
            className="w-7 h-7 rounded flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary disabled:opacity-30"
            aria-label="Next camera page"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
    </div>
  )
}
