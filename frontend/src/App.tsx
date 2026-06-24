import { useEffect } from 'react'
import { useStore } from '@/store/useStore'
import { SplashPage } from '@/pages/SplashPage'
import { SetupPage } from '@/pages/SetupPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { Toaster } from '@/components/ui/toaster'

export default function App() {
  const appPhase = useStore((s) => s.appPhase)

  // Apply dark class to <html> so Radix portals (Select, Dialog, Tooltip)
  // get the correct CSS variables — portals render outside any child div
  useEffect(() => {
    document.documentElement.classList.add('dark')
    return () => document.documentElement.classList.remove('dark')
  }, [])

  return (
    <div className="dark">
      {appPhase === 'splash' && <SplashPage />}
      {appPhase === 'setup' && <SetupPage />}
      {appPhase === 'dashboard' && <DashboardPage />}
      <Toaster />
    </div>
  )
}
