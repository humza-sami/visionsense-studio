import { useState } from 'react'
import { Plus } from 'lucide-react'
import { useStore } from '@/store/useStore'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import * as api from '@/lib/api'
import type { CameraSourceType } from '@/types'

const DEFAULT_PIPELINE: import('@/types').PipelineConfig = {
  model: 'yolov8n.pt',
  task: 'detect',
  open_vocab_prompt: [],
  tracking: { enabled: false, tracker: 'bytetrack' },
  thresholds: { confidence: 0.5, iou: 0.45 },
  features: { boxes: true, masks: false, keypoints: false, labels: true, trails: false, obb: false, semantic: false },
  applications: [],
  frame_skip: 0,
}

export function AddCameraDialog({ trigger }: { trigger?: React.ReactNode }) {
  const { addCamera } = useStore()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [sourceType, setSourceType] = useState<CameraSourceType>('rtsp')
  const [url, setUrl] = useState('')
  const [deviceIndex, setDeviceIndex] = useState('0')
  const [loading, setLoading] = useState(false)

  async function handleAdd() {
    if (!name) return
    setLoading(true)
    const source =
      sourceType === 'rtsp'
        ? { type: sourceType, url }
        : { type: sourceType, device_index: parseInt(deviceIndex) }

    try {
      const cam = await api.createCamera({ name, source, pipeline: DEFAULT_PIPELINE })
      addCamera(cam)
    } catch {
      addCamera({
        id: Math.random().toString(36).slice(2),
        name,
        source,
        status: 'idle',
        pipeline: DEFAULT_PIPELINE,
      })
    } finally {
      setLoading(false)
      setOpen(false)
      setName('')
      setUrl('')
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button size="sm" variant="outline" className="gap-1.5">
            <Plus className="w-4 h-4" /> Add Camera
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Add Camera</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label htmlFor="cam-name">Camera Name</Label>
            <Input
              id="cam-name"
              placeholder="e.g. Entrance Camera"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>Source Type</Label>
            <Select value={sourceType} onValueChange={(v) => setSourceType(v as CameraSourceType)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="rtsp">RTSP Network Camera</SelectItem>
                <SelectItem value="webcam">Webcam</SelectItem>
                <SelectItem value="usb">USB Camera</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {sourceType === 'rtsp' ? (
            <div className="space-y-2">
              <Label htmlFor="rtsp-url">RTSP URL</Label>
              <Input
                id="rtsp-url"
                placeholder="rtsp://user:pass@192.168.1.100:554/stream"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </div>
          ) : (
            <div className="space-y-2">
              <Label htmlFor="device-index">Device Index</Label>
              <Input
                id="device-index"
                type="number"
                min="0"
                value={deviceIndex}
                onChange={(e) => setDeviceIndex(e.target.value)}
              />
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
          <Button onClick={handleAdd} disabled={!name || loading}>
            {loading ? 'Adding...' : 'Add Camera'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
