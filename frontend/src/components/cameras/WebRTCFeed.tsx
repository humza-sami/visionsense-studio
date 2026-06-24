import { useEffect, useRef } from 'react'

interface WebRTCFeedProps {
  cameraId: string
  cameraName: string
  retryToken: number
  onPlaying: () => void
  onUnavailable: () => void
}

const ICE_GATHER_TIMEOUT_MS = 3000
const PLAYBACK_TIMEOUT_MS = 8000

function getWhepUrl(cameraId: string): string {
  const configured = import.meta.env.VITE_WEBRTC_BASE_URL as string | undefined
  const base = configured?.replace(/\/$/, '')
    ?? `${window.location.protocol}//${window.location.hostname}:8889`
  return `${base}/${encodeURIComponent(cameraId)}/whep`
}

function waitForIceGathering(
  peer: RTCPeerConnection,
  timeoutMs: number
): Promise<void> {
  if (peer.iceGatheringState === 'complete') return Promise.resolve()

  return new Promise((resolve) => {
    const timeout = window.setTimeout(finish, timeoutMs)
    function finish() {
      window.clearTimeout(timeout)
      peer.removeEventListener('icegatheringstatechange', onStateChange)
      resolve()
    }
    function onStateChange() {
      if (peer.iceGatheringState === 'complete') finish()
    }
    peer.addEventListener('icegatheringstatechange', onStateChange)
  })
}

export function WebRTCFeed({
  cameraId,
  cameraName,
  retryToken,
  onPlaying,
  onUnavailable,
}: WebRTCFeedProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const abortController = new AbortController()
    const peer = new RTCPeerConnection({
      bundlePolicy: 'max-bundle',
    })
    let resourceUrl: string | null = null
    let disposed = false
    let playbackTimer = 0

    const fail = () => {
      if (!disposed) onUnavailable()
    }

    async function connect() {
      try {
        playbackTimer = window.setTimeout(fail, PLAYBACK_TIMEOUT_MS)
        const video = videoRef.current
        if (video) {
          video.onplaying = () => {
            window.clearTimeout(playbackTimer)
            onPlaying()
          }
          video.onerror = fail
        }
        peer.addTransceiver('video', { direction: 'recvonly' })
        peer.ontrack = (event) => {
          const target = videoRef.current
          if (target) {
            target.srcObject = event.streams[0] ?? new MediaStream([event.track])
          }
        }
        peer.onconnectionstatechange = () => {
          if (peer.connectionState === 'failed' || peer.connectionState === 'closed') {
            fail()
          }
        }

        const offer = await peer.createOffer()
        await peer.setLocalDescription(offer)
        await waitForIceGathering(peer, ICE_GATHER_TIMEOUT_MS)
        if (!peer.localDescription) throw new Error('WebRTC offer was not created')

        const whepUrl = getWhepUrl(cameraId)
        const response = await fetch(whepUrl, {
          method: 'POST',
          headers: {
            Accept: 'application/sdp',
            'Content-Type': 'application/sdp',
          },
          body: peer.localDescription.sdp,
          signal: abortController.signal,
        })
        if (!response.ok) {
          throw new Error(`WHEP request failed (${response.status})`)
        }

        const location = response.headers.get('Location')
        if (location) resourceUrl = new URL(location, whepUrl).toString()
        const answer = await response.text()
        await peer.setRemoteDescription({ type: 'answer', sdp: answer })
      } catch (error) {
        if (!abortController.signal.aborted) fail()
      }
    }

    void connect()
    return () => {
      disposed = true
      window.clearTimeout(playbackTimer)
      abortController.abort()
      const video = videoRef.current
      if (video) {
        video.onplaying = null
        video.onerror = null
        video.srcObject = null
      }
      peer.close()
      if (resourceUrl) {
        void fetch(resourceUrl, { method: 'DELETE', keepalive: true }).catch(() => {})
      }
    }
  }, [cameraId, onPlaying, onUnavailable, retryToken])

  return (
    <video
      ref={videoRef}
      aria-label={cameraName}
      autoPlay
      muted
      playsInline
      className="absolute inset-0 w-full h-full object-cover"
    />
  )
}
