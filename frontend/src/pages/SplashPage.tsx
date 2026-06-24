import { useEffect } from 'react'
import { useStore } from '@/store/useStore'
import logoUrl from '@/assets/logo.svg'

export function SplashPage() {
  const setAppPhase = useStore((s) => s.setAppPhase)

  useEffect(() => {
    const timer = setTimeout(() => setAppPhase('setup'), 3000)
    return () => clearTimeout(timer)
  }, [setAppPhase])

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center"
      style={{ backgroundColor: '#181818' }}
    >
      {/* Eye icon */}
      <img
        src={logoUrl}
        alt="VisionSense"
        className="w-48 h-48 mb-6 select-none"
        draggable={false}
        style={{ filter: 'drop-shadow(0 0 24px rgba(25,181,190,0.35))' }}
      />

      {/* Wordmark */}
      <h1
        className="text-white select-none"
        style={{
          fontSize: '3.2rem',
          fontWeight: 800,
          letterSpacing: '-0.01em',
          lineHeight: 1,
          fontFamily: 'Inter Variable, sans-serif',
        }}
      >
        VisionSense
      </h1>

      {/* Tagline */}
      <p
        className="mt-2 select-none"
        style={{
          color: '#19B5BE',
          fontSize: '0.75rem',
          fontWeight: 500,
          letterSpacing: '0.3em',
          textTransform: 'uppercase',
          fontFamily: 'Inter Variable, sans-serif',
        }}
      >
        Business Intelligence
      </p>

      {/* Thin loading bar at bottom */}
      <div
        className="absolute bottom-0 left-0 h-[2px]"
        style={{
          backgroundColor: '#19B5BE',
          animation: 'splash-bar 3s linear forwards',
        }}
      />

      <style>{`
        @keyframes splash-bar {
          from { width: 0% }
          to   { width: 100% }
        }
      `}</style>
    </div>
  )
}
