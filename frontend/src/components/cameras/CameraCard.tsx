import { Play, Square, Wifi, Camera, Circle } from 'lucide-react'
import { useStore } from '@/store/useStore'
import * as api from '@/lib/api'
import type { Camera as CameraType } from '@/types'

interface CameraCardProps {
  camera: CameraType
  isSelected: boolean
  onClick: () => void
}

const statusConfig = {
  idle:       { color: 'text-muted-foreground', dot: 'bg-muted-foreground opacity-30', label: 'Idle' },
  connecting: { color: 'text-muted-foreground', dot: 'bg-muted-foreground animate-pulse', label: 'Connecting' },
  live:       { color: 'text-foreground',       dot: 'bg-foreground',                   label: 'Live' },
  error:      { color: 'text-destructive',      dot: 'bg-destructive',                  label: 'Error' },
  stopped:    { color: 'text-muted-foreground', dot: 'bg-muted-foreground opacity-30', label: 'Stopped' },
}

export function CameraCard({ camera, isSelected, onClick }: CameraCardProps) {
  const { updateCamera } = useStore()
  const status = statusConfig[camera.status]
  const canStart = camera.status === 'idle' || camera.status === 'stopped' || camera.status === 'error'

  async function handleToggle(e: React.MouseEvent) {
    e.stopPropagation()
    try {
      if (canStart) {
        updateCamera(camera.id, { status: 'connecting' })
        const updated = await api.startCamera(camera.id)
        updateCamera(camera.id, updated)
      } else {
        const updated = await api.stopCamera(camera.id)
        updateCamera(camera.id, updated)
      }
    } catch {
      updateCamera(camera.id, { status: 'error' })
    }
  }

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 p-2.5 rounded-lg transition-all duration-150 text-left group ${
        isSelected
          ? 'bg-primary/10 border border-primary/20'
          : 'hover:bg-secondary/60 border border-transparent'
      }`}
    >
      <div className="relative shrink-0">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
          isSelected ? 'bg-primary/10' : 'bg-secondary'
        }`}>
          {camera.source.type === 'rtsp' ? (
            <Wifi className={`w-4 h-4 ${isSelected ? 'text-foreground' : 'text-muted-foreground'}`} />
          ) : (
            <Camera className={`w-4 h-4 ${isSelected ? 'text-foreground' : 'text-muted-foreground'}`} />
          )}
        </div>
        <Circle className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 fill-current ${status.dot}`} />
      </div>

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium truncate ${isSelected ? 'text-foreground' : 'text-foreground/80'}`}>
          {camera.name}
        </p>
        <p className={`text-xs ${status.color}`}>{status.label}</p>
      </div>

      {/* Start / Stop button */}
      <button
        onClick={handleToggle}
        className={`shrink-0 w-6 h-6 rounded flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all ${
          canStart
            ? 'hover:bg-primary/10 text-muted-foreground hover:text-foreground'
            : 'hover:bg-destructive/10 text-muted-foreground hover:text-destructive'
        }`}
        title={canStart ? 'Start stream' : 'Stop stream'}
      >
        {canStart ? <Play className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
      </button>
    </button>
  )
}
