'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  CheckCircle2,
  XCircle,
  Clock,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Loader2
} from 'lucide-react'

interface Approval {
  id: string
  agent_type: string
  decision_type: string
  context: Record<string, any>
  reasoning_chain: string[]
  conclusion: string
  confidence: number
  created_at: string
  requires_approval: boolean
}

interface ApprovalQueueProps {
  onApprove?: (id: string) => void
  onReject?: (id: string) => void
}

export function ApprovalQueue({ onApprove, onReject }: ApprovalQueueProps) {
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [loading, setLoading] = useState(true)
  const [processing, setProcessing] = useState<string | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchApprovals()
    const interval = setInterval(fetchApprovals, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const fetchApprovals = async () => {
    try {
      const data = await api.getPendingApprovals()
      setApprovals(data.approvals || [])
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch approvals')
    } finally {
      setLoading(false)
    }
  }

  const handleApprove = async (id: string) => {
    try {
      setProcessing(id)
      await api.approveDecision(id, 'Approved via dashboard')
      setApprovals(prev => prev.filter(a => a.id !== id))
      onApprove?.(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to approve')
    } finally {
      setProcessing(null)
    }
  }

  const handleReject = async (id: string, reason: string) => {
    try {
      setProcessing(id)
      await api.rejectDecision(id, reason)
      setApprovals(prev => prev.filter(a => a.id !== id))
      onReject?.(id)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reject')
    } finally {
      setProcessing(null)
    }
  }

  const getDecisionTypeColor = (type: string) => {
    const colors: Record<string, string> = {
      'adjust_parameters': 'bg-blue-500',
      'run_hyperopt': 'bg-purple-500',
      'apply_research': 'bg-green-500',
      'create_strategy': 'bg-cyan-500',
      'stop_strategy': 'bg-red-500',
      'deprecate_strategy': 'bg-orange-500',
      'promote_strategy': 'bg-emerald-500',
      'alert_user': 'bg-yellow-500',
    }
    return colors[type] || 'bg-gray-500'
  }

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.8) return 'text-green-500'
    if (confidence >= 0.6) return 'text-yellow-500'
    return 'text-red-500'
  }

  const formatDecisionType = (type: string) => {
    return type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span className="ml-2">Loading approvals...</span>
        </CardContent>
      </Card>
    )
  }

  if (approvals.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 text-green-500" />
            Approval Queue
          </CardTitle>
          <CardDescription>No pending approvals</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8 text-muted-foreground">
            <CheckCircle2 className="h-12 w-12 mx-auto mb-2 text-green-500" />
            <p>All caught up! No decisions pending approval.</p>
          </div>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500" />
            Approval Queue
          </div>
          <Badge variant="destructive">{approvals.length} pending</Badge>
        </CardTitle>
        <CardDescription>
          Autonomous agent decisions requiring your approval
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {approvals.map((approval) => (
            <div key={approval.id} className="border rounded-lg p-4">
              <div className="flex items-start justify-between">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2">
                    <Badge className={`${getDecisionTypeColor(approval.decision_type)} text-white`}>
                      {formatDecisionType(approval.decision_type)}
                    </Badge>
                    <Badge variant="outline">{approval.agent_type}</Badge>
                    <span className="text-sm text-muted-foreground">
                      {new Date(approval.created_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="font-medium">{approval.conclusion}</p>
                </div>
                <div className={`text-sm font-medium ${getConfidenceColor(approval.confidence)}`}>
                  {(approval.confidence * 100).toFixed(0)}% confidence
                </div>
              </div>

              {/* Expandable Reasoning */}
              <div className="mt-3">
                <button
                  className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
                  onClick={() => setExpandedId(expandedId === approval.id ? null : approval.id)}
                >
                  {expandedId === approval.id ? (
                    <>
                      <ChevronUp className="h-4 w-4" />
                      Hide reasoning
                    </>
                  ) : (
                    <>
                      <ChevronDown className="h-4 w-4" />
                      Show reasoning
                    </>
                  )}
                </button>

                {expandedId === approval.id && (
                  <div className="mt-2 p-3 bg-slate-50 dark:bg-slate-900 rounded-md">
                    <p className="text-sm font-medium mb-2">Reasoning Chain:</p>
                    <ol className="list-decimal list-inside space-y-1">
                      {approval.reasoning_chain.map((step, i) => (
                        <li key={i} className="text-sm text-muted-foreground">{step}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>

              {/* Context Summary */}
              {approval.context && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {approval.context.strategy_id && (
                    <span className="mr-3">Strategy: {approval.context.strategy_id.slice(0, 8)}...</span>
                  )}
                  {approval.context.improvement_pct !== undefined && (
                    <span className="mr-3">Improvement: {approval.context.improvement_pct.toFixed(1)}%</span>
                  )}
                </div>
              )}

              {/* Action Buttons */}
              <div className="mt-4 flex gap-2">
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="default"
                      size="sm"
                      className="bg-green-500 hover:bg-green-600"
                      disabled={processing === approval.id}
                    >
                      {processing === approval.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <CheckCircle2 className="h-4 w-4 mr-1" />
                      )}
                      Approve
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Approve Decision?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will execute the decision: {formatDecisionType(approval.decision_type)}
                        <br /><br />
                        {approval.conclusion}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction onClick={() => handleApprove(approval.id)}>
                        Approve
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      variant="destructive"
                      size="sm"
                      disabled={processing === approval.id}
                    >
                      <XCircle className="h-4 w-4 mr-1" />
                      Reject
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Reject Decision?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will reject the decision and prevent it from executing.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => handleReject(approval.id, 'Rejected via dashboard')}
                        className="bg-red-500 hover:bg-red-600"
                      >
                        Reject
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}