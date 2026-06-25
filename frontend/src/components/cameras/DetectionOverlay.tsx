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

// Convert hex color to rgba string for SVG fill
function hexToRgba(hex: string, alpha: number) {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

interface DetectionOverlayProps {
  detections: Detection[]
  showBoxes: boolean
  showLabels: boolean
  showKeypoints: boolean
  showSegments?: boolean
  trails?: Record<string, [number, number][]>
  showTrails: boolean
}

export function DetectionOverlay({
  detections,
  showBoxes,
  showLabels,
  showKeypoints,
  showSegments,
  trails,
  showTrails,
}: DetectionOverlayProps) {
  const hasSegments = detections.some((d) => d.segments && d.segments.length > 0)
  const nothing = !showBoxes && !showLabels && !showKeypoints && !showTrails && !(showSegments && hasSegments)
  if (nothing) return null

  return (
    <svg
      className="absolute inset-0 z-10 w-full h-full pointer-events-none"
      viewBox="0 0 1 1"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      {/* Motion trails */}
      {showTrails && trails && Object.entries(trails).map(([trackId, pts]) => {
        if (pts.length < 2) return null
        const color = COLORS[Math.abs(parseInt(trackId)) % COLORS.length]
        const d = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ')
        return (
          <path
            key={`trail-${trackId}`}
            d={d}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeOpacity="0.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )
      })}

      {/* Detections */}
      {detections.map((det, idx) => {
        const color = classColor(det.class_id)
        const w = Math.max(0, det.x2 - det.x1)
        const h = Math.max(0, det.y2 - det.y1)
        const label = `${det.track_id != null ? `#${det.track_id} ` : ''}${det.label} ${(det.confidence * 100).toFixed(0)}%`
        const labelW = Math.min(0.28, Math.max(0.09, label.length * 0.009))
        const labelY = Math.max(0.025, det.y1)
        const key = `${det.track_id ?? idx}-${det.class_id}`

        const polyPoints = det.segments?.length
          ? det.segments.map(([x, y]) => `${x},${y}`).join(' ')
          : null

        return (
          <g key={key}>
            {/* Segmentation mask polygon */}
            {showSegments && polyPoints && (
              <polygon
                points={polyPoints}
                fill={hexToRgba(color, 0.25)}
                stroke={color}
                strokeWidth="1.5"
                strokeOpacity="0.85"
                vectorEffect="non-scaling-stroke"
              />
            )}

            {/* Bounding box (detect / obb modes) */}
            {showBoxes && (
              <rect
                x={det.x1}
                y={det.y1}
                width={w}
                height={h}
                fill="transparent"
                stroke={color}
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            )}

            {/* Label */}
            {showLabels && (
              <>
                <rect
                  x={det.x1}
                  y={labelY - 0.025}
                  width={labelW}
                  height="0.025"
                  fill={color}
                  opacity="0.92"
                />
                <text
                  x={det.x1 + 0.004}
                  y={labelY - 0.006}
                  fill="#020617"
                  fontSize="0.014"
                  fontWeight="700"
                >
                  {label}
                </text>
              </>
            )}

            {/* Pose skeleton */}
            {showKeypoints && det.keypoints && det.keypoints.length >= 5 && (
              <>
                {SKELETON.map(([a, b], i) => {
                  const kpA = det.keypoints![a]
                  const kpB = det.keypoints![b]
                  if (!kpA || !kpB || kpA[2] < 0.3 || kpB[2] < 0.3) return null
                  return (
                    <line
                      key={i}
                      x1={kpA[0]} y1={kpA[1]}
                      x2={kpB[0]} y2={kpB[1]}
                      stroke={color}
                      strokeWidth="2"
                      strokeOpacity="0.9"
                      vectorEffect="non-scaling-stroke"
                    />
                  )
                })}
                {det.keypoints.map((kp, i) => {
                  if (kp[2] < 0.3) return null
                  return (
                    <circle
                      key={i}
                      cx={kp[0]}
                      cy={kp[1]}
                      r="0.004"
                      fill="white"
                      stroke={color}
                      strokeWidth="1"
                      vectorEffect="non-scaling-stroke"
                    />
                  )
                })}
              </>
            )}
          </g>
        )
      })}
    </svg>
  )
}
