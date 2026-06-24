import { useState, useEffect } from 'react'
import {
  Camera, Activity, Users2, BellRing, SlidersHorizontal,
  Image, Circle, Trash2, Download, Video
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { CameraCard } from '@/components/cameras/CameraCard'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { formatMs, formatTimestamp } from '@/lib/utils'
import * as api from '@/lib/api'

const ALERT_COLORS: Record<string, string> = {
  intrusion: 'text-red-400 bg-red-500/10 border-red-500/20',
  speed: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  ppe: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  default: 'text-muted-foreground bg-secondary/50 border-border/40',
}

export function LeftSidebar() {
  const {
    cameras, selectedCameraId, telemetry, alerts, clearAlerts,
    selectCamera, updateCamera, removeCamera,
  } = useStore()

  const [models, setModels] = useState<string[]>(['yolov8n.pt', 'yolov8s.pt', 'yolov8m.pt'])
  const selectedCamera = cameras.find((c) => c.id === selectedCameraId)
  const camTelemetry = selectedCameraId ? telemetry[selectedCameraId] : null

  // Aggregate counts across all live cameras
  const aggregateCounts: Record<string, number> = {}
  cameras.forEach((cam) => {
    const t = telemetry[cam.id]
    if (t) {
      Object.entries(t.counts).forEach(([label, count]) => {
        aggregateCounts[label] = (aggregateCounts[label] ?? 0) + count
      })
    }
  })

  useEffect(() => {
    api.getModels().then(setModels).catch(() => {})
  }, [])

  async function updateThreshold(key: 'confidence' | 'iou', value: number) {
    if (!selectedCamera) return
    const newThresholds = { ...selectedCamera.pipeline.thresholds, [key]: value }
    updateCamera(selectedCamera.id, { pipeline: { ...selectedCamera.pipeline, thresholds: newThresholds } })
    try {
      await api.updatePipeline(selectedCamera.id, { thresholds: newThresholds })
    } catch { /* noop */ }
  }

  async function updateModel(model: string) {
    if (!selectedCamera) return
    updateCamera(selectedCamera.id, { pipeline: { ...selectedCamera.pipeline, model } })
    try {
      await api.updatePipeline(selectedCamera.id, { model })
    } catch { /* noop */ }
  }

  return (
    <div className="flex flex-col h-full bg-[#111118] border-r border-border/60 overflow-hidden">
      <ScrollArea className="flex-1 scrollbar-thin">
        <div className="p-3 space-y-4">

          {/* Section: Cameras */}
          <SidebarSection icon={<Camera className="w-3.5 h-3.5" />} title="CAMERAS" count={cameras.length}>
            {cameras.length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-2">No cameras added</p>
            ) : (
              <div className="space-y-0.5">
                {cameras.map((cam) => (
                  <CameraCard
                    key={cam.id}
                    camera={cam}
                    isSelected={selectedCameraId === cam.id}
                    onClick={() => selectCamera(cam.id === selectedCameraId ? null : cam.id)}
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
                  className="h-full bg-indigo-500 rounded-full transition-all duration-500"
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

          {/* Section: Live Counts */}
          <SidebarSection icon={<Users2 className="w-3.5 h-3.5" />} title="LIVE COUNTS">
            {Object.keys(aggregateCounts).length === 0 ? (
              <p className="text-xs text-muted-foreground px-2 py-2">No detections yet</p>
            ) : (
              <div className="space-y-1.5">
                {Object.entries(aggregateCounts).map(([label, count]) => (
                  <div key={label} className="flex items-center justify-between px-2 py-1 rounded bg-secondary/30">
                    <span className="text-xs text-foreground/80 capitalize">{label}</span>
                    <Badge variant="indigo" className="text-xs font-mono tabular-nums h-5">
                      {count}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
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

          {/* Section: Global Controls */}
          <SidebarSection icon={<SlidersHorizontal className="w-3.5 h-3.5" />} title="CONTROLS">
            <div className="space-y-4 px-1">
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">Confidence</span>
                  <span className="tabular-nums text-foreground/80">
                    {selectedCamera ? (selectedCamera.pipeline.thresholds.confidence * 100).toFixed(0) : '—'}%
                  </span>
                </div>
                <Slider
                  min={0}
                  max={100}
                  step={1}
                  value={[Math.round((selectedCamera?.pipeline.thresholds.confidence ?? 0.5) * 100)]}
                  onValueChange={([v]) => updateThreshold('confidence', v / 100)}
                  disabled={!selectedCamera}
                />
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">IoU Threshold</span>
                  <span className="tabular-nums text-foreground/80">
                    {selectedCamera ? (selectedCamera.pipeline.thresholds.iou * 100).toFixed(0) : '—'}%
                  </span>
                </div>
                <Slider
                  min={0}
                  max={100}
                  step={1}
                  value={[Math.round((selectedCamera?.pipeline.thresholds.iou ?? 0.45) * 100)]}
                  onValueChange={([v]) => updateThreshold('iou', v / 100)}
                  disabled={!selectedCamera}
                />
              </div>
              <div className="space-y-1.5">
                <span className="text-xs text-muted-foreground">AI Model</span>
                <Select
                  value={selectedCamera?.pipeline.model ?? ''}
                  onValueChange={updateModel}
                  disabled={!selectedCamera}
                >
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {models.map((m) => (
                      <SelectItem key={m} value={m}>{m}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
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
                  className="gap-1.5 text-xs h-8 col-span-2 border-red-500/30 hover:bg-red-500/10 hover:text-red-400"
                  onClick={async () => {
                    try {
                      await api.deleteCamera(selectedCamera.id)
                    } catch { /* noop */ }
                    removeCamera(selectedCamera.id)
                  }}
                >
                  <Trash2 className="w-3.5 h-3.5 text-red-400" /> Remove Camera
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
    good: 'text-green-400',
    warn: 'text-amber-400',
    bad: 'text-red-400',
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
