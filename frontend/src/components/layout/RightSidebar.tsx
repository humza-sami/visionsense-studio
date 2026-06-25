import { useState, useMemo } from 'react'
import {
  SlidersHorizontal, Cpu, Layers3, Search, ChevronDown, ChevronRight, X,
  Box, Layers, PersonStanding, RotateCw, Grid3X3, Navigation2,
  Users, ArrowLeftRight, UserCheck, Smartphone, HardHat,
  Flame, ShieldAlert, EyeOff, Gauge,
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Separator } from '@/components/ui/separator'
import * as api from '@/lib/api'
import type { Camera, PipelineFeatures, ApplicationConfig } from '@/types'

// ── Model sizes ───────────────────────────────────────────────────────────────

const MODEL_SIZES = [
  { id: 'yolo26n', label: 'N' },
  { id: 'yolo26s', label: 'S' },
  { id: 'yolo26m', label: 'M' },
  { id: 'yolo26l', label: 'L' },
  { id: 'yolo26x', label: 'X' },
]

// ── Detection modes (mutually exclusive) ─────────────────────────────────────

const MODES = [
  { value: 'none',     label: 'None',     icon: null,                                    sets: {} },
  { value: 'detect',   label: 'Detect',   icon: <Box className="w-3.5 h-3.5" />,         sets: { boxes: true } },
  { value: 'segment',  label: 'Segment',  icon: <Layers className="w-3.5 h-3.5" />,      sets: { masks: true } },
  { value: 'pose',     label: 'Pose',     icon: <PersonStanding className="w-3.5 h-3.5" />, sets: { keypoints: true } },
  { value: 'obb',      label: 'OBB',      icon: <RotateCw className="w-3.5 h-3.5" />,    sets: { obb: true } },
  { value: 'semantic', label: 'Semantic', icon: <Grid3X3 className="w-3.5 h-3.5" />,     sets: { semantic: true } },
] as const

type ModeValue = typeof MODES[number]['value']

function getActiveMode(f: PipelineFeatures): ModeValue {
  if (f.keypoints) return 'pose'
  if (f.masks)     return 'segment'
  if (f.obb)       return 'obb'
  if (f.semantic)  return 'semantic'
  if (f.boxes)     return 'detect'
  return 'none'
}

// ── Applications ──────────────────────────────────────────────────────────────

const APP_DEFS = [
  { type: 'head_count',       label: 'Head Count',       icon: <Users className="w-3.5 h-3.5" />,         description: 'Count persons in frame' },
  { type: 'customer_in_out',  label: 'Customer In/Out',  icon: <ArrowLeftRight className="w-3.5 h-3.5" />, description: 'Line-crossing counter' },
  { type: 'manager_presence', label: 'Manager Presence', icon: <UserCheck className="w-3.5 h-3.5" />,      description: 'Detect person in seat' },
  { type: 'mobile_usage',     label: 'Mobile Usage',     icon: <Smartphone className="w-3.5 h-3.5" />,     description: 'Phone usage detection' },
  { type: 'ppe_safety',       label: 'PPE / Safety',     icon: <HardHat className="w-3.5 h-3.5" />,        description: 'Safety equipment check' },
  { type: 'heatmap',          label: 'Heatmap',          icon: <Flame className="w-3.5 h-3.5" />,          description: 'Foot traffic heatmap' },
  { type: 'intrusion',        label: 'Intrusion Alarm',  icon: <ShieldAlert className="w-3.5 h-3.5" />,    description: 'Zone alert system' },
  { type: 'privacy_blur',     label: 'Privacy Blur',     icon: <EyeOff className="w-3.5 h-3.5" />,         description: 'Face / person blur' },
  { type: 'speed_estimation', label: 'Speed Estimation', icon: <Gauge className="w-3.5 h-3.5" />,          description: 'Object speed tracking' },
]

// ── COCO 80 class names ───────────────────────────────────────────────────────

