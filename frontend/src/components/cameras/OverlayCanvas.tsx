import { useEffect, useRef } from 'react'
import type { Detection } from '@/types'

// COCO 17-keypoint skeleton pairs
const SKELETON: [number, number][] = [
  [15, 13], [13, 11], [16, 14], [14, 12], [11, 12],
  [5, 11],  [6, 12],  [5, 6],   [5, 7],   [6, 8],
  [7, 9],   [8, 10],  [1, 2],   [0, 1],   [0, 2],
  [1, 3],   [2, 4],   [3, 5],   [4, 6],
]

const COLORS = [
  '#38bdf8', '#34d399', '#fbbf24', '#fb7185', '#a78bfa',
  '#2dd4bf', '#f97316', '#60a5fa', '#e879f9', '#a3e635',
]

function classColor(classId: number) {
  return COLORS[Math.abs(classId) % COLORS.length]
}

function hexToRgb(hex: string): [number, number, number] {
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
  ]
}

export interface OverlayData {
  detections: Detection[]
  trails: Record<string, [number, number][]> | undefined
  showBoxes: boolean
  showLabels: boolean
  showKeypoints: boolean
  showSegments: boolean
  showTrails: boolean
}

interface OverlayCanvasProps {
  videoEl: HTMLVideoElement | null
  dataRef: React.MutableRefObject<OverlayData>
}

export function OverlayCanvas({ videoEl, dataRef }: OverlayCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!videoEl || !canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let cbId = 0
    let running = true

    const draw = (_now: DOMHighResTimeStamp, _meta: VideoFrameCallbackMetadata) => {
      if (!running) return

      // Match canvas to displayed container size
      const cw = videoEl.clientWidth || 640
      const ch = videoEl.clientHeight || 480
      if (canvas.width !== cw || canvas.height !== ch) {
        canvas.width = cw
        canvas.height = ch
      }

      ctx.clearRect(0, 0, cw, ch)

      // Compute object-cover transform: video is scaled to fill the container,
      // with overflow cropped symmetrically. Detection coords are normalized to
      // the original video frame, so we must map through this same transform.
      const vw = videoEl.videoWidth || cw
      const vh = videoEl.videoHeight || ch
      const scale = Math.max(cw / vw, ch / vh)
      const renderedW = vw * scale
      const renderedH = vh * scale
      const ox = (cw - renderedW) / 2  // negative when video wider than container
      const oy = (ch - renderedH) / 2  // negative when video taller than container

      // Map normalized coord (0-1 relative to source frame) → canvas pixel
      const cx_ = (n: number) => n * renderedW + ox
      const cy_ = (n: number) => n * renderedH + oy

      const { detections, trails, showBoxes, showLabels, showKeypoints, showSegments, showTrails } = dataRef.current

      // ── Trails ──────────────────────────────────────────────────────────────
      if (showTrails && trails) {
        for (const [trackId, pts] of Object.entries(trails)) {
          if (pts.length < 2) continue
          const color = COLORS[Math.abs(parseInt(trackId)) % COLORS.length]
          ctx.lineWidth = 2
          ctx.lineCap = 'round'
          ctx.lineJoin = 'round'
          for (let i = 1; i < pts.length; i++) {
            ctx.globalAlpha = (i / pts.length) * 0.7
            ctx.strokeStyle = color
            ctx.beginPath()
            ctx.moveTo(cx_(pts[i - 1][0]), cy_(pts[i - 1][1]))
            ctx.lineTo(cx_(pts[i][0]), cy_(pts[i][1]))
            ctx.stroke()
          }
          ctx.globalAlpha = 1
        }
      }

      // ── Detections ──────────────────────────────────────────────────────────
      for (const det of detections) {
        const color = classColor(det.class_id)
        const [r, g, b] = hexToRgb(color)
        const x1 = Math.round(cx_(det.x1))
        const y1 = Math.round(cy_(det.y1))
        const x2 = Math.round(cx_(det.x2))
        const y2 = Math.round(cy_(det.y2))

        // Segment polygon
        if (showSegments && det.segments?.length) {
          ctx.beginPath()
          ctx.moveTo(cx_(det.segments[0][0]), cy_(det.segments[0][1]))
          for (const [px, py] of det.segments.slice(1)) {
            ctx.lineTo(cx_(px), cy_(py))
          }
          ctx.closePath()
          ctx.fillStyle = `rgba(${r},${g},${b},0.25)`
          ctx.fill()
          ctx.strokeStyle = color
          ctx.globalAlpha = 0.85
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.globalAlpha = 1
        }

        // Bounding box
        if (showBoxes) {
          ctx.strokeStyle = color
          ctx.lineWidth = 2
          ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
        }

        // Label
        if (showLabels) {
          const label = `${det.track_id != null ? `#${det.track_id} ` : ''}${det.label} ${(det.confidence * 100).toFixed(0)}%`
          ctx.font = 'bold 11px sans-serif'
          const tw = ctx.measureText(label).width
          const lx = x1
          const ly = Math.max(16, y1)
          ctx.fillStyle = color
          ctx.fillRect(lx, ly - 15, tw + 8, 15)
          ctx.fillStyle = '#020617'
          ctx.fillText(label, lx + 4, ly - 4)
        }

        // Keypoints + skeleton
        if (showKeypoints && det.keypoints && det.keypoints.length >= 5) {
          ctx.globalAlpha = 0.9

          // Skeleton lines
          ctx.strokeStyle = color
          ctx.lineWidth = 2
          for (const [a, bIdx] of SKELETON) {
            const kpA = det.keypoints[a]
            const kpB = det.keypoints[bIdx]
            if (!kpA || !kpB || kpA[2] < 0.3 || kpB[2] < 0.3) continue
            ctx.beginPath()
            ctx.moveTo(cx_(kpA[0]), cy_(kpA[1]))
            ctx.lineTo(cx_(kpB[0]), cy_(kpB[1]))
            ctx.stroke()
          }

          // Keypoint circles
          for (const kp of det.keypoints) {
            if (kp[2] < 0.3) continue
            ctx.beginPath()
            ctx.arc(cx_(kp[0]), cy_(kp[1]), 4, 0, Math.PI * 2)
            ctx.fillStyle = 'white'
            ctx.fill()
            ctx.strokeStyle = color
            ctx.lineWidth = 1
            ctx.stroke()
          }

          ctx.globalAlpha = 1
        }
      }

      cbId = videoEl.requestVideoFrameCallback(draw)
    }

    cbId = videoEl.requestVideoFrameCallback(draw)
    return () => {
      running = false
      videoEl.cancelVideoFrameCallback(cbId)
      const canvas = canvasRef.current
      if (canvas) {
        const ctx = canvas.getContext('2d')
        ctx?.clearRect(0, 0, canvas.width, canvas.height)
      }
    }
  }, [videoEl, dataRef])

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 w-full h-full pointer-events-none z-10"
    />
  )
}
