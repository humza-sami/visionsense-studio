import { Wifi, Camera, Circle } from 'lucide-react'
import type { Camera as CameraType } from '@/types'

interface CameraCardProps {
  camera: CameraType
  isSelected: boolean
  onClick: () => void
}

const statusConfig = {
  idle: { color: 'text-muted-foreground', dot: 'bg-muted-foreground', label: 'Idle' },
  connecting: { color: 'text-amber-400', dot: 'bg-amber-400', label: 'Connecting' },
  live: { color: 'text-green-400', dot: 'bg-green-400', label: 'Live' },
  error: { color: 'text-red-400', dot: 'bg-red-400', label: 'Error' },
  stopped: { color: 'text-muted-foreground', dot: 'bg-muted-foreground', label: 'Stopped' },
}

export function CameraCard({ camera, isSelected, onClick }: CameraCardProps) {
  const status = statusConfig[camera.status]

  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-3 p-2.5 rounded-lg transition-all duration-150 text-left group ${
        isSelected
          ? 'bg-indigo-500/15 border border-indigo-500/30'
          : 'hover:bg-secondary/60 border border-transparent'
      }`}
    >
      <div className="relative shrink-0">
        <div className={`w-8 h-8 rounded-full flex items-center justify-center ${
          isSelected ? 'bg-indigo-500/20' : 'bg-secondary'
        }`}>
          {camera.source.type === 'rtsp' ? (
            <Wifi className={`w-4 h-4 ${isSelected ? 'text-indigo-400' : 'text-muted-foreground'}`} />
          ) : (
            <Camera className={`w-4 h-4 ${isSelected ? 'text-indigo-400' : 'text-muted-foreground'}`} />
          )}
        </div>
        <Circle
          className={`absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 fill-current ${status.dot} ${
            camera.status === 'live' ? 'shadow-[0_0_4px_rgba(34,197,94,0.8)]' :
            camera.status === 'connecting' ? 'animate-pulse' : ''
          }`}
        />
      </div>

      <div className="flex-1 min-w-0">
        <p className={`text-sm font-medium truncate ${isSelected ? 'text-foreground' : 'text-foreground/80'}`}>
          {camera.name}
        </p>
        <p className={`text-xs ${status.color}`}>{status.label}</p>
      </div>
    </button>
  )
}
