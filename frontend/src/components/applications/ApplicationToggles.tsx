import { useState } from 'react'
import {
  Users, ArrowLeftRight, UserCheck, Smartphone, HardHat,
  Flame, ShieldAlert, EyeOff, Gauge, Search, ChevronRight
} from 'lucide-react'
import { useStore } from '@/store/useStore'
import { Switch } from '@/components/ui/switch'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import * as api from '@/lib/api'
import type { ApplicationConfig, Camera } from '@/types'

interface AppDef {
  type: string
  label: string
  icon: React.ReactNode
  description: string
  color: string
  hasZone?: boolean
  hasLine?: boolean
}

const APP_DEFS: AppDef[] = [
  {
    type: 'head_count',
    label: 'Head Count',
    icon: <Users className="w-4 h-4" />,
    description: 'Count persons in frame',
    color: 'text-blue-400',
  },
  {
    type: 'customer_in_out',
    label: 'Customer In/Out',
    icon: <ArrowLeftRight className="w-4 h-4" />,
    description: 'Line-crossing counter',
    color: 'text-green-400',
    hasLine: true,
  },
  {
    type: 'manager_presence',
    label: 'Manager Presence',
    icon: <UserCheck className="w-4 h-4" />,
    description: 'Detect person in seat',
    color: 'text-purple-400',
    hasZone: true,
  },
  {
    type: 'mobile_usage',
    label: 'Mobile Usage',
    icon: <Smartphone className="w-4 h-4" />,
    description: 'Phone usage detection',
    color: 'text-amber-400',
  },
  {
    type: 'ppe_safety',
    label: 'PPE / Safety',
    icon: <HardHat className="w-4 h-4" />,
    description: 'Safety equipment check',
    color: 'text-orange-400',
  },
  {
    type: 'heatmap',
    label: 'Heatmap',
    icon: <Flame className="w-4 h-4" />,
    description: 'Foot traffic heatmap',
    color: 'text-red-400',
  },
  {
    type: 'intrusion',
    label: 'Intrusion Alarm',
    icon: <ShieldAlert className="w-4 h-4" />,
    description: 'Zone alert system',
    color: 'text-red-400',
    hasZone: true,
  },
  {
    type: 'privacy_blur',
    label: 'Privacy Blur',
    icon: <EyeOff className="w-4 h-4" />,
    description: 'Face / person blur',
    color: 'text-slate-400',
  },
  {
    type: 'speed_estimation',
    label: 'Speed Estimation',
    icon: <Gauge className="w-4 h-4" />,
    description: 'Object speed tracking',
    color: 'text-cyan-400',
  },
]

async function doToggleApp(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  type: string,
  enabled: boolean
) {
  const { applications } = cam.pipeline
  let newApps: ApplicationConfig[]
  const existing = applications.find((a) => a.type === type)

  if (existing) {
    newApps = applications.map((a) => a.type === type ? { ...a, enabled } : a)
  } else {
    newApps = [...applications, { type, enabled, config: {} }]
  }

  updateCamera(cam.id, { pipeline: { ...cam.pipeline, applications: newApps } })
  try {
    await api.updatePipeline(cam.id, { applications: newApps })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, applications } })
  }
}

async function doSubmitPrompt(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  customPrompt: string
) {
  const { open_vocab_prompt } = cam.pipeline
  const tokens = customPrompt.split(',').map((t) => t.trim()).filter(Boolean)
  const newPrompt = [...new Set([...open_vocab_prompt, ...tokens])]
  updateCamera(cam.id, { pipeline: { ...cam.pipeline, open_vocab_prompt: newPrompt } })
  try {
    await api.updatePipeline(cam.id, { open_vocab_prompt: newPrompt })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, open_vocab_prompt } })
  }
}

async function doRemoveToken(
  cam: Camera,
  updateCamera: (id: string, u: Partial<Camera>) => void,
  token: string
) {
  const { open_vocab_prompt } = cam.pipeline
  const newPrompt = open_vocab_prompt.filter((t) => t !== token)
  updateCamera(cam.id, { pipeline: { ...cam.pipeline, open_vocab_prompt: newPrompt } })
  try {
    await api.updatePipeline(cam.id, { open_vocab_prompt: newPrompt })
  } catch {
    updateCamera(cam.id, { pipeline: { ...cam.pipeline, open_vocab_prompt } })
  }
}

export function ApplicationToggles() {
  const { selectedCameraId, cameras, updateCamera } = useStore()
  const [customPrompt, setCustomPrompt] = useState('')
  const camera = cameras.find((c) => c.id === selectedCameraId)

  if (!camera) {
    return (
      <div className="text-xs text-muted-foreground text-center py-4">
        Select a camera to configure applications
      </div>
    )
  }

  const { applications, open_vocab_prompt } = camera.pipeline

  function isEnabled(type: string) {
    return applications.some((a) => a.type === type && a.enabled)
  }

  return (
    <div className="space-y-1">
      {APP_DEFS.map((app) => {
        const enabled = isEnabled(app.type)
        return (
          <div key={app.type} className="rounded-lg overflow-hidden">
            <div className="flex items-center gap-3 px-2 py-2 hover:bg-secondary/50 transition-colors group">
              <div className={`w-7 h-7 rounded-md flex items-center justify-center transition-colors ${
                enabled ? 'bg-indigo-500/10' : 'bg-secondary/60'
              } ${enabled ? app.color : 'text-muted-foreground'}`}>
                {app.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{app.label}</p>
                <p className="text-xs text-muted-foreground">{app.description}</p>
              </div>
              <div className="flex items-center gap-2">
                {enabled && (app.hasZone || app.hasLine) && (
                  <Button size="sm" variant="outline" className="h-6 px-2 text-[10px]">
                    {app.hasLine ? 'Draw Line' : 'Draw Zone'}
                    <ChevronRight className="w-3 h-3" />
                  </Button>
                )}
                <Switch
                  checked={enabled}
                  onCheckedChange={(v) => void doToggleApp(camera, updateCamera, app.type, v)}
                />
              </div>
            </div>
          </div>
        )
      })}

      {/* Custom Detection */}
      <div className="mt-3 pt-3 border-t border-border/50 space-y-2">
        <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider px-2">Custom Detection</p>

        {open_vocab_prompt.length > 0 && (
          <div className="flex flex-wrap gap-1 px-2">
            {open_vocab_prompt.map((token) => (
              <button
                key={token}
                onClick={() => void doRemoveToken(camera, updateCamera, token)}
                className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-xs hover:bg-red-500/15 hover:border-red-500/30 hover:text-red-300 transition-colors group"
              >
                {token}
                <span className="text-[10px] opacity-0 group-hover:opacity-100 transition-opacity">×</span>
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2 px-2">
          <Input
            placeholder="knife, hardhat, phone..."
            value={customPrompt}
            onChange={(e) => setCustomPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                void doSubmitPrompt(camera, updateCamera, customPrompt)
                setCustomPrompt('')
              }
            }}
            className="h-8 text-xs flex-1"
          />
          <Button
            size="sm"
            variant="outline"
            onClick={() => {
              void doSubmitPrompt(camera, updateCamera, customPrompt)
              setCustomPrompt('')
            }}
            className="h-8 px-2.5 shrink-0"
          >
            <Search className="w-3.5 h-3.5" />
          </Button>
        </div>
        <p className="text-[10px] text-muted-foreground px-2">Comma-separated objects. Press Enter or click search.</p>
      </div>
    </div>
  )
}
