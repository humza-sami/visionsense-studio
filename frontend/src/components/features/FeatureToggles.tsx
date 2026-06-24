import { useStore } from '@/store/useStore'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import * as api from '@/lib/api'
import type { Camera, PipelineFeatures } from '@/types'
import {
  Box, Layers, PersonStanding, RotateCw, Grid3X3, Palette, Navigation2
} from 'lucide-react'

interface FeatureItem {
  key: keyof PipelineFeatures
  label: string
  icon: React.ReactNode
  description: string
}

const FEATURES: FeatureItem[] = [
  { key: 'boxes', label: 'Detect', icon: <Box className="w-4 h-4" />, description: 'Bounding boxes' },
  { key: 'masks', label: 'Segment', icon: <Layers className="w-4 h-4" />, description: 'Instance masks' },
  { key: 'keypoints', label: 'Pose', icon: <PersonStanding className="w-4 h-4" />, description: 'Skeleton estimation' },
  { key: 'obb', label: 'OBB', icon: <RotateCw className="w-4 h-4" />, description: 'Oriented boxes' },
  { key: 'semantic', label: 'Semantic', icon: <Grid3X3 className="w-4 h-4" />, description: 'Pixel segmentation' },
  { key: 'labels', label: 'Labels', icon: <Palette className="w-4 h-4" />, description: 'Class labels' },
  { key: 'trails', label: 'Trails', icon: <Navigation2 className="w-4 h-4" />, description: 'Motion trails' },
]

async function doToggleFeature(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  key: keyof PipelineFeatures,
  value: boolean
) {
  const { features } = cam.pipeline
  const newFeatures = { ...features, [key]: value }
  updateCamera(cam.id, { pipeline: { ...cam.pipeline, features: newFeatures } })
  try {
    await api.updatePipeline(cam.id, { features: newFeatures })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, features } })
  }
}

async function doToggleTracking(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  enabled: boolean
) {
  const { tracking } = cam.pipeline
  const newTracking = { ...tracking, enabled }
  updateCamera(cam.id, { pipeline: { ...cam.pipeline, tracking: newTracking } })
  try {
    await api.updatePipeline(cam.id, { tracking: newTracking })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, tracking } })
  }
}

async function doSetTracker(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  tracker: string
) {
  const { tracking } = cam.pipeline
  const newTracking = { ...tracking, tracker }
  updateCamera(cam.id, { pipeline: { ...cam.pipeline, tracking: newTracking } })
  try {
    await api.updatePipeline(cam.id, { tracking: newTracking })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, tracking } })
  }
}

export function FeatureToggles() {
  const { selectedCameraId, cameras, updateCamera } = useStore()
  const camera = cameras.find((c) => c.id === selectedCameraId)

  if (!camera) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4">
        Select a camera to configure features
      </div>
    )
  }

  const { features, tracking } = camera.pipeline

  return (
    <div className="space-y-1">
      {FEATURES.map((feat) => (
        <div
          key={feat.key}
          className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-secondary/50 transition-colors group"
        >
          <div className={`w-7 h-7 rounded-md flex items-center justify-center transition-colors ${
            features[feat.key]
              ? 'bg-indigo-500/20 text-indigo-400'
              : 'bg-secondary/60 text-muted-foreground'
          }`}>
            {feat.icon}
          </div>
          <div className="flex-1 min-w-0">
            <Label className="text-sm font-medium cursor-pointer">{feat.label}</Label>
            <p className="text-xs text-muted-foreground">{feat.description}</p>
          </div>
          <Switch
            checked={features[feat.key]}
            onCheckedChange={(v) => void doToggleFeature(camera, updateCamera, feat.key, v)}
          />
        </div>
      ))}

      {/* Tracking toggle */}
      <div className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-secondary/50 transition-colors mt-1">
        <div className={`w-7 h-7 rounded-md flex items-center justify-center transition-colors ${
          tracking.enabled
            ? 'bg-indigo-500/20 text-indigo-400'
            : 'bg-secondary/60 text-muted-foreground'
        }`}>
          <Navigation2 className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <Label className="text-sm font-medium cursor-pointer">Track</Label>
          <p className="text-xs text-muted-foreground">Object tracking</p>
        </div>
        <Switch
          checked={tracking.enabled}
          onCheckedChange={(v) => void doToggleTracking(camera, updateCamera, v)}
        />
      </div>

      {tracking.enabled && (
        <div className="px-2 py-1.5">
          <Label className="text-xs text-muted-foreground mb-1.5 block">Tracker Algorithm</Label>
          <Select
            value={tracking.tracker}
            onValueChange={(v) => void doSetTracker(camera, updateCamera, v)}
          >
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="bytetrack">ByteTrack</SelectItem>
              <SelectItem value="botsort">BoT-SORT</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  )
}