const COCO_CLASSES = [
  'airplane','apple','backpack','banana','baseball bat','baseball glove','bear',
  'bed','bench','bicycle','bird','boat','book','bottle','bowl','broccoli','bus',
  'cake','car','carrot','cat','cell phone','chair','clock','couch','cow','cup',
  'dining table','dog','donut','elephant','fire hydrant','fork','frisbee',
  'giraffe','hair drier','handbag','horse','hot dog','keyboard','kite','knife',
  'laptop','microwave','motorcycle','mouse','orange','oven','parking meter',
  'person','pizza','potted plant','refrigerator','remote','sandwich','scissors',
  'sheep','sink','skateboard','skis','snowboard','spoon','sports ball',
  'stop sign','suitcase','surfboard','teddy bear','tennis racket','tie',
  'toaster','toilet','toothbrush','traffic light','train','truck','tv',
  'umbrella','vase','wine glass','zebra',
]

// ── Section wrapper ───────────────────────────────────────────────────────────

function Section({
  icon, title, children, collapsible = false,
}: {
  icon: React.ReactNode
  title: string
  children: React.ReactNode
  collapsible?: boolean
}) {
  const [open, setOpen] = useState(true)
  return (
    <div className="space-y-2">
      <button
        type="button"
        className="flex items-center gap-2 px-1 w-full group"
        onClick={() => collapsible && setOpen((o) => !o)}
      >
        <span className="text-muted-foreground">{icon}</span>
        <span className="text-[10px] font-semibold text-muted-foreground tracking-wider flex-1 text-left">{title}</span>
        {collapsible && (
          open
            ? <ChevronDown className="w-3 h-3 text-muted-foreground" />
            : <ChevronRight className="w-3 h-3 text-muted-foreground" />
        )}
      </button>
      {open && children}
    </div>
  )
}

// ── API helpers ───────────────────────────────────────────────────────────────

