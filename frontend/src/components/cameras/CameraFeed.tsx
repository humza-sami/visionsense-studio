import { useState, useCallback } from 'react'
import { AlertTriangle, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getStreamUrl } from '@/lib/api'
import type { Camera } from '@/types'

interface CameraFeedProps {
  camera: Camera
  onSelect: () => void
  onDoubleClick: () => void
  isSelected: boolean
  isSpotlight: boolean
}

export function CameraFeed({ camera, onSelect, onDoubleClick, isSelected, isSpotlight }: CameraFeedProps) {
  const { telemetry, backendUrl, updateCamera } = useStore()
  const camTelemetry = telemetry[camera.id]
  const [imgError, setImgError] = useState(false)
  const [imgLoaded, setImgLoaded] = useState(false)

  const streamUrl = getStreamUrl(camera.id, backendUrl)
  const isLive = camera.status === 'live'
  const isConnecting = camera.status === 'connecting'
  const isError = camera.status === 'error' || imgError
  const recentAlert = camTelemetry?.alerts?.[0]

  const handleRetry = useCallback(() => {
    setImgError(false)
    setImgLoaded(false)
    updateCamera(camera.id, { status: 'connecting', error_message: undefined })
  }, [camera.id, updateCamera])

  const statusColor = {
    idle: 'border-white/10',
    connecting: 'border-amber-500/60',
    live: isSpotlight
      ? 'border-indigo-400 shadow-[0_0_0_2px_rgba(99,102,241,0.6)]'
      : isSelected
      ? 'border-indigo-500/70 shadow-[0_0_0_2px_rgba(99,102,241,0.3)]'
      : 'border-green-500/20',
    error: 'border-red-500/40',
    stopped: 'border-white/10',
  }[camera.status] || 'border-white/10'

  return (
    <div
      className={`relative w-full h-full rounded-lg overflow-hidden border-2 cursor-pointer transition-all duration-200 select-none bg-[#0d0d1a] ${statusColor}`}
      onClick={onSelect}
      onDoubleClick={onDoubleClick}
    >
      {/* MJPEG Stream */}
      {isLive && !imgError && (
        <img
          src={streamUrl}
          alt={camera.name}
          className={`absolute inset-0 w-full h-full object-cover transition-opacity duration-300 ${imgLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
          draggable={false}
        />
      )}

      {/* Connecting overlay */}
      {isConnecting && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#0d0d1a]">
          <div className="relative">
            <Wifi className="w-8 h-8 text-amber-400 animate-pulse" />
          </div>
          <p className="text-xs text-amber-400">Connecting...</p>
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Error overlay */}
      {(isError) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-[#0d0d1a]">
          <WifiOff className="w-8 h-8 text-red-400" />
          <p className="text-xs text-red-400 text-center px-4">
            {camera.error_message ?? 'Stream unavailable'}
          </p>
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleRetry() }} className="text-xs h-7 gap-1.5">
            <RefreshCw className="w-3 h-3" /> Retry
          </Button>
        </div>
      )}

      {/* Idle overlay */}
      {camera.status === 'idle' && !isConnecting && !isError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-[#0d0d1a]">
          <div className="w-10 h-10 rounded-full bg-secondary/50 flex items-center justify-center">
            <Wifi className="w-5 h-5 text-muted-foreground" />
          </div>
          <p className="text-xs text-muted-foreground">Camera idle</p>
        </div>
      )}

      {/* Loading shimmer while stream initializes */}
      {isLive && !imgLoaded && !imgError && (
        <div className="absolute inset-0 bg-secondary/20 overflow-hidden">
          <div
            className="absolute inset-0 animate-shimmer"
            style={{
              background: 'linear-gradient(90deg, transparent 0%, rgba(99,102,241,0.05) 50%, transparent 100%)',
              backgroundSize: '200% 100%',
            }}
          />
        </div>
      )}

      {/* Top overlays */}
      <div className="absolute top-0 left-0 right-0 p-2 flex items-start justify-between pointer-events-none">
        {/* Camera name */}
        <div className="flex items-center gap-1.5 bg-black/60 backdrop-blur-sm rounded px-2 py-1 max-w-[60%]">
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            camera.status === 'live' ? 'bg-green-400 shadow-[0_0_4px_rgba(34,197,94,0.8)]' :
            camera.status === 'connecting' ? 'bg-amber-400 animate-pulse' :
            camera.status === 'error' ? 'bg-red-400' : 'bg-muted-foreground'
          }`} />
          <span className="text-xs font-medium text-white truncate">{camera.name}</span>
        </div>

        {/* FPS / inference */}
        {camTelemetry && (
          <div className="flex gap-1">
            <Badge variant="indigo" className="text-[10px] h-5 px-1.5 font-mono">
              {camTelemetry.fps.toFixed(1)} fps
            </Badge>
            <Badge variant="secondary" className="text-[10px] h-5 px-1.5 font-mono">
              {Math.round(camTelemetry.inference_ms)}ms
            </Badge>
          </div>
        )}
      </div>

      {/* Bottom counts */}
      {camTelemetry && Object.keys(camTelemetry.counts).length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 p-2 flex gap-1 flex-wrap pointer-events-none">
          {Object.entries(camTelemetry.counts).map(([label, count]) => (
            <div key={label} className="bg-black/70 backdrop-blur-sm rounded px-1.5 py-0.5">
              <span className="text-[10px] text-white/90">
                {label}: <span className="font-bold text-indigo-300">{count}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Alert indicator */}
      {recentAlert && (
        <div className="absolute top-2 right-2 pointer-events-none">
          <div className="w-2 h-2 rounded-full bg-red-400 shadow-[0_0_8px_rgba(239,68,68,0.8)] animate-pulse" />
        </div>
      )}

      {/* Spotlight indicator */}
      {isSpotlight && (
        <div className="absolute inset-0 border-2 border-indigo-400 rounded-lg pointer-events-none" />
      )}

      {/* Alert banner */}
      {recentAlert && (
        <div className="absolute bottom-8 left-2 right-2 bg-red-500/20 backdrop-blur-sm border border-red-500/30 rounded px-2 py-1 flex items-center gap-1.5 pointer-events-none">
          <AlertTriangle className="w-3 h-3 text-red-400 shrink-0" />
          <span className="text-[10px] text-red-300 truncate">{recentAlert.type}: {recentAlert.detail}</span>
        </div>
      )}
    </div>
  )
}
