import { Cpu, Layers3 } from 'lucide-react'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { FeatureToggles } from '@/components/features/FeatureToggles'
import { ApplicationToggles } from '@/components/applications/ApplicationToggles'

export function RightSidebar() {
  return (
    <div className="flex flex-col h-full bg-[#111118] border-l border-border/60 overflow-hidden">
      <ScrollArea className="flex-1 scrollbar-thin">
        <div className="p-3 space-y-4">

          {/* Features Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1">
              <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-[10px] font-semibold text-muted-foreground tracking-wider">FEATURES</span>
            </div>
            <FeatureToggles />
          </div>

          <Separator className="opacity-40" />

          {/* Applications Section */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 px-1">
              <Layers3 className="w-3.5 h-3.5 text-muted-foreground" />
              <span className="text-[10px] font-semibold text-muted-foreground tracking-wider">APPLICATIONS</span>
            </div>
            <ApplicationToggles />
          </div>

        </div>
      </ScrollArea>
    </div>
  )
}
