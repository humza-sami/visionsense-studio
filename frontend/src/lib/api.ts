import type { Camera, PipelineConfig, Device } from '@/types'

let _backendUrl = 'http://localhost:8000'

export function setBackendUrl(url: string) {
  _backendUrl = url
}

export function getBackendUrl(): string {
  return _backendUrl
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${_backendUrl}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`API ${path} failed (${res.status}): ${text}`)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function getCameras(): Promise<Camera[]> {
  return request<Camera[]>('/api/cameras')
}

export async function createCamera(
  data: Omit<Camera, 'id' | 'status'>
): Promise<Camera> {
  return request<Camera>('/api/cameras', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export async function deleteCamera(id: string): Promise<void> {
  return request<void>(`/api/cameras/${id}`, { method: 'DELETE' })
}

export async function startCamera(id: string): Promise<Camera> {
  return request<Camera>(`/api/cameras/${id}/start`, { method: 'POST' })
}

export async function stopCamera(id: string): Promise<Camera> {
  return request<Camera>(`/api/cameras/${id}/stop`, { method: 'POST' })
}

export async function activateCameras(cameraIds: string[]): Promise<Camera[]> {
  return request<Camera[]>('/api/cameras/activate', {
    method: 'POST',
    body: JSON.stringify({ camera_ids: cameraIds }),
  })
}

export async function updatePipeline(
  id: string,
  pipeline: Partial<PipelineConfig>
): Promise<Camera> {
  return request<Camera>(`/api/cameras/${id}/pipeline`, {
    method: 'PATCH',
    body: JSON.stringify(pipeline),
  })
}

export async function probeChannels(
  template: string,
  rangeStart: number,
  rangeEnd: number,
  username?: string,
  password?: string,
  subtype = 0
): Promise<{ alive: number[] }> {
  return request<{ alive: number[] }>('/api/cameras/probe', {
    method: 'POST',
    body: JSON.stringify({
      template,
      range_start: rangeStart,
      range_end: rangeEnd,
      username,
      password,
      subtype,
    }),
  })
}

export async function getDevices(): Promise<Device[]> {
  return request<Device[]>('/api/devices')
}

export async function getModels(): Promise<string[]> {
  const res = await request<Array<string | { name: string }>>('/api/models')
  return res.map((m) => (typeof m === 'string' ? m : m.name))
}

export function getStreamUrl(camId: string, backendUrl?: string): string {
  const base = backendUrl ?? _backendUrl
  return `${base}/stream/${camId}`
}
