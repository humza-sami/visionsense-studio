import { Plus } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { CameraFeed } from './CameraFeed'
import { AddCameraDialog } from './AddCameraDialog'

export function CameraGrid() {
  const { cameras, gridSize, selectedCameraId, spotlightCameraId, selectCamera, setSpotlight } = useStore()

  const totalCells = gridSize * gridSize
  const cells = Array.from({ length: totalCells })

  const gridCols = {
    1: 'grid-cols-1',
    2: 'grid-cols-2',
    3: 'grid-cols-3',
    4: 'grid-cols-4',
  }[gridSize]

  // If spotlight mode, show single full-screen camera
  if (spotlightCameraId) {
    const cam = cameras.find((c) => c.id === spotlightCameraId)
    if (cam) {
      return (
        <div className="w-full h-full p-1">
          <CameraFeed
            camera={cam}
            isSelected={false}
            isSpotlight
            onSelect={() => {}}
            onDoubleClick={() => setSpotlight(null)}
          />
          <p className="text-center text-xs text-muted-foreground mt-1">
            Double-click to exit spotlight
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
    <div className={`w-full h-full grid ${gridCols} gap-1.5 p-1.5`}>
      {cells.map((_, i) => {
        const camera = cameras[i]
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
            className="rounded-lg border-2 border-dashed border-border/40 bg-secondary/10 flex items-center justify-center group hover:border-indigo-500/30 hover:bg-indigo-500/5 transition-all duration-200 cursor-pointer"
          >
            <AddCameraDialog
              trigger={
                <div className="flex flex-col items-center gap-2 text-muted-foreground group-hover:text-indigo-400 transition-colors">
                  <div className="w-10 h-10 rounded-full bg-secondary/60 flex items-center justify-center group-hover:bg-indigo-500/10 transition-colors">
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
  )
}
