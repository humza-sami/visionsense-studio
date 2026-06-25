import {
  Camera, Activity, BellRing,
  Image, Circle, Trash2, Download, Video, PanelLeftClose
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { CameraCard } from '@/components/cameras/CameraCard'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { formatMs, formatTimestamp } from '@/lib/utils'
import * as api from '@/lib/api'

const ALERT_COLORS: Record<string, string> = {
  intrusion: 'text-destructive bg-destructive/10 border-destructive/20',
  default: 'text-muted-foreground bg-secondary/50 border-border/40',
}

export function LeftSidebar() {
  const {
    cameras, selectedCameraId, telemetry, alerts, clearAlerts,
    selectCamera, removeCamera, setLeftSidebarCollapsed, setCameraPage,
  } = useStore()

  const selectedCamera = cameras.find((c) => c.id === selectedCameraId)
  const camTelemetry = selectedCameraId ? telemetry[selectedCameraId] : null

  const aggregateCounts: Record<string, number> = {}
  cameras.forEach((cam) => {
    const t = telemetry[cam.id]
    if (t) {
      Object.entries(t.counts).forEach(([label, count]) => {
        aggregateCounts[label] = (aggregateCounts[label] ?? 0) + count
      })
    }
  })

  return (
    <div className="flex flex-col h-full bg-card border-r border-border/60 overflow-hidden">
      <ScrollArea className="flex-1 scrollbar-thin">
        <div className="p-3 space-y-4">

          {/* Section: Cameras */}
          <SidebarSection
            icon={<Camera className="w-3.5 h-3.5" />}
            title="CAMERAS"
            count={cameras.length}
            action={
              <button
                type="button"
                onClick={() => setLeftSidebarCollapsed(true)}
                className="w-6 h-6 rounded-md flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-secondary transition-colors"
                title="Collapse camera panel"
                aria-label="Collapse camera panel"
              >
                <PanelLeftClose className="w-3.5 h-3.5" />
              </button>
            }
          >
            {cameras.length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-2">No cameras added</p>
            ) : (
              <div className="space-y-0.5">
                {cameras.map((cam) => (
                  <CameraCard
                    key={cam.id}
                    camera={cam}
                    isSelected={selectedCameraId === cam.id}
                    onClick={() => {
                      setCameraPage(Math.floor(cameras.findIndex((camera) => camera.id === cam.id) / 2))
                      selectCamera(cam.id === selectedCameraId ? null : cam.id)
                    }}
                  />
                ))}
              </div>
            )}
          </SidebarSection>

          <Separator className="opacity-40" />

          {/* Section: System Health */}
          <SidebarSection icon={<Activity className="w-3.5 h-3.5" />} title="SYSTEM HEALTH">
            <div className="grid grid-cols-2 gap-2">
              <MetricCard
                label="FPS"
                value={camTelemetry ? camTelemetry.fps.toFixed(1) : '—'}
                unit="fps"
                status={camTelemetry ? (camTelemetry.fps >= 20 ? 'good' : camTelemetry.fps >= 10 ? 'warn' : 'bad') : 'idle'}
              />
              <MetricCard
                label="Inference"
                value={camTelemetry ? formatMs(camTelemetry.inference_ms) : '—'}
                status={camTelemetry ? (camTelemetry.inference_ms < 50 ? 'good' : camTelemetry.inference_ms < 100 ? 'warn' : 'bad') : 'idle'}
              />
            </div>
            <div className="mt-2 px-1">
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>Active Streams</span>
                <span className="tabular-nums">{cameras.filter((c) => c.status === 'live').length}/{cameras.length}</span>
              </div>
              <div className="h-1.5 bg-secondary/60 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{
                    width: cameras.length > 0
                      ? `${(cameras.filter((c) => c.status === 'live').length / cameras.length) * 100}%`
                      : '0%',
                  }}
                />
              </div>
            </div>
          </SidebarSection>

          <Separator className="opacity-40" />

          {/* Section: Alerts */}
          <SidebarSection
            icon={<BellRing className="w-3.5 h-3.5" />}
            title="LIVE ALERTS"
            count={alerts.length}
            action={
              alerts.length > 0 ? (
                <button onClick={clearAlerts} className="text-[10px] text-muted-foreground hover:text-foreground transition-colors">
                  Clear
                </button>
              ) : undefined
            }
          >
            <ScrollArea className="h-40">
              {alerts.length === 0 ? (
                <p className="text-xs text-muted-foreground px-2 py-2">No alerts</p>
              ) : (
                <div className="space-y-1.5 pr-2">
                  {alerts.slice(0, 20).map((alert) => {
                    const cam = cameras.find((c) => c.id === alert.cam_id)
                    const colorClass = ALERT_COLORS[alert.type] ?? ALERT_COLORS.default
                    return (
                      <div key={alert.id} className={`flex gap-2 p-2 rounded-md border text-xs ${colorClass}`}>
                        <Circle className="w-2 h-2 mt-0.5 fill-current shrink-0" />
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-medium capitalize">{alert.type}</span>
                            {cam && (
                              <span className="text-[10px] opacity-70">· {cam.name}</span>
                            )}
                          </div>
                          <p className="opacity-80 truncate">{alert.detail}</p>
                          <p className="text-[10px] opacity-50 mt-0.5">{formatTimestamp(alert.ts)}</p>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </ScrollArea>
          </SidebarSection>

          <Separator className="opacity-40" />

          {/* Section: Actions */}
          <SidebarSection icon={<Image className="w-3.5 h-3.5" />} title="ACTIONS">
            <div className="grid grid-cols-2 gap-2">
              <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" disabled={!selectedCamera}>
                <Image className="w-3.5 h-3.5" /> Snapshot
              </Button>
              <Button size="sm" variant="outline" className="gap-1.5 text-xs h-8" disabled={!selectedCamera}>
                <Video className="w-3.5 h-3.5" /> Record
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 text-xs h-8 col-span-2"
                disabled={Object.keys(aggregateCounts).length === 0}
                onClick={() => {
                  const data = JSON.stringify({ telemetry, timestamp: Date.now() }, null, 2)
                  const blob = new Blob([data], { type: 'application/json' })
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `visionsense-export-${Date.now()}.json`
                  a.click()
                  URL.revokeObjectURL(url)
                }}
              >
                <Download className="w-3.5 h-3.5" /> Export Data
              </Button>
              {selectedCamera && (
                <Button
                  size="sm"
                  variant="outline"
                  className="gap-1.5 text-xs h-8 col-span-2 border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                  onClick={async () => {
                    try {
                      await api.deleteCamera(selectedCamera.id)
                    } catch { /* noop */ }
                    removeCamera(selectedCamera.id)
                  }}
                >
                  <Trash2 className="w-3.5 h-3.5" /> Remove Camera
                </Button>
              )}
            </div>
          </SidebarSection>

        </div>
      </ScrollArea>
    </div>
  )
}

function SidebarSection({
  icon,
  title,
  count,
  action,
  children,
}: {
  icon: React.ReactNode
  title: string
  count?: number
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-[10px] font-semibold text-muted-foreground tracking-wider flex-1">{title}</span>
        {count !== undefined && count > 0 && (
          <Badge variant="secondary" className="h-4 text-[10px] px-1.5">{count}</Badge>
        )}
        {action}
      </div>
      {children}
    </div>
  )
}

function MetricCard({
  label,
  value,
  unit,
  status,
}: {
  label: string
  value: string
  unit?: string
  status: 'good' | 'warn' | 'bad' | 'idle'
}) {
  const statusColors = {
    good: 'text-foreground',
    warn: 'text-muted-foreground',
    bad: 'text-destructive',
    idle: 'text-muted-foreground',
  }

  return (
    <div className="bg-secondary/40 rounded-lg p-2.5 space-y-1">
      <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${statusColors[status]}`}>
        {value}
        {unit && <span className="text-xs font-normal text-muted-foreground ml-1">{unit}</span>}
      </p>
    </div>
  )
}
