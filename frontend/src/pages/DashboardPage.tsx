import { useEffect } from 'react'
import { LayoutGrid, Settings, Wifi, WifiOff } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { useTelemetryWS } from '@/lib/websocket'
import { LeftSidebar } from '@/components/layout/LeftSidebar'
import { RightSidebar } from '@/components/layout/RightSidebar'
import { CameraGrid } from '@/components/cameras/CameraGrid'
import { AddCameraDialog } from '@/components/cameras/AddCameraDialog'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import * as api from '@/lib/api'
import logoUrl from '@/assets/logo.svg'

const GRID_SIZES = [1, 2, 3, 4] as const

export function DashboardPage() {
  const { cameras, setCameras, gridSize, setGridSize, backendUrl } = useStore()
  const { connected } = useTelemetryWS(backendUrl)

  useEffect(() => {
    api.setBackendUrl(backendUrl)
    api.getCameras().then(setCameras).catch(() => {})
  }, [backendUrl, setCameras])

  return (
    <TooltipProvider delayDuration={400}>
      <div className="flex flex-col h-screen bg-[#0a0a0f] overflow-hidden">
        {/* Top Bar */}
        <header className="h-12 flex items-center gap-3 px-3 border-b border-border/60 bg-[#111118] shrink-0">
          {/* Logo + Title */}
          <div className="flex items-center gap-2 shrink-0">
            <img src={logoUrl} alt="VS" className="w-7 h-7" />
            <div className="hidden sm:block">
              <span className="font-semibold text-sm text-gradient">VisionSense</span>
              <span className="text-xs text-muted-foreground ml-1">Studio</span>
            </div>
          </div>

          <div className="w-px h-5 bg-border/60 mx-1" />

          {/* Camera count */}
          <div className="text-xs text-muted-foreground shrink-0">
            <span className="tabular-nums text-foreground/70">{cameras.filter((c) => c.status === 'live').length}</span>
            <span className="mx-0.5">/</span>
            <span className="tabular-nums">{cameras.length}</span>
            <span className="ml-1">live</span>
          </div>

          <div className="flex-1" />

          {/* WS connection indicator */}
          <Tooltip>
            <TooltipTrigger asChild>
              <div className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs ${
                connected
                  ? 'text-green-400 bg-green-500/10'
                  : 'text-red-400 bg-red-500/10'
              }`}>
                {connected ? (
                  <Wifi className="w-3.5 h-3.5" />
                ) : (
                  <WifiOff className="w-3.5 h-3.5 animate-pulse" />
                )}
                <span className="hidden sm:inline">{connected ? 'Connected' : 'Reconnecting'}</span>
              </div>
            </TooltipTrigger>
            <TooltipContent>
              WebSocket telemetry {connected ? 'connected' : 'disconnected — auto-retrying'}
            </TooltipContent>
          </Tooltip>

          <div className="w-px h-5 bg-border/60 mx-1" />

          {/* Grid Size buttons */}
          <div className="flex items-center gap-0.5 bg-secondary/60 rounded-lg p-0.5">
            {GRID_SIZES.map((size) => (
              <Tooltip key={size}>
                <TooltipTrigger asChild>
                  <button
                    onClick={() => setGridSize(size)}
                    className={`w-7 h-7 rounded-md flex items-center justify-center transition-all duration-150 ${
                      gridSize === size
                        ? 'bg-primary text-primary-foreground shadow-sm'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                    }`}
                  >
                    <GridIcon size={size} />
                  </button>
                </TooltipTrigger>
                <TooltipContent>{size}×{size} grid</TooltipContent>
              </Tooltip>
            ))}
          </div>

          <div className="w-px h-5 bg-border/60 mx-1" />

          {/* Add camera */}
          <AddCameraDialog />

          {/* Settings */}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button size="icon" variant="ghost" className="w-8 h-8">
                <Settings className="w-4 h-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>Settings</TooltipContent>
          </Tooltip>
        </header>

        {/* Main 3-column layout */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left Sidebar */}
          <div className="w-[280px] shrink-0 overflow-hidden">
            <LeftSidebar />
          </div>

          {/* Center: Camera Grid */}
          <main className="flex-1 overflow-hidden bg-[#0a0a0f]">
            <CameraGrid />
          </main>

          {/* Right Sidebar */}
          <div className="w-[320px] shrink-0 overflow-hidden">
            <RightSidebar />
          </div>
        </div>
      </div>
    </TooltipProvider>
  )
}

function GridIcon({ size }: { size: 1 | 2 | 3 | 4 }) {
  if (size === 1) {
    return <LayoutGrid className="w-3.5 h-3.5" />
  }
  const count = size * size
  const cols = size
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
      {Array.from({ length: count }).map((_, i) => {
        const col = i % cols
        const row = Math.floor(i / cols)
        const cellSize = 12 / cols
        const gap = 1
        const x = col * (cellSize + gap / cols)
        const y = row * (cellSize + gap / cols)
        const s = cellSize - gap * ((cols - 1) / cols)
        return (
          <rect
            key={i}
            x={x + 1}
            y={y + 1}
            width={s}
            height={s}
            rx={0.5}
            fill="currentColor"
            opacity={0.8}
          />
        )
      })}
    </svg>
  )
}
