import { useEffect } from 'react'
import { Camera, PanelLeftOpen, Settings, Wifi, WifiOff } from 'lucide-react'
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

export function DashboardPage() {
  const {
    cameras, setCameras, updateCamera, setGridSize, backendUrl,
    leftSidebarCollapsed, setLeftSidebarCollapsed,
  } = useStore()
  const { connected } = useTelemetryWS(backendUrl)

  useEffect(() => {
    api.setBackendUrl(backendUrl)
    api.getCameras().then((loadedCameras) => {
      setCameras(loadedCameras)
      const currentGridSize = useStore.getState().gridSize
      if (loadedCameras.length > currentGridSize * currentGridSize) {
        setGridSize(
          loadedCameras.length > 9 ? 4 :
          loadedCameras.length > 4 ? 3 :
          loadedCameras.length > 1 ? 2 : 1
        )
      }
    }).catch(() => {})
  }, [backendUrl, setCameras, setGridSize])

  // Poll camera status every 5 s so error/stopped cameras update without WebSocket
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const cams = await api.getCameras()
        cams.forEach((c) => updateCamera(c.id, { status: c.status, error_message: c.error_message }))
      } catch { /* noop */ }
    }, 5000)
    return () => clearInterval(id)
  }, [updateCamera])

  return (
    <TooltipProvider delayDuration={400}>
      <div className="flex flex-col h-screen bg-background overflow-hidden">
        {/* Top Bar */}
        <header className="h-12 flex items-center gap-3 px-3 border-b border-border/60 bg-card shrink-0">
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
                  ? 'text-foreground bg-secondary'
                  : 'text-destructive bg-destructive/10'
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

          <div className="rounded-md bg-secondary/60 px-2 py-1 text-[11px] text-muted-foreground">
            2 cameras per page
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
          <div
            className={`shrink-0 overflow-hidden transition-[width] duration-200 ease-out ${
              leftSidebarCollapsed ? 'w-10' : 'w-[280px]'
            }`}
          >
            {leftSidebarCollapsed ? (
              <div className="h-full bg-card border-r border-border/60 flex flex-col items-center py-2 gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      onClick={() => setLeftSidebarCollapsed(false)}
                      className="w-7 h-7 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                      aria-label="Expand camera panel"
                    >
                      <PanelLeftOpen className="w-4 h-4" />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="right">Expand camera panel</TooltipContent>
                </Tooltip>
                <div className="w-5 h-px bg-border/60" />
                <Camera className="w-4 h-4 text-muted-foreground" />
                <span className="text-[10px] tabular-nums text-muted-foreground [writing-mode:vertical-rl] rotate-180">
                  {cameras.filter((camera) => camera.status === 'live').length}/{cameras.length} live
                </span>
              </div>
            ) : (
              <LeftSidebar />
            )}
          </div>

          {/* Center: Camera Grid */}
          <main className="flex-1 overflow-hidden bg-background">
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
