import { useState, useCallback, useEffect } from 'react'
import { AlertTriangle, RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { getStreamUrl } from '@/lib/api'
import { WebRTCFeed } from './WebRTCFeed'
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
  const [webrtcLoaded, setWebrtcLoaded] = useState(false)
  const [useFallback, setUseFallback] = useState(false)
  const [streamVersion, setStreamVersion] = useState(0)
  const [webRtcVersion, setWebRtcVersion] = useState(0)

  const streamUrl = `${getStreamUrl(camera.id, backendUrl)}?v=${streamVersion}`
  const isLive = camera.status === 'live'
  const isConnecting = camera.status === 'connecting'
  const isError = camera.status === 'error' || (useFallback && imgError)
  const mediaLoaded = webrtcLoaded || (useFallback && imgLoaded)
  const recentAlert = camTelemetry?.alerts?.[0]

  const handleRetry = useCallback(() => {
    setImgError(false)
    setImgLoaded(false)
    setWebrtcLoaded(false)
    setUseFallback(false)
    setStreamVersion((version) => version + 1)
    setWebRtcVersion((version) => version + 1)
    updateCamera(camera.id, { status: 'connecting', error_message: undefined })
  }, [camera.id, updateCamera])
  const handleWebRtcPlaying = useCallback(() => {
    setWebrtcLoaded(true)
    setUseFallback(false)
  }, [])
  const handleWebRtcUnavailable = useCallback(() => {
    setWebrtcLoaded(false)
    setUseFallback(true)
  }, [])

  useEffect(() => {
    if (!imgError || !['live', 'connecting'].includes(camera.status)) return
    const timer = window.setTimeout(handleRetry, 1500)
    return () => window.clearTimeout(timer)
  }, [camera.status, handleRetry, imgError])

  useEffect(() => {
    if (!isLive || !useFallback) return
    const timer = window.setTimeout(
      () => setWebRtcVersion((version) => version + 1),
      3000
    )
    return () => window.clearTimeout(timer)
  }, [isLive, useFallback, webRtcVersion])

  const statusBorder = {
    idle:       'border-border',
    connecting: 'border-muted-foreground/60',
    live: isSpotlight
      ? 'border-primary ring-2 ring-primary/40'
      : isSelected
      ? 'border-primary/60 ring-1 ring-primary/20'
      : 'border-border',
    error:   'border-destructive/50',
    stopped: 'border-border',
  }[camera.status] || 'border-border'

  return (
    <div
      className={`relative w-full h-full rounded-lg overflow-hidden border-2 cursor-pointer transition-all duration-200 select-none bg-background ${statusBorder}`}
      onClick={onSelect}
      onDoubleClick={onDoubleClick}
    >
      {/* Production WebRTC transport */}
      {isLive && (
        <WebRTCFeed
          cameraId={camera.id}
          cameraName={camera.name}
          retryToken={webRtcVersion}
          onPlaying={handleWebRtcPlaying}
          onUnavailable={handleWebRtcUnavailable}
        />
      )}

      {/* MJPEG compatibility fallback */}
      {isLive && useFallback && !imgError && (
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
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background">
          <Wifi className="w-8 h-8 text-muted-foreground animate-pulse" />
          <p className="text-xs text-muted-foreground">Connecting...</p>
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce"
                style={{ animationDelay: `${i * 0.15}s` }}
              />
            ))}
          </div>
        </div>
      )}

      {/* Error overlay */}
      {isError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background">
          <WifiOff className="w-8 h-8 text-destructive" />
          <p className="text-xs text-destructive text-center px-4">
            {camera.error_message ?? 'Stream unavailable'}
          </p>
          <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); handleRetry() }} className="text-xs h-7 gap-1.5">
            <RefreshCw className="w-3 h-3" /> Retry
          </Button>
        </div>
      )}

      {/* Idle overlay */}
      {camera.status === 'idle' && !isConnecting && !isError && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background">
          <div className="w-10 h-10 rounded-full bg-secondary/50 flex items-center justify-center">
            <Wifi className="w-5 h-5 text-muted-foreground" />
          </div>
          <p className="text-xs text-muted-foreground">Camera idle</p>
        </div>
      )}

      {/* Loading shimmer */}
      {isLive && !mediaLoaded && !isError && (
        <div className="absolute inset-0 bg-secondary/20 overflow-hidden">
          <div className="absolute inset-0 animate-shimmer bg-gradient-to-r from-transparent via-secondary/30 to-transparent bg-[length:200%_100%]" />
        </div>
      )}

      {/* Top overlays */}
      <div className="absolute top-0 left-0 right-0 p-2 flex items-start justify-between pointer-events-none">
        <div className="flex items-center gap-1.5 bg-black/60 backdrop-blur-sm rounded px-2 py-1 max-w-[60%]">
          <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
            camera.status === 'live'       ? 'bg-foreground' :
            camera.status === 'connecting' ? 'bg-muted-foreground animate-pulse' :
            camera.status === 'error'      ? 'bg-destructive' :
                                             'bg-muted-foreground opacity-30'
          }`} />
          <span className="text-xs font-medium text-white truncate">{camera.name}</span>
        </div>

        {camTelemetry && (
          <div className="flex gap-1">
            <Badge variant="secondary" className="text-[10px] h-5 px-1.5 font-mono">
              {camTelemetry.fps.toFixed(1)} fps
            </Badge>
            <Badge variant="outline" className="text-[10px] h-5 px-1.5 font-mono bg-black/60">
              {Math.round(camTelemetry.inference_ms)}ms
            </Badge>
          </div>
        )}
      </div>

      {isLive && mediaLoaded && (
        <div className="absolute bottom-2 right-2 pointer-events-none">
          <Badge variant="outline" className="text-[9px] h-5 px-1.5 bg-black/60 text-white border-white/20">
            {useFallback ? 'MJPEG fallback' : 'WebRTC'}
          </Badge>
        </div>
      )}

      {/* Bottom counts */}
      {camTelemetry && Object.keys(camTelemetry.counts).length > 0 && (
        <div className="absolute bottom-0 left-0 right-0 p-2 flex gap-1 flex-wrap pointer-events-none">
          {Object.entries(camTelemetry.counts).map(([label, count]) => (
            <div key={label} className="bg-black/70 backdrop-blur-sm rounded px-1.5 py-0.5">
              <span className="text-[10px] text-white/90">
                {label}: <span className="font-bold text-white">{count}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Alert dot */}
      {recentAlert && (
        <div className="absolute top-2 right-2 pointer-events-none">
          <div className="w-2 h-2 rounded-full bg-destructive animate-pulse" />
        </div>
      )}

      {/* Spotlight frame */}
      {isSpotlight && (
        <div className="absolute inset-0 border-2 border-primary rounded-lg pointer-events-none" />
      )}

      {/* Alert banner */}
      {recentAlert && (
        <div className="absolute bottom-8 left-2 right-2 bg-destructive/20 backdrop-blur-sm border border-destructive/30 rounded px-2 py-1 flex items-center gap-1.5 pointer-events-none">
          <AlertTriangle className="w-3 h-3 text-destructive shrink-0" />
          <span className="text-[10px] text-foreground truncate">{recentAlert.type}: {recentAlert.detail}</span>
        </div>
      )}
    </div>
  )
}
