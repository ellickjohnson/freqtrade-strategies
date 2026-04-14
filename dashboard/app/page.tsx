'use client'

import { useEffect, useState } from "react"
import { useStrategyStore } from '@/lib/store'
import { api } from '@/lib/api'
import { useWebSocket } from '@/lib/websocket'
import PLSummary from '@/components/dashboard/PLSummary'
import StrategyGrid from '@/components/dashboard/StrategyGrid'
import { ResearchActivityFeed } from '@/components/dashboard/ResearchActivityFeed'
import { SettingsPage } from '@/components/dashboard/SettingsPage'
import { AutonomousDashboard } from '@/components/dashboard/AutonomousDashboard'
import { ApprovalQueue } from '@/components/dashboard/ApprovalQueue'
import { RiskDashboard } from '@/components/dashboard/RiskDashboard'
import { MemorySearch } from '@/components/dashboard/MemorySearch'
import { ActivityStream } from '@/components/dashboard/ActivityStream'
import { Settings, LayoutDashboard, RefreshCw, Brain, Shield, CheckSquare, FileSearch, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function HomePage() {
  const [activeView, setActiveView] = useState<'dashboard' | 'activity' | 'autonomous' | 'approvals' | 'risk' | 'memory' | 'settings'>('dashboard')
  const { setStrategies, setPortfolio, setLoading, setError } = useStrategyStore()
  const ws = useWebSocket()
  
  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true)
        const [strategiesData, portfolioData] = await Promise.all([
          api.getStrategies(),
          api.getPortfolio(),
        ])
        setStrategies(strategiesData.strategies)
        setPortfolio(portfolioData)
      } catch (error) {
        setError({ message: error instanceof Error ? error.message : 'Failed to fetch data' })
      } finally {
        setLoading(false)
      }
    }
    
    fetchData()
  }, [setStrategies, setPortfolio, setLoading, setError])
  
  useEffect(() => {
    ws.on('connected', () => {
      console.log('WebSocket connected')
    })
    
    ws.on('trade', (data) => {
      console.log('Trade update:', data)
    })
    
    ws.on('status', (data) => {
      console.log('Status update:', data)
    })
    
    return () => {
      ws.disconnect()
    }
  }, [ws])

  const handleRefresh = async () => {
    setLoading(true)
    try {
      const [strategiesData, portfolioData] = await Promise.all([
        api.getStrategies(),
        api.getPortfolio(),
      ])
      setStrategies(strategiesData.strategies)
      setPortfolio(portfolioData)
    } catch (error) {
      setError({ message: error instanceof Error ? error.message : 'Failed to fetch data' })
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div className="min-h-screen bg-slate-950">
      {/* Navigation Header */}
      <header className="sticky top-0 z-50 bg-slate-900/80 backdrop-blur border-b border-slate-800">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="text-xl font-bold text-slate-50">Freqtrade Dashboard</h1>
            <nav className="flex items-center gap-2">
              <Button
                variant={activeView === 'dashboard' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('dashboard')}
                className="gap-2"
              >
                <LayoutDashboard className="h-4 w-4" />
                Dashboard
              </Button>
              <Button
                variant={activeView === 'activity' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('activity')}
                className="gap-2"
              >
                <Activity className="h-4 w-4" />
                Activity
              </Button>
              <Button
                variant={activeView === 'autonomous' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('autonomous')}
                className="gap-2"
              >
                <Brain className="h-4 w-4" />
                Autonomous
              </Button>
              <Button
                variant={activeView === 'approvals' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('approvals')}
                className="gap-2"
              >
                <CheckSquare className="h-4 w-4" />
                Approvals
              </Button>
              <Button
                variant={activeView === 'risk' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('risk')}
                className="gap-2"
              >
                <Shield className="h-4 w-4" />
                Risk
              </Button>
              <Button
                variant={activeView === 'memory' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('memory')}
                className="gap-2"
              >
                <FileSearch className="h-4 w-4" />
                Memory
              </Button>
              <Button
                variant={activeView === 'settings' ? 'default' : 'ghost'}
                size="sm"
                onClick={() => setActiveView('settings')}
                className="gap-2"
              >
                <Settings className="h-4 w-4" />
                Settings
              </Button>
            </nav>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={handleRefresh} className="gap-2">
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      {activeView === 'dashboard' && (
        <div className="container mx-auto px-4 py-8">
          <PLSummary />
          <div className="mt-8">
            <StrategyGrid />
          </div>
          <div className="mt-12">
            <ResearchActivityFeed onApplySuccess={handleRefresh} />
          </div>
        </div>
      )}

      {activeView === 'activity' && (
        <div className="container mx-auto px-4 py-8">
          <ActivityStream />
        </div>
      )}

      {activeView === 'autonomous' && (
        <div className="container mx-auto px-4 py-8">
          <AutonomousDashboard />
        </div>
      )}

      {activeView === 'approvals' && (
        <div className="container mx-auto px-4 py-8">
          <ApprovalQueue />
        </div>
      )}

      {activeView === 'risk' && (
        <div className="container mx-auto px-4 py-8">
          <RiskDashboard />
        </div>
      )}

      {activeView === 'memory' && (
        <div className="container mx-auto px-4 py-8">
          <MemorySearch />
        </div>
      )}

      {activeView === 'settings' && (
        <div className="container mx-auto px-4 py-8">
          <SettingsPage />
        </div>
      )}
    </div>
  )
}