async function patchPipeline(cam: Camera, updateCamera: (id: string, u: Partial<Camera>) => void, patch: Partial<Camera['pipeline']>) {
  const next = { ...cam.pipeline, ...patch }
  updateCamera(cam.id, { pipeline: next })
  try {
    await api.updatePipeline(cam.id, patch)
  } catch {
    updateCamera(cam.id, { pipeline: cam.pipeline })
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export function RightSidebar() {
  const { selectedCameraId, cameras, updateCamera, classFilters, setClassFilter } = useStore()
  const cam = cameras.find((c) => c.id === selectedCameraId)
  const [classSearch, setClassSearch] = useState('')

  const activeFilter = cam ? (classFilters[cam.id] ?? []) : []

  const filteredClasses = useMemo(() => {
    if (!classSearch.trim()) return COCO_CLASSES
    const q = classSearch.toLowerCase()
    return COCO_CLASSES.filter((c) => c.includes(q))
  }, [classSearch])

  const placeholder = cam ? null : (
    <p className="text-xs text-muted-foreground text-center py-6">Select a camera to configure</p>
  )

  // ── Control helpers ────────────────────────────────────────────────────────

  function updateThreshold(key: 'confidence' | 'iou', value: number) {
    if (!cam) return
    updateCamera(cam.id, {
      pipeline: {
        ...cam.pipeline,
        thresholds: { ...cam.pipeline.thresholds, [key]: value },
      },
    })
  }

  function updateModel(id: string) {
    if (!cam) return
    void patchPipeline(cam, updateCamera, { model: id })
  }

  // ── Feature helpers ────────────────────────────────────────────────────────

  function setMode(mode: ModeValue) {
    if (!cam) return
    const base: PipelineFeatures = {
      boxes: false, masks: false, keypoints: false,
      obb: false, semantic: false,
      labels: cam.pipeline.features.labels,
      trails: cam.pipeline.features.trails,
    }
    if (mode !== 'none') {
      const m = MODES.find((m) => m.value === mode)
      Object.assign(base, m?.sets ?? {})
    }
    void patchPipeline(cam, updateCamera, { features: base })
  }

  function toggleDisplay(key: 'labels' | 'trails') {
    if (!cam) return
    const features = { ...cam.pipeline.features, [key]: !cam.pipeline.features[key] }
    void patchPipeline(cam, updateCamera, { features })
  }

  function toggleTracking(enabled: boolean) {
    if (!cam) return
    void patchPipeline(cam, updateCamera, {
      tracking: { ...cam.pipeline.tracking, enabled },
    })
  }

  // ── App helpers ────────────────────────────────────────────────────────────

  function toggleApp(type: string, enabled: boolean) {
    if (!cam) return
    const apps = cam.pipeline.applications
    let next: ApplicationConfig[]
    const existing = apps.find((a) => a.type === type)
    if (existing) {
      next = apps.map((a) => a.type === type ? { ...a, enabled } : a)
    } else {
      next = [...apps, { type, enabled, config: {} }]
    }
    void patchPipeline(cam, updateCamera, { applications: next })
  }

  function isAppEnabled(type: string) {
    return cam?.pipeline.applications.some((a) => a.type === type && a.enabled) ?? false
  }

  // ── Class filter helpers ───────────────────────────────────────────────────

  function addClassFilter(cls: string) {
    if (!cam || activeFilter.includes(cls)) return
    setClassFilter(cam.id, [...activeFilter, cls])
    setClassSearch('')
  }

  function removeClassFilter(cls: string) {
    if (!cam) return
    setClassFilter(cam.id, activeFilter.filter((c) => c !== cls))
  }

  // ── Derived values ─────────────────────────────────────────────────────────

  const activeMode = cam ? getActiveMode(cam.pipeline.features) : 'none'
  const activeModelId = cam?.pipeline.model
    ?.replace(/-(pose|seg|obb|cls)(\.pt)?$/, '')
    ?.replace(/\.pt$/, '') ?? 'yolo26n'

  return (
    <div className="flex flex-col h-full bg-card border-l border-border/60 overflow-hidden">
      <ScrollArea className="flex-1 scrollbar-thin">
        <div className="p-3 space-y-4">

          {/* ── Controls ───────────────────────────────────────────────────── */}
          <Section icon={<SlidersHorizontal className="w-3.5 h-3.5" />} title="CONTROLS">
            {placeholder ?? (
              <div className="space-y-4 px-1">
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">Confidence</span>
                    <span className="tabular-nums">{((cam!.pipeline.thresholds.confidence) * 100).toFixed(0)}%</span>
                  </div>
                  <Slider min={0} max={100} step={1}
                    value={[Math.round(cam!.pipeline.thresholds.confidence * 100)]}
                    onValueChange={([v]) => updateThreshold('confidence', v / 100)}
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-muted-foreground">IoU Threshold</span>
                    <span className="tabular-nums">{((cam!.pipeline.thresholds.iou) * 100).toFixed(0)}%</span>
                  </div>
                  <Slider min={0} max={100} step={1}
                    value={[Math.round(cam!.pipeline.thresholds.iou * 100)]}
                    onValueChange={([v]) => updateThreshold('iou', v / 100)}
                  />
                </div>
                <div className="space-y-1.5">
                  <span className="text-xs text-muted-foreground">Model Size</span>
                  <div className="flex gap-1">
                    {MODEL_SIZES.map(({ id, label }) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => updateModel(id)}
                        className={`flex-1 h-7 rounded text-xs font-semibold transition-colors ${
                          activeModelId === id
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-secondary text-muted-foreground hover:text-foreground hover:bg-secondary/80'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </Section>

          <Separator className="opacity-40" />

          {/* ── Feature ────────────────────────────────────────────────────── */}
          <Section icon={<Cpu className="w-3.5 h-3.5" />} title="FEATURE">
            {placeholder ?? (
              <div className="space-y-3 px-1">
                {/* Mode dropdown */}
                <Select value={activeMode} onValueChange={(v) => setMode(v as ModeValue)}>
                  <SelectTrigger className="h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {MODES.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        <span className="flex items-center gap-2">
                          {m.icon}
                          {m.label}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                {/* Display options */}
                <div className="flex items-center gap-2 flex-wrap">
                  {(['labels', 'trails'] as const).map((key) => {
                    const active = cam!.pipeline.features[key]
                    return (
                      <button
                        key={key}
                        type="button"
                        onClick={() => toggleDisplay(key)}
                        className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors capitalize ${
                          active
                            ? 'bg-primary/15 text-primary border border-primary/30'
                            : 'bg-secondary text-muted-foreground border border-transparent hover:border-border'
                        }`}
                      >
                        {key}
                      </button>
                    )
                  })}
                  <button
                    type="button"
                    onClick={() => toggleTracking(!cam!.pipeline.tracking.enabled)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                      cam!.pipeline.tracking.enabled
                        ? 'bg-primary/15 text-primary border border-primary/30'
                        : 'bg-secondary text-muted-foreground border border-transparent hover:border-border'
                    }`}
                  >
                    <Navigation2 className="w-3 h-3 inline mr-1" />
                    Track
                  </button>
                </div>
              </div>
            )}
          </Section>

          <Separator className="opacity-40" />

          {/* ── Applications ───────────────────────────────────────────────── */}
          <Section icon={<Layers3 className="w-3.5 h-3.5" />} title="APPLICATIONS" collapsible>
            {placeholder ?? (
              <div className="space-y-0.5 px-1">
                {APP_DEFS.map((app) => {
                  const enabled = isAppEnabled(app.type)
                  return (
                    <div
                      key={app.type}
                      className="flex items-center gap-2.5 py-1.5 px-1 rounded hover:bg-secondary/50 transition-colors"
                    >
                      <span className={`shrink-0 ${enabled ? 'text-foreground' : 'text-muted-foreground'}`}>
                        {app.icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-medium leading-none">{app.label}</p>
                        <p className="text-[10px] text-muted-foreground mt-0.5 leading-none">{app.description}</p>
                      </div>
                      <Switch
                        checked={enabled}
                        onCheckedChange={(v) => toggleApp(app.type, v)}
                        className="shrink-0 scale-75"
                      />
                    </div>
                  )
                })}
              </div>
            )}
          </Section>

          <Separator className="opacity-40" />

          {/* ── Class Filter ───────────────────────────────────────────────── */}
          <Section icon={<Search className="w-3.5 h-3.5" />} title="CLASS FILTER">
            {placeholder ?? (
              <div className="space-y-2 px-1">
                {/* Active filter tags */}
                {activeFilter.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {activeFilter.map((cls) => (
                      <button
                        key={cls}
                        type="button"
                        onClick={() => removeClassFilter(cls)}
                        className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/10 border border-primary/20 text-xs text-primary hover:bg-destructive/10 hover:border-destructive/20 hover:text-destructive transition-colors"
                      >
                        {cls}
                        <X className="w-2.5 h-2.5" />
                      </button>
                    ))}
                    <button
                      type="button"
                      onClick={() => cam && setClassFilter(cam.id, [])}
                      className="text-[10px] text-muted-foreground hover:text-foreground px-1 transition-colors"
                    >
                      clear all
                    </button>
                  </div>
                )}

                {/* Search input */}
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground pointer-events-none" />
                  <Input
                    placeholder="Search YOLO classes..."
                    value={classSearch}
                    onChange={(e) => setClassSearch(e.target.value)}
                    className="h-8 pl-7 text-xs"
                  />
                </div>

                {/* Class list (shows when searching or always shows top matches) */}
                {(classSearch || activeFilter.length === 0) && (
                  <div className="max-h-36 overflow-y-auto rounded-md border border-border/50 bg-secondary/20">
                    {filteredClasses.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-3">No classes match</p>
                    ) : (
                      filteredClasses.slice(0, 30).map((cls) => {
                        const selected = activeFilter.includes(cls)
                        return (
                          <button
                            key={cls}
                            type="button"
                            onClick={() => selected ? removeClassFilter(cls) : addClassFilter(cls)}
                            className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center justify-between ${
                              selected
                                ? 'bg-primary/10 text-primary'
                                : 'hover:bg-secondary/80 text-foreground'
                            }`}
                          >
                            {cls}
                            {selected && <X className="w-3 h-3 shrink-0" />}
                          </button>
                        )
                      })
                    )}
                  </div>
                )}

                <p className="text-[10px] text-muted-foreground">
                  {activeFilter.length === 0
                    ? 'Showing all classes. Select to filter.'
                    : `Filtering to ${activeFilter.length} class${activeFilter.length > 1 ? 'es' : ''}.`}
                </p>
              </div>
            )}
          </Section>

        </div>
      </ScrollArea>
    </div>
  )
}
