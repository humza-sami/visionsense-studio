import { useState, useEffect } from 'react'
import { Wifi, Camera as CameraIcon, SkipForward, ChevronRight, ChevronLeft, Search, Check, Plus, Eye, EyeOff } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import * as api from '@/lib/api'
import type { Camera as CameraType, Device } from '@/types'
import logoUrl from '@/assets/logo.svg'

type SetupStep = 'choice' | 'rtsp' | 'webcam' | 'confirm'
type RtspMode  = 'paste' | 'fields'

interface PendingCamera {
  name: string
  source: CameraType['source']
}

const DEFAULT_PIPELINE: CameraType['pipeline'] = {
  model: 'yolov8n.pt',
  task: 'detect',
  open_vocab_prompt: [],
  tracking: { enabled: false, tracker: 'bytetrack' },
  thresholds: { confidence: 0.5, iou: 0.45 },
  features: { boxes: false, masks: false, keypoints: false, labels: false, trails: false, obb: false, semantic: false },
  applications: [],
  frame_skip: 1,
}

// Build RTSP URL from fields — matches common Dahua / Hikvision NVR format
function buildRtspUrl(ip: string, port: string, user: string, pass: string, channel: string | number, subtype = 0) {
  const encodedPass = encodeURIComponent(pass)
  return `rtsp://${user}:${encodedPass}@${ip}:${port}/cam/realmonitor?channel=${channel}&subtype=${subtype}`
}

export function SetupPage() {
  const { setAppPhase, addCamera, setGridSize, backendUrl } = useStore()
  const [step, setStep]     = useState<SetupStep>('choice')
  const [pending, setPending] = useState<PendingCamera[]>([])

  // ── RTSP ────────────────────────────────────────────────────────────────────
  const [rtspMode, setRtspMode]   = useState<RtspMode>('fields')

  // Paste-URL mode
  const [singleUrl, setSingleUrl]   = useState('')
  const [singleName, setSingleName] = useState('')
  const [addingPasteUrl, setAddingPasteUrl] = useState(false)

  // Fields mode
  const [ip, setIp]               = useState('')
  const [port, setPort]           = useState('554')
  const [user, setUser]           = useState('admin')
  const [pass, setPass]           = useState('')
  const [showPass, setShowPass]   = useState(false)
  const [rangeStart, setRangeStart] = useState('1')
  const [rangeEnd, setRangeEnd]   = useState('16')
  const [subtype, setSubtype]     = useState('1')

  // Probe results
  const [probing, setProbing]             = useState(false)
  const [probeResults, setProbeResults]   = useState<number[]>([])
  const [probeError, setProbeError]       = useState('')
  const [selectedChannels, setSelectedChannels] = useState<Set<number>>(new Set())

  // ── Webcam ──────────────────────────────────────────────────────────────────
  const [devices, setDevices]           = useState<Device[]>([])
  const [loadingDevices, setLoadingDevices] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)

  useEffect(() => { api.setBackendUrl(backendUrl) }, [backendUrl])

  // Live URL preview for fields mode
  const previewUrl = ip
    ? buildRtspUrl(ip, port, user, pass || '••••••', '{channel}', parseInt(subtype))
    : 'rtsp://admin:pass@192.168.1.100:554/cam/realmonitor?channel={channel}&subtype=0'

  async function handleProbe() {
    setProbing(true)
    setProbeResults([])
    setProbeError('')
    try {
      const template = buildRtspUrl(ip, port, user, pass, '{channel}', parseInt(subtype))
      const result = await api.probeChannels(
        template,
        parseInt(rangeStart),
        parseInt(rangeEnd),
        user || undefined,
        pass || undefined,
        parseInt(subtype)
      )
      if (result.alive.length === 0) setProbeError('No active channels found. Check your IP, credentials, or channel range.')
      setProbeResults(result.alive)
      setSelectedChannels(new Set(result.alive))
    } catch {
      setProbeError('Could not reach the NVR. Check the IP address and network connection.')
    } finally {
      setProbing(false)
    }
  }

  async function addPasteSingle() {
    if (!singleUrl || addingPasteUrl) return
    setAddingPasteUrl(true)
    const template = /[?&]channel=\d+/i.test(singleUrl)
      ? singleUrl.replace(/([?&]channel=)\d+/i, '$1{channel}')
      : null

    try {
      if (template) {
        const result = await api.probeChannels(
          template,
          Math.max(1, parseInt(rangeStart) || 1),
          Math.min(64, Math.max(1, parseInt(rangeEnd) || 16)),
          undefined,
          undefined,
          parseInt(subtype)
        )
        if (result.alive.length > 0) {
          setPending(p => [
            ...p,
            ...result.alive.map((channel) => ({
              name: `${singleName || 'Camera'} - Channel ${channel}`,
              source: {
                type: 'rtsp' as const,
                url: template.replace('{channel}', String(channel)),
              },
            })),
          ])
          setStep('confirm')
          return
        }
      }

      setPending(p => [...p, {
        name: singleName || `Camera ${p.length + 1}`,
        source: { type: 'rtsp', url: singleUrl },
      }])
      setStep('confirm')
    } catch {
      // Discovery failed: still allow the exact URL to be added as one camera.
      setPending(p => [...p, {
        name: singleName || `Camera ${p.length + 1}`,
        source: { type: 'rtsp', url: singleUrl },
      }])
      setStep('confirm')
    } finally {
      setAddingPasteUrl(false)
    }
  }

  function addSelectedChannels() {
    const newCams: PendingCamera[] = Array.from(selectedChannels).sort((a, b) => a - b).map((ch) => ({
      name: `Channel ${ch}`,
      source: { type: 'rtsp', url: buildRtspUrl(ip, port, user, pass, ch, parseInt(subtype)) },
    }))
    setPending(p => [...p, ...newCams])
    setStep('confirm')
  }

  async function loadDevices() {
    setLoadingDevices(true)
    try {
      const devs = await api.getDevices()
      setDevices(devs)
    } catch {
      setDevices([{ index: 0, name: 'Default Camera (index 0)' }])
    } finally {
      setLoadingDevices(false)
    }
  }

  function addWebcam() {
    if (!selectedDevice) return
    setPending(p => [...p, { name: selectedDevice.name, source: { type: 'webcam', device_index: selectedDevice.index } }])
    setStep('confirm')
  }

  async function finishSetup() {
    setGridSize(pending.length > 9 ? 4 : pending.length > 4 ? 3 : pending.length > 1 ? 2 : 1)
    setAppPhase('dashboard')

    for (const cam of pending) {
      try {
        const created = await api.createCamera({ name: cam.name, source: cam.source, pipeline: DEFAULT_PIPELINE })
        addCamera(created)
      } catch {
        addCamera({ id: Math.random().toString(36).slice(2), name: cam.name, source: cam.source, status: 'idle', pipeline: DEFAULT_PIPELINE })
      }
    }
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-8 py-5 border-b border-border/40">
        <img src={logoUrl} alt="logo" className="w-8 h-8" />
        <span className="font-semibold text-foreground">VisionSense Studio</span>
        <Badge variant="secondary" className="ml-2 text-xs">Setup</Badge>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-xl">

          {/* ── CHOICE ─────────────────────────────────────────────────────── */}
          {step === 'choice' && (
            <div className="space-y-8 animate-fade-in">
              <div className="text-center space-y-2">
                <h2 className="text-2xl font-bold">Connect Your Cameras</h2>
                <p className="text-muted-foreground text-sm">Choose how to add camera sources</p>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <ChoiceCard icon={<Wifi className="w-8 h-8" />}       title="RTSP / IP Camera" description="NVR, DVR, or any IP camera via RTSP"       onClick={() => setStep('rtsp')} />
                <ChoiceCard icon={<CameraIcon className="w-8 h-8" />} title="Webcam / USB"      description="Connected webcams and USB cameras"        onClick={() => { loadDevices(); setStep('webcam') }} />
                <ChoiceCard icon={<SkipForward className="w-8 h-8" />} title="Skip for Now"     description="Go to dashboard and add cameras later"   onClick={() => setAppPhase('dashboard')} muted />
              </div>
            </div>
          )}

          {/* ── RTSP ───────────────────────────────────────────────────────── */}
          {step === 'rtsp' && (
            <div className="space-y-5 animate-fade-in">
              <StepHeader step={1} total={3} title="RTSP Camera" onBack={() => { setProbeResults([]); setStep('choice') }} />

              {/* Mode tabs */}
              <div className="flex rounded-lg bg-secondary/40 p-1 gap-1">
                <TabBtn active={rtspMode === 'fields'} onClick={() => { setRtspMode('fields'); setProbeResults([]) }}>
                  Fill in Details
                </TabBtn>
                <TabBtn active={rtspMode === 'paste'} onClick={() => setRtspMode('paste')}>
                  Paste Full URL
                </TabBtn>
              </div>

              {/* ── MODE: Fill in Details ── */}
              {rtspMode === 'fields' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-3">
                    <div className="col-span-2 space-y-1.5">
                      <Label>IP Address</Label>
                      <Input placeholder="192.168.1.100" value={ip} onChange={e => setIp(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Port</Label>
                      <Input placeholder="554" value={port} onChange={e => setPort(e.target.value)} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label>Username</Label>
                      <Input placeholder="admin" value={user} onChange={e => setUser(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Password</Label>
                      <div className="relative">
                        <Input
                          type={showPass ? 'text' : 'password'}
                          placeholder="••••••"
                          value={pass}
                          onChange={e => setPass(e.target.value)}
                          className="pr-9"
                        />
                        <button
                          type="button"
                          onClick={() => setShowPass(v => !v)}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                        >
                          {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div className="space-y-1.5">
                      <Label>From Channel</Label>
                      <Input type="number" min="1" value={rangeStart} onChange={e => setRangeStart(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>To Channel</Label>
                      <Input type="number" max="64" value={rangeEnd} onChange={e => setRangeEnd(e.target.value)} />
                    </div>
                    <div className="space-y-1.5">
                      <Label>Stream</Label>
                      <select
                        value={subtype}
                        onChange={e => setSubtype(e.target.value)}
                        className="w-full h-9 rounded-md border border-input bg-input px-3 text-sm text-foreground"
                      >
                        <option value="0">Main (HD)</option>
                        <option value="1">Sub (SD)</option>
                      </select>
                    </div>
                  </div>

                  {/* URL preview */}
                  <div className="rounded-md bg-secondary/30 border border-border/50 px-3 py-2">
                    <p className="text-[10px] text-muted-foreground mb-1 uppercase tracking-wider">Generated URL preview</p>
                    <p className="font-mono text-xs text-muted-foreground break-all leading-relaxed">{previewUrl}</p>
                  </div>

                  <Button onClick={handleProbe} disabled={probing || !ip} className="w-full">
                    {probing
                      ? <><Spinner /> Scanning channels {rangeStart}–{rangeEnd}...</>
                      : <><Search className="w-4 h-4" /> Detect Active Channels</>}
                  </Button>

                  {probeError && (
                    <p className="text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md px-3 py-2">{probeError}</p>
                  )}

                  {probeResults.length > 0 && (
                    <div className="space-y-3">
                      <p className="text-sm text-muted-foreground">
                        <span className="text-foreground font-medium">{probeResults.length}</span> active channel{probeResults.length !== 1 ? 's' : ''} found
                      </p>
                      <div className="grid grid-cols-5 gap-2">
                        {probeResults.map(ch => (
                          <button
                            key={ch}
                            onClick={() => {
                              const s = new Set(selectedChannels)
                              s.has(ch) ? s.delete(ch) : s.add(ch)
                              setSelectedChannels(s)
                            }}
                            className={`relative p-2.5 rounded-lg border text-sm font-medium transition-all ${
                              selectedChannels.has(ch)
                                ? 'border-primary/60 bg-primary/10 text-foreground'
                                : 'border-border bg-secondary/40 text-muted-foreground hover:border-border/80'
                            }`}
                          >
                            {selectedChannels.has(ch) && <Check className="absolute top-1 right-1 w-2.5 h-2.5" />}
                            CH {ch}
                          </button>
                        ))}
                      </div>
                      <div className="flex gap-2 items-center">
                        <button onClick={() => setSelectedChannels(new Set(probeResults))} className="text-xs text-muted-foreground hover:text-foreground">Select all</button>
                        <span className="text-border">·</span>
                        <button onClick={() => setSelectedChannels(new Set())} className="text-xs text-muted-foreground hover:text-foreground">Clear</button>
                        <Button onClick={addSelectedChannels} disabled={selectedChannels.size === 0} size="sm" className="ml-auto">
                          <Plus className="w-3.5 h-3.5" /> Add {selectedChannels.size || ''} Channel{selectedChannels.size !== 1 ? 's' : ''}
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ── MODE: Paste Full URL ── */}
              {rtspMode === 'paste' && (
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <Label>Camera Name <span className="text-muted-foreground">(optional)</span></Label>
                    <Input placeholder="e.g. Front Entrance" value={singleName} onChange={e => setSingleName(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>RTSP URL</Label>
                    <Input
                      placeholder="rtsp://admin:pass@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0"
                      value={singleUrl}
                      onChange={e => setSingleUrl(e.target.value)}
                      className="font-mono text-xs"
                    />
                    <p className="text-xs text-muted-foreground">Paste the full RTSP URL including credentials</p>
                  </div>
                  <Button onClick={addPasteSingle} disabled={!singleUrl || addingPasteUrl} className="w-full">
                    {addingPasteUrl
                      ? <><Spinner /> Scanning channels 1–16…</>
                      : <><Plus className="w-4 h-4" /> Add Camera</>}
                  </Button>
                </div>
              )}
            </div>
          )}

          {/* ── WEBCAM ─────────────────────────────────────────────────────── */}
          {step === 'webcam' && (
            <div className="space-y-5 animate-fade-in">
              <StepHeader step={1} total={3} title="Webcam / USB Camera" onBack={() => setStep('choice')} />
              {loadingDevices ? (
                <div className="flex items-center justify-center h-32 text-muted-foreground gap-3"><Spinner /> Detecting cameras...</div>
              ) : devices.length === 0 ? (
                <div className="text-center h-32 flex items-center justify-center text-muted-foreground text-sm">No devices found. Connect a camera and try again.</div>
              ) : (
                <div className="space-y-2">
                  {devices.map(d => (
                    <button key={d.index} onClick={() => setSelectedDevice(d)}
                      className={`w-full p-4 rounded-lg border text-left transition-all ${
                        selectedDevice?.index === d.index ? 'border-primary/60 bg-primary/10' : 'border-border bg-secondary/30 hover:border-border/80'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <CameraIcon className={`w-5 h-5 ${selectedDevice?.index === d.index ? 'text-foreground' : 'text-muted-foreground'}`} />
                        <div>
                          <p className="font-medium text-sm">{d.name}</p>
                          <p className="text-xs text-muted-foreground">Index: {d.index}</p>
                        </div>
                        {selectedDevice?.index === d.index && <Check className="ml-auto w-4 h-4" />}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('choice')} className="flex-1"><ChevronLeft className="w-4 h-4" /> Back</Button>
                <Button onClick={addWebcam} disabled={!selectedDevice} className="flex-1">Use Camera <ChevronRight className="w-4 h-4" /></Button>
              </div>
            </div>
          )}

          {/* ── CONFIRM ────────────────────────────────────────────────────── */}
          {step === 'confirm' && (
            <div className="space-y-5 animate-fade-in">
              <StepHeader step={3} total={3} title="Confirm Setup" onBack={() => setStep('choice')} />
              <div className="space-y-2">
                {pending.map((cam, i) => (
                  <Card key={i} className="bg-secondary/30">
                    <CardContent className="p-4 flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        {cam.source.type === 'rtsp' ? <Wifi className="w-4 h-4" /> : <CameraIcon className="w-4 h-4" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{cam.name}</p>
                        <p className="text-xs text-muted-foreground truncate font-mono">{cam.source.url ?? `Device ${cam.source.device_index}`}</p>
                      </div>
                      <Badge variant="secondary" className="shrink-0 text-xs">{cam.source.type.toUpperCase()}</Badge>
                    </CardContent>
                  </Card>
                ))}
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => { setPending([]); setStep('choice') }} className="flex-1">Add More</Button>
                <Button onClick={finishSetup} className="flex-1"><Check className="w-4 h-4" /> Launch Dashboard</Button>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  )
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 py-1.5 text-sm font-medium rounded-md transition-all ${
        active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
      }`}
    >
      {children}
    </button>
  )
}

function ChoiceCard({ icon, title, description, onClick, muted = false }: {
  icon: React.ReactNode; title: string; description: string; onClick: () => void; muted?: boolean
}) {
  return (
    <button onClick={onClick}
      className={`group p-6 rounded-xl border text-left transition-all duration-200 w-full ${
        muted ? 'border-border/40 bg-secondary/20 hover:bg-secondary/30' : 'border-border bg-secondary/30 hover:border-primary/40 hover:bg-primary/5'
      }`}
    >
      <div className="flex flex-col gap-3">
        <div className={`transition-transform duration-200 group-hover:scale-110 ${muted ? 'opacity-40 text-muted-foreground' : 'text-foreground'}`}>{icon}</div>
        <div>
          <p className={`font-semibold text-sm ${muted ? 'text-muted-foreground' : 'text-foreground'}`}>{title}</p>
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        </div>
        <ChevronRight className={`w-4 h-4 ml-auto transition-transform duration-200 group-hover:translate-x-1 ${muted ? 'text-muted-foreground/30' : 'text-muted-foreground'}`} />
      </div>
    </button>
  )
}

function StepHeader({ step, total, title, onBack }: { step: number; total: number; title: string; onBack: () => void }) {
  return (
    <div className="space-y-3">
      <button onClick={onBack} className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors">
        <ChevronLeft className="w-3.5 h-3.5" /> Back
      </button>
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">{title}</h2>
        <Badge variant="secondary" className="text-xs">Step {step}/{total}</Badge>
      </div>
      <div className="flex gap-1">
        {Array.from({ length: total }).map((_, i) => (
          <div key={i} className={`h-0.5 flex-1 rounded-full transition-all duration-300 ${i < step ? 'bg-primary' : 'bg-border'}`} />
        ))}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
