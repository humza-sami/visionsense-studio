import { useStore } from '@/store/useStore'
import { SplashPage } from '@/pages/SplashPage'
import { SetupPage } from '@/pages/SetupPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { Toaster } from '@/components/ui/toaster'

export default function App() {
  const appPhase = useStore((s) => s.appPhase)

  return (
    <div className="dark">
      {appPhase === 'splash' && <SplashPage />}
      {appPhase === 'setup' && <SetupPage />}
      {appPhase === 'dashboard' && <DashboardPage />}
      <Toaster />
    </div>
  )
}
