'use client'

import { useState, useEffect } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Activity, Loader2, Brain, Search, TrendingUp, AlertCircle,
  CheckCircle, Zap, Clock, Filter, RefreshCw
} from 'lucide-react'

interface ActivityEvent {
  id: string
  activity_type: string
  agent: string
  title: string
  message: string
  details: Record<string, any>
  timestamp: string
  progress?: number
}

interface ActivityStreamProps {
  maxHeight?: string
  showFilters?: boolean
  agentFilter?: string
}

export function ActivityStream({ maxHeight = '600px', showFilters = true, agentFilter }: ActivityStreamProps) {
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [filter, setFilter] = useState<string | null>(agentFilter || null)

  const loadActivity = async () => {
    try {
      setLoading(true)
      const data = await api.getActivity({
        limit: 100,
        since_hours: 24,
        agent: filter || undefined,
      })
      setEvents(data.events || [])
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load activity')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadActivity()
  }, [filter])

  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(loadActivity, 5000) // Refresh every 5 seconds
      return () => clearInterval(interval)
    }
  }, [autoRefresh, filter])

  const getActivityIcon = (type: string) => {
    switch (type) {
      case 'research_start':
      case 'research_progress':
      case 'research_finding':
      case 'research_complete':
        return <Search className="h-4 w-4 text-purple-400" />
      case 'analysis_start':
      case 'analysis_progress':
      case 'analysis_complete':
        return <Brain className="h-4 w-4 text-blue-400" />
      case 'decision_made':
        return <CheckCircle className="h-4 w-4 text-green-400" />
      case 'hyperopt_start':
      case 'hyperopt_progress':
      case 'hyperopt_epoch':
      case 'hyperopt_complete':
        return <TrendingUp className="h-4 w-4 text-orange-400" />
      case 'error':
        return <AlertCircle className="h-4 w-4 text-red-400" />
      default:
        return <Activity className="h-4 w-4 text-slate-400" />
    }
  }

  const getActivityColor = (type: string) => {
    switch (type) {
      case 'research_start':
      case 'research_progress':
      case 'research_finding':
        return 'bg-purple-500/10 border-purple-500/30'
      case 'research_complete':
        return 'bg-green-500/10 border-green-500/30'
      case 'analysis_start':
      case 'analysis_progress':
        return 'bg-blue-500/10 border-blue-500/30'
      case 'analysis_complete':
        return 'bg-green-500/10 border-green-500/30'
      case 'decision_made':
        return 'bg-green-500/10 border-green-500/30'
      case 'hyperopt_start':
      case 'hyperopt_progress':
      case 'hyperopt_epoch':
        return 'bg-orange-500/10 border-orange-500/30'
      case 'hyperopt_complete':
        return 'bg-green-500/10 border-green-500/30'
      case 'error':
        return 'bg-red-500/10 border-red-500/30'
      default:
        return 'bg-slate-500/10 border-slate-500/30'
    }
  }

  const formatTimestamp = (ts: string) => {
    try {
      let date = new Date(ts)
      if (isNaN(date.getTime())) return ts
      if (!ts.endsWith('Z') && !ts.includes('+') && !/\d{2}:\d{2}\s/.test(ts)) {
        date = new Date(ts + 'Z')
      }
      return date.toLocaleString('en-US', {
        timeZone: 'America/Denver',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
      })
    } catch {
      return ts
    }
  }

  const getProgressColor = (progress?: number) => {
    if (!progress) return ''
    if (progress < 0.3) return 'bg-red-500'
    if (progress < 0.7) return 'bg-yellow-500'
    return 'bg-green-500'
  }

  const agents = ['ResearchAgent', 'AnalysisAgent', 'RiskAgent', 'StrategyAgent', 'OrchestratorAgent', 'test']

  if (loading && events.length === 0) {
    return (
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
          <span className="ml-2 text-slate-400">Loading activity...</span>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-slate-50 flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Activity Stream
            </CardTitle>
            <CardDescription>
              Real-time agent activity and research progress
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant={autoRefresh ? 'default' : 'outline'}
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className="gap-1"
            >
              <Zap className={`h-3 w-3 ${autoRefresh ? 'text-yellow-400' : ''}`} />
              Auto
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={loadActivity}
              disabled={loading}
              className="gap-1"
            >
              <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </div>

        {showFilters && (
          <div className="flex flex-wrap gap-2 mt-3">
            <Badge
              variant={filter === null ? 'default' : 'outline'}
              className={`cursor-pointer ${
                filter === null ? 'bg-blue-600' : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
              }`}
              onClick={() => setFilter(null)}
            >
              All
            </Badge>
            {agents.map((agent) => (
              <Badge
                key={agent}
                variant={filter === agent ? 'default' : 'outline'}
                className={`cursor-pointer ${
                  filter === agent ? 'bg-blue-600' : 'bg-slate-800 border-slate-700 hover:bg-slate-700'
                }`}
                onClick={() => setFilter(agent)}
              >
                {agent}
              </Badge>
            ))}
          </div>
        )}
      </CardHeader>

      <CardContent>
        {error && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 mb-4">
            {error}
          </div>
        )}

        <div
          className="space-y-3 overflow-y-auto pr-2"
          style={{ maxHeight }}
        >
          {events.length === 0 && !loading && (
            <div className="text-center py-8 text-slate-400">
              No activity events in the last 24 hours.
              <br />
              <span className="text-sm">
                Agent activities will appear here when research or analysis is running.
              </span>
            </div>
          )}

          {events.map((event) => (
            <div
              key={event.id}
              className={`p-3 rounded-lg border ${getActivityColor(event.activity_type)}`}
            >
              <div className="flex items-start gap-3">
                <div className="mt-0.5">
                  {getActivityIcon(event.activity_type)}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-slate-100 text-sm">
                        {event.title}
                      </span>
                      <Badge variant="outline" className="text-xs">
                        {event.agent}
                      </Badge>
                    </div>
                    <span className="text-xs text-slate-400 flex items-center gap-1 whitespace-nowrap">
                      <Clock className="h-3 w-3" />
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>

                  <p className="text-sm text-slate-300 mt-1 line-clamp-2">
                    {event.message}
                  </p>

                  {event.progress !== undefined && event.progress !== null && (
                    <div className="mt-2">
                      <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                        <span>Progress</span>
                        <span>{Math.round(event.progress * 100)}%</span>
                      </div>
                      <div className="w-full bg-slate-700 rounded-full h-1.5">
                        <div
                          className={`h-1.5 rounded-full transition-all ${getProgressColor(event.progress)}`}
                          style={{ width: `${event.progress * 100}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {event.details && Object.keys(event.details).length > 0 && (
                    <details className="mt-2">
                      <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-200">
                        View details
                      </summary>
                      <pre className="mt-2 p-2 bg-black/30 rounded text-xs overflow-x-auto">
                        {JSON.stringify(event.details, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}