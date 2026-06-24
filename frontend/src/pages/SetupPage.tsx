import { useState, useEffect } from 'react'
import { Wifi, Camera as CameraIcon, SkipForward, ChevronRight, ChevronLeft, Search, Check, Plus } from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import * as api from '@/lib/api'
import type { Camera as CameraType, Device } from '@/types'
import logoUrl from '@/assets/logo.svg'

type SetupStep = 'choice' | 'rtsp' | 'rtsp-single' | 'rtsp-auto' | 'webcam' | 'confirm'

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
  features: { boxes: true, masks: false, keypoints: false, labels: true, trails: false, obb: false, semantic: false },
  applications: [],
  frame_skip: 0,
}

export function SetupPage() {
  const { setAppPhase, addCamera, backendUrl } = useStore()
  const [step, setStep] = useState<SetupStep>('choice')
  const [pending, setPending] = useState<PendingCamera[]>([])

  // RTSP single
  const [singleUrl, setSingleUrl] = useState('')
  const [singleName, setSingleName] = useState('')

  // RTSP auto-detect
  const [autoIp, setAutoIp] = useState('')
  const [autoPort, setAutoPort] = useState('554')
  const [autoUser, setAutoUser] = useState('')
  const [autoPass, setAutoPass] = useState('')
  const [autoPath, setAutoPath] = useState('rtsp://{ip}:{port}/{user}:{pass}@channel{channel}/subtype{subtype}')
  const [autoRangeStart, setAutoRangeStart] = useState('1')
  const [autoRangeEnd, setAutoRangeEnd] = useState('16')
  const [probing, setProbing] = useState(false)
  const [probeResults, setProbeResults] = useState<number[]>([])
  const [selectedChannels, setSelectedChannels] = useState<Set<number>>(new Set())

  // Webcam
  const [devices, setDevices] = useState<Device[]>([])
  const [loadingDevices, setLoadingDevices] = useState(false)
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null)

  useEffect(() => {
    api.setBackendUrl(backendUrl)
  }, [backendUrl])

  async function handleProbe() {
    setProbing(true)
    setProbeResults([])
    try {
      const result = await api.probeChannels(
        autoPath,
        parseInt(autoRangeStart),
        parseInt(autoRangeEnd),
        autoUser || undefined,
        autoPass || undefined,
        autoPort ? parseInt(autoPort) : undefined
      )
      setProbeResults(result.alive)
    } catch {
      setProbeResults([])
    } finally {
      setProbing(false)
    }
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

  function addRtspSingle() {
    if (!singleUrl) return
    setPending([...pending, {
      name: singleName || `Camera ${pending.length + 1}`,
      source: { type: 'rtsp', url: singleUrl },
    }])
    setSingleUrl('')
    setSingleName('')
    setStep('confirm')
  }

  function addSelectedChannels() {
    const newCams: PendingCamera[] = Array.from(selectedChannels).map((ch) => ({
      name: `Channel ${ch}`,
      source: { type: 'rtsp', url: autoPath.replace('{channel}', String(ch)).replace('{ip}', autoIp).replace('{port}', autoPort).replace('{user}', autoUser).replace('{pass}', autoPass).replace('{subtype}', '0') },
    }))
    setPending([...pending, ...newCams])
    setStep('confirm')
  }

  function addWebcam() {
    if (!selectedDevice) return
    setPending([...pending, {
      name: selectedDevice.name,
      source: { type: 'webcam', device_index: selectedDevice.index },
    }])
    setStep('confirm')
  }

  async function finishSetup() {
    for (const cam of pending) {
      try {
        const created = await api.createCamera({ name: cam.name, source: cam.source, pipeline: DEFAULT_PIPELINE })
        addCamera(created)
      } catch {
        addCamera({
          id: Math.random().toString(36).slice(2),
          name: cam.name,
          source: cam.source,
          status: 'idle',
          pipeline: DEFAULT_PIPELINE,
        })
      }
    }
    setAppPhase('dashboard')
  }

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 px-8 py-5 border-b border-border/40">
        <img src={logoUrl} alt="logo" className="w-8 h-8" />
        <span className="font-semibold text-gradient">VisionSense Studio</span>
        <Badge variant="secondary" className="ml-2 text-xs">Setup</Badge>
      </div>

      <div className="flex-1 flex items-center justify-center p-8">
        <div className="w-full max-w-2xl">

          {/* STEP: Choice */}
          {step === 'choice' && (
            <div className="space-y-8 animate-fade-in">
              <div className="text-center space-y-2">
                <h2 className="text-2xl font-bold text-foreground">Connect Your Cameras</h2>
                <p className="text-muted-foreground">Choose how to add camera sources to VisionSense Studio</p>
              </div>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <ChoiceCard
                  icon={<Wifi className="w-8 h-8 text-indigo-400" />}
                  title="RTSP Network Camera"
                  description="IP cameras, NVRs, DVRs via RTSP protocol"
                  onClick={() => { setStep('rtsp') }}
                />
                <ChoiceCard
                  icon={<CameraIcon className="w-8 h-8 text-indigo-400" />}
                  title="Webcam / USB"
                  description="Connected webcams and USB cameras"
                  onClick={() => { loadDevices(); setStep('webcam') }}
                />
                <ChoiceCard
                  icon={<SkipForward className="w-8 h-8 text-muted-foreground" />}
                  title="Skip for Now"
                  description="Go to dashboard and add cameras later"
                  onClick={() => setAppPhase('dashboard')}
                  muted
                />
              </div>
            </div>
          )}

          {/* STEP: RTSP mode select */}
          {step === 'rtsp' && (
            <div className="space-y-6 animate-fade-in">
              <StepHeader step={1} total={3} title="RTSP Camera Source" onBack={() => setStep('choice')} />
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <ChoiceCard
                  icon={<Wifi className="w-7 h-7 text-indigo-400" />}
                  title="Single Camera URL"
                  description="Enter a complete RTSP stream URL"
                  onClick={() => setStep('rtsp-single')}
                />
                <ChoiceCard
                  icon={<Search className="w-7 h-7 text-indigo-400" />}
                  title="Auto-Detect NVR Channels"
                  description="Probe an NVR/DVR for active channels"
                  onClick={() => setStep('rtsp-auto')}
                />
              </div>
            </div>
          )}

          {/* STEP: RTSP single URL */}
          {step === 'rtsp-single' && (
            <div className="space-y-6 animate-fade-in">
              <StepHeader step={2} total={3} title="Single RTSP Camera" onBack={() => setStep('rtsp')} />
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="cam-name">Camera Name</Label>
                  <Input id="cam-name" placeholder="e.g. Front Door" value={singleName} onChange={(e) => setSingleName(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rtsp-url">RTSP URL</Label>
                  <Input id="rtsp-url" placeholder="rtsp://user:pass@192.168.1.100:554/stream" value={singleUrl} onChange={(e) => setSingleUrl(e.target.value)} />
                </div>
              </div>
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('rtsp')} className="flex-1">
                  <ChevronLeft className="w-4 h-4" /> Back
                </Button>
                <Button onClick={addRtspSingle} disabled={!singleUrl} className="flex-1">
                  Add Camera <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}

          {/* STEP: RTSP auto-detect */}
          {step === 'rtsp-auto' && (
            <div className="space-y-6 animate-fade-in">
              <StepHeader step={2} total={3} title="Auto-Detect NVR Channels" onBack={() => setStep('rtsp')} />
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>NVR IP Address</Label>
                  <Input placeholder="192.168.1.100" value={autoIp} onChange={(e) => setAutoIp(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Port</Label>
                  <Input placeholder="554" value={autoPort} onChange={(e) => setAutoPort(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Username</Label>
                  <Input placeholder="admin" value={autoUser} onChange={(e) => setAutoUser(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Password</Label>
                  <Input type="password" placeholder="••••••" value={autoPass} onChange={(e) => setAutoPass(e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Channel Range Start</Label>
                  <Input type="number" value={autoRangeStart} onChange={(e) => setAutoRangeStart(e.target.value)} min="1" />
                </div>
                <div className="space-y-2">
                  <Label>Channel Range End</Label>
                  <Input type="number" value={autoRangeEnd} onChange={(e) => setAutoRangeEnd(e.target.value)} max="64" />
                </div>
                <div className="col-span-2 space-y-2">
                  <Label>URL Template</Label>
                  <Input value={autoPath} onChange={(e) => setAutoPath(e.target.value)} className="font-mono text-xs" />
                  <p className="text-xs text-muted-foreground">Use {'{channel}'}, {'{ip}'}, {'{port}'}, {'{user}'}, {'{pass}'}, {'{subtype}'} as placeholders</p>
                </div>
              </div>

              <Button onClick={handleProbe} disabled={probing || !autoIp} className="w-full">
                {probing ? (
                  <span className="flex items-center gap-2"><Spinner /> Probing channels...</span>
                ) : (
                  <span className="flex items-center gap-2"><Search className="w-4 h-4" /> Detect Channels</span>
                )}
              </Button>

              {probeResults.length > 0 && (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">{probeResults.length} active channel(s) found</p>
                  <div className="grid grid-cols-4 gap-2">
                    {probeResults.map((ch) => (
                      <button
                        key={ch}
                        onClick={() => {
                          const s = new Set(selectedChannels)
                          s.has(ch) ? s.delete(ch) : s.add(ch)
                          setSelectedChannels(s)
                        }}
                        className={`relative p-3 rounded-lg border text-sm font-medium transition-all duration-150 ${
                          selectedChannels.has(ch)
                            ? 'border-indigo-500 bg-indigo-500/20 text-indigo-300'
                            : 'border-border bg-secondary/50 text-foreground hover:border-indigo-500/40'
                        }`}
                      >
                        {selectedChannels.has(ch) && (
                          <Check className="absolute top-1 right-1 w-3 h-3 text-indigo-400" />
                        )}
                        CH {ch}
                      </button>
                    ))}
                  </div>
                  <div className="flex gap-3">
                    <Button variant="outline" onClick={() => setSelectedChannels(new Set(probeResults))} size="sm">
                      Select All
                    </Button>
                    <Button variant="outline" onClick={() => setSelectedChannels(new Set())} size="sm">
                      Clear
                    </Button>
                    <Button onClick={addSelectedChannels} disabled={selectedChannels.size === 0} className="ml-auto">
                      <Plus className="w-4 h-4" /> Add {selectedChannels.size} Channel(s)
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP: Webcam */}
          {step === 'webcam' && (
            <div className="space-y-6 animate-fade-in">
              <StepHeader step={2} total={3} title="Webcam / USB Camera" onBack={() => setStep('choice')} />
              {loadingDevices ? (
                <div className="flex items-center justify-center h-32 text-muted-foreground gap-3">
                  <Spinner /> Detecting cameras...
                </div>
              ) : devices.length === 0 ? (
                <div className="text-center h-32 flex items-center justify-center text-muted-foreground">
                  No devices found. Make sure cameras are connected.
                </div>
              ) : (
                <div className="space-y-3">
                  {devices.map((d) => (
                    <button
                      key={d.index}
                      onClick={() => setSelectedDevice(d)}
                      className={`w-full p-4 rounded-lg border text-left transition-all duration-150 ${
                        selectedDevice?.index === d.index
                          ? 'border-indigo-500 bg-indigo-500/10'
                          : 'border-border bg-secondary/30 hover:border-indigo-500/40'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <CameraIcon className={`w-5 h-5 ${selectedDevice?.index === d.index ? 'text-indigo-400' : 'text-muted-foreground'}`} />
                        <div>
                          <p className="font-medium text-sm">{d.name}</p>
                          <p className="text-xs text-muted-foreground">Device index: {d.index}</p>
                        </div>
                        {selectedDevice?.index === d.index && (
                          <Check className="ml-auto w-4 h-4 text-indigo-400" />
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="flex gap-3">
                <Button variant="outline" onClick={() => setStep('choice')} className="flex-1">
                  <ChevronLeft className="w-4 h-4" /> Back
                </Button>
                <Button onClick={addWebcam} disabled={!selectedDevice} className="flex-1">
                  Use This Camera <ChevronRight className="w-4 h-4" />
                </Button>
              </div>
            </div>
          )}

          {/* STEP: Confirm */}
          {step === 'confirm' && (
            <div className="space-y-6 animate-fade-in">
              <StepHeader step={3} total={3} title="Confirm Camera Setup" onBack={() => setStep('choice')} />
              <div className="space-y-3">
                {pending.map((cam, i) => (
                  <Card key={i} className="bg-secondary/30">
                    <CardContent className="p-4 flex items-center gap-3">
                      <div className="w-8 h-8 rounded-full bg-indigo-500/20 flex items-center justify-center">
                        {cam.source.type === 'rtsp' ? (
                          <Wifi className="w-4 h-4 text-indigo-400" />
                        ) : (
                          <CameraIcon className="w-4 h-4 text-indigo-400" />
                        )}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-sm">{cam.name}</p>
                        <p className="text-xs text-muted-foreground truncate">
                          {cam.source.url ?? `Device ${cam.source.device_index}`}
                        </p>
                      </div>
                      <Badge variant={cam.source.type === 'rtsp' ? 'indigo' : 'secondary'} className="shrink-0">
                        {cam.source.type.toUpperCase()}
                      </Badge>
                    </CardContent>
                  </Card>
                ))}
              </div>

              <div className="flex gap-3">
                <Button
                  variant="outline"
                  onClick={() => { setPending([]); setStep('choice') }}
                  className="flex-1"
                >
                  Add More
                </Button>
                <Button onClick={finishSetup} className="flex-1" variant="glow">
                  <Check className="w-4 h-4" /> Finish Setup
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function ChoiceCard({
  icon,
  title,
  description,
  onClick,
  muted = false,
}: {
  icon: React.ReactNode
  title: string
  description: string
  onClick: () => void
  muted?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className={`group p-6 rounded-xl border text-left transition-all duration-200 ${
        muted
          ? 'border-border/40 bg-secondary/20 hover:border-border/60 hover:bg-secondary/30'
          : 'border-border bg-secondary/30 hover:border-indigo-500/50 hover:bg-indigo-500/5 hover:shadow-[0_0_20px_rgba(99,102,241,0.1)]'
      }`}
    >
      <div className="flex flex-col gap-3">
        <div className={`transition-transform duration-200 group-hover:scale-110 ${muted ? 'opacity-50' : ''}`}>
          {icon}
        </div>
        <div>
          <p className={`font-semibold text-sm ${muted ? 'text-muted-foreground' : 'text-foreground'}`}>{title}</p>
          <p className="text-xs text-muted-foreground mt-1">{description}</p>
        </div>
        <ChevronRight className={`w-4 h-4 ml-auto transition-transform duration-200 group-hover:translate-x-1 ${muted ? 'text-muted-foreground/40' : 'text-muted-foreground'}`} />
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
      <div className="flex items-center gap-3">
        <h2 className="text-xl font-bold">{title}</h2>
        <Badge variant="secondary" className="ml-auto text-xs">Step {step}/{total}</Badge>
      </div>
      <div className="flex gap-1">
        {Array.from({ length: total }).map((_, i) => (
          <div key={i} className={`h-0.5 flex-1 rounded-full transition-all duration-300 ${i < step ? 'bg-indigo-500' : 'bg-border'}`} />
        ))}
      </div>
    </div>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin w-4 h-4 text-indigo-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}
