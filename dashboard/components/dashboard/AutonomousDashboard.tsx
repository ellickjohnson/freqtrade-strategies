'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { useWebSocket } from '@/lib/websocket'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Activity,
  Brain,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  Zap
} from 'lucide-react'

interface AgentStatus {
  running: boolean
  state: string
  last_run: string | null
  config: {
    interval_minutes: number
    paper_trading_only: boolean
    auto_apply_improvements: boolean
  }
  knowledge_graph: {
    entity_count: number
    relation_count: number
    finding_count: number
    decision_count: number
    pending_approvals: number
  }
  pending_approvals: number
}

interface Decision {
  id: string
  agent_type: string
  decision_type: string
  conclusion: string
  confidence: number
  created_at: string
  requires_approval: boolean
  approved_at: string | null
}

interface Finding {
  id: string
  source: string
  finding_type: string
  title: string
  content: string
  sentiment: number
  relevance: number
  confidence: number
  created_at: string
  applied_at: string | null
}

export function AutonomousDashboard() {
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [decisions, setDecisions] = useState<Decision[]>([])
  const [findings, setFindings] = useState<Finding[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const ws = useWebSocket()

  useEffect(() => {
    fetchData()

    ws.on('decision', (data: Decision) => {
      setDecisions(prev => [data, ...prev.slice(0, 49)])
    })

    ws.on('finding', (data: Finding) => {
      setFindings(prev => [data, ...prev.slice(0, 49)])
    })

    return () => {
      ws.disconnect()
    }
  }, [])

  const fetchData = async () => {
    try {
      setLoading(true)
      const [statusRes, decisionsRes, findingsRes] = await Promise.all([
        api.getAutonomousStatus(),
        api.getDecisions({ limit: 20 }),
        api.getFindings({ limit: 20 }),
      ])

      setStatus(statusRes)
      setDecisions(decisionsRes.decisions || [])
      setFindings(findingsRes.findings || [])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch data')
    } finally {
      setLoading(false)
    }
  }

  const startAgent = async () => {
    try {
      await api.startAutonomous()
      await fetchData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to start agent')
    }
  }

  const stopAgent = async () => {
    try {
      await api.stopAutonomous()
      await fetchData()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to stop agent')
    }
  }

  const getStateColor = (state: string) => {
    switch (state) {
      case 'idle': return 'bg-gray-500'
      case 'researching': return 'bg-blue-500'
      case 'analyzing': return 'bg-yellow-500'
      case 'deciding': return 'bg-purple-500'
      case 'executing': return 'bg-green-500'
      case 'error': return 'bg-red-500'
      default: return 'bg-gray-500'
    }
  }

  const getStateIcon = (state: string) => {
    switch (state) {
      case 'researching': return <Brain className="h-4 w-4" />
      case 'analyzing': return <TrendingUp className="h-4 w-4" />
      case 'deciding': return <Zap className="h-4 w-4" />
      case 'executing': return <Activity className="h-4 w-4" />
      default: return <Clock className="h-4 w-4" />
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <Activity className="h-8 w-8 animate-spin text-blue-500" />
        <span className="ml-2">Loading autonomous agent...</span>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Agent Control */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                Autonomous Agent
              </CardTitle>
              <CardDescription>
                Self-improving trading agent with LLM reasoning
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              {status?.running ? (
                <Button variant="destructive" size="sm" onClick={stopAgent}>
                  Stop Agent
                </Button>
              ) : (
                <Button variant="default" size="sm" onClick={startAgent}>
                  Start Agent
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={fetchData}>
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Status</p>
              <div className="flex items-center gap-2">
                <div className={`h-3 w-3 rounded-full ${status?.running ? 'bg-green-500' : 'bg-gray-500'}`} />
                <span className="font-medium">{status?.running ? 'Running' : 'Stopped'}</span>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">State</p>
              <div className="flex items-center gap-2">
                <Badge className={`${getStateColor(status?.state || 'idle')} text-white`}>
                  {getStateIcon(status?.state || 'idle')}
                  <span className="ml-1 capitalize">{status?.state || 'idle'}</span>
                </Badge>
              </div>
            </div>

            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Last Run</p>
              <p className="font-medium">
                {status?.last_run
                  ? new Date(status.last_run).toLocaleTimeString()
                  : 'Never'
                }
              </p>
            </div>

            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">Interval</p>
              <p className="font-medium">{status?.config.interval_minutes} min</p>
            </div>
          </div>

          {status?.config.paper_trading_only && (
            <div className="mt-4 flex items-center gap-2 text-sm text-yellow-500">
              <AlertTriangle className="h-4 w-4" />
              Paper trading only - Live trading disabled
            </div>
          )}
        </CardContent>
      </Card>

      {/* Knowledge Graph Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{status?.knowledge_graph.decision_count || 0}</div>
            <p className="text-sm text-muted-foreground">Decisions</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{status?.knowledge_graph.finding_count || 0}</div>
            <p className="text-sm text-muted-foreground">Findings</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{status?.knowledge_graph.entity_count || 0}</div>
            <p className="text-sm text-muted-foreground">Entities</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{status?.pending_approvals || 0}</div>
            <p className="text-sm text-muted-foreground">Pending</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="text-2xl font-bold">{status?.knowledge_graph.relation_count || 0}</div>
            <p className="text-sm text-muted-foreground">Relations</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent Decisions */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Decisions</CardTitle>
          <CardDescription>Latest autonomous agent decisions with reasoning</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {decisions.length === 0 ? (
              <p className="text-muted-foreground text-center py-4">No decisions yet</p>
            ) : (
              decisions.slice(0, 10).map((decision) => (
                <div key={decision.id} className="border rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{decision.agent_type}</Badge>
                      <Badge variant="secondary">{decision.decision_type}</Badge>
                      {decision.requires_approval && !decision.approved_at && (
                        <Badge variant="destructive">Needs Approval</Badge>
                      )}
                      {decision.approved_at && (
                        <Badge variant="success" className="bg-green-500 text-white">
                          <CheckCircle2 className="h-3 w-3 mr-1" />
                          Approved
                        </Badge>
                      )}
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {new Date(decision.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-sm">{decision.conclusion}</p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Confidence:</span>
                    <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-500"
                        style={{ width: `${decision.confidence * 100}%` }}
                      />
                    </div>
                    <span className="text-xs font-medium">{(decision.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>

      {/* Research Findings */}
      <Card>
        <CardHeader>
          <CardTitle>Research Findings</CardTitle>
          <CardDescription>Latest research from news, sentiment, and on-chain analysis</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {findings.length === 0 ? (
              <p className="text-muted-foreground text-center py-4">No findings yet</p>
            ) : (
              findings.slice(0, 10).map((finding) => (
                <div key={finding.id} className="border rounded-lg p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{finding.source}</Badge>
                      <Badge variant="secondary">{finding.finding_type}</Badge>
                      {finding.applied_at && (
                        <Badge variant="success" className="bg-green-500 text-white">Applied</Badge>
                      )}
                    </div>
                    <span className="text-sm text-muted-foreground">
                      {new Date(finding.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="font-medium">{finding.title}</p>
                  <p className="text-sm text-muted-foreground">{finding.content}</p>
                  <div className="flex gap-4 text-xs">
                    <span>Sentiment: {(finding.sentiment * 100).toFixed(0)}%</span>
                    <span>Relevance: {(finding.relevance * 100).toFixed(0)}%</span>
                    <span>Confidence: {(finding.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}