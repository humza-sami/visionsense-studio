import { useState } from 'react'
import { LoaderCircle, Plus } from 'lucide-react'
import { useStore } from '@/store/useStore'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import * as api from '@/lib/api'
import type { CameraSourceType } from '@/types'

const DEFAULT_PIPELINE: import('@/types').PipelineConfig = {
  model: 'yolov8n.pt',
  task: 'detect',
  open_vocab_prompt: [],
  tracking: { enabled: false, tracker: 'bytetrack' },
  thresholds: { confidence: 0.5, iou: 0.45 },
  features: { boxes: false, masks: false, keypoints: false, labels: false, trails: false, obb: false, semantic: false },
  applications: [],
  frame_skip: 1,
}

function channelTemplate(url: string): string | null {
  if (!/^rtsp:\/\//i.test(url) || !/[?&]channel=\d+/i.test(url)) return null
  return url.replace(/([?&]channel=)\d+/i, '$1{channel}')
}

function channelUrl(template: string, channel: number): string {
  return template.replace('{channel}', String(channel))
}

function withSubtype(url: string, subtype: string): string {
  if (/([?&]subtype=)\d+/i.test(url)) {
    return url.replace(/([?&]subtype=)\d+/i, `$1${subtype}`)
  }
  return `${url}${url.includes('?') ? '&' : '?'}subtype=${subtype}`
}

export function AddCameraDialog({ trigger }: { trigger?: React.ReactNode }) {
  const { addCamera } = useStore()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [sourceType, setSourceType] = useState<CameraSourceType>('rtsp')
  const [url, setUrl] = useState('')
  const [rangeStart, setRangeStart] = useState('1')
  const [rangeEnd, setRangeEnd] = useState('16')
  const [streamSubtype, setStreamSubtype] = useState('1')
  const [deviceIndex, setDeviceIndex] = useState('0')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [progressLabel, setProgressLabel] = useState('')
  const [progressValue, setProgressValue] = useState(0)

  async function handleAdd() {
    if (!name || (sourceType === 'rtsp' && !url)) return
    setLoading(true)
    setError('')
    const firstChannel = Math.max(1, parseInt(rangeStart) || 1)
    const lastChannel = Math.min(64, Math.max(firstChannel, parseInt(rangeEnd) || 16))
    setProgressLabel(sourceType === 'rtsp' ? `Scanning channels ${firstChannel}–${lastChannel}…` : 'Adding camera…')
    setProgressValue(8)

    try {
      let sources: Array<{ name: string; source: import('@/types').CameraSource }>

      if (sourceType === 'rtsp') {
        const selectedUrl = withSubtype(url, streamSubtype)
        const template = channelTemplate(selectedUrl)
        let channels: number[] = []

        if (template) {
          try {
            const result = await api.probeChannels(
              template,
              firstChannel,
              lastChannel,
              undefined,
              undefined,
              parseInt(streamSubtype)
            )
            channels = result.alive
          } catch {
            // If discovery is unavailable, preserve the exact URL as one camera.
          }
        }

        sources = channels.length > 0 && template
          ? channels.map((channel) => ({
              name: `${name} - Channel ${channel}`,
              source: { type: 'rtsp', url: channelUrl(template, channel) },
            }))
          : [{ name, source: { type: 'rtsp', url: selectedUrl } }]
      } else {
        sources = [{
          name,
          source: { type: sourceType, device_index: parseInt(deviceIndex) },
        }]
      }

      setProgressValue(15)
      for (let index = 0; index < sources.length; index += 1) {
        const camera = sources[index]
        setProgressLabel(`Adding camera ${index + 1} of ${sources.length}…`)
        const created = await api.createCamera({ ...camera, pipeline: DEFAULT_PIPELINE })
        addCamera(created)
        setProgressValue(15 + Math.round(((index + 1) / sources.length) * 85))

      }

      setOpen(false)
      setName('')
      setUrl('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not add camera')
    } finally {
      setLoading(false)
      setProgressLabel('')
      setProgressValue(0)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => {
      if (!loading) setOpen(nextOpen)
    }}>
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
              <p className="text-[11px] text-muted-foreground">
                Choose the range that matches your NVR. Up to 64 channels can be scanned.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label htmlFor="channel-from">From channel</Label>
                  <Input
                    id="channel-from"
                    type="number"
                    min="1"
                    max="64"
                    value={rangeStart}
                    onChange={(e) => setRangeStart(e.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="channel-to">To channel</Label>
                  <Input
                    id="channel-to"
                    type="number"
                    min="1"
                    max="64"
                    value={rangeEnd}
                    onChange={(e) => setRangeEnd(e.target.value)}
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <Label>Stream quality</Label>
                <Select value={streamSubtype} onValueChange={setStreamSubtype}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1">Sub stream — recommended for multi-camera</SelectItem>
                    <SelectItem value="0">Main stream — HD, higher CPU usage</SelectItem>
                  </SelectContent>
                </Select>
              </div>
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
          {loading && (
            <div className="space-y-2 rounded-lg border border-border/60 bg-secondary/20 p-3">
              <div className="flex items-center gap-2 text-sm">
                <LoaderCircle className="h-4 w-4 animate-spin text-primary" />
                <span>{progressLabel}</span>
              </div>
              <Progress value={progressValue} />
              <p className="text-[11px] text-muted-foreground">
                Cameras will appear in the dashboard as they are added.
              </p>
            </div>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)} disabled={loading}>Cancel</Button>
          <Button onClick={handleAdd} disabled={!name || (sourceType === 'rtsp' && !url) || loading}>
            {loading ? progressLabel : 'Add Camera'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
