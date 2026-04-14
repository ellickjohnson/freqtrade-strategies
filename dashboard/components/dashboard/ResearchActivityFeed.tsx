"use client"

import { useState, useEffect } from "react"
import { api } from "@/lib/api"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { CheckCircle, Loader2, Play, Clock, CheckCheck } from "lucide-react"

interface ResearchActivityFeedProps {
  onApplySuccess?: () => void
  strategyId?: string
  strategyName?: string
}

export function ResearchActivityFeed({ onApplySuccess, strategyId, strategyName }: ResearchActivityFeedProps) {
  const [activeResearch, setActiveResearch] = useState<any[]>([])
  const [discoveries, setDiscoveries] = useState<any[]>([])
  const [history, setHistory] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [scheduled, setScheduled] = useState<any[]>([])
  const [loading, setLoading] = useState({ active: false, discoveries: false, history: false, summary: false })
  const [applying, setApplying] = useState<string | null>(null)
  const [startingResearch, setStartingResearch] = useState(false)
  const [filter, setFilter] = useState({ type: "all" })

  useEffect(() => {
    loadActive()
    loadDiscoveries()
    loadSummary()
    loadScheduled()
  }, [])

  const loadActive = async () => {
    setLoading(l => ({ ...l, active: true }))
    try {
      const data = await api.getActiveResearch()
      setActiveResearch(data.active || [])
    } catch (error) {
      console.error("Failed to load active research:", error)
    } finally {
      setLoading(l => ({ ...l, active: false }))
    }
  }

  const loadDiscoveries = async () => {
    setLoading(l => ({ ...l, discoveries: true }))
    try {
      const data = await api.getRecentDiscoveries(20)
      setDiscoveries(data.discoveries || [])
    } catch (error) {
      console.error("Failed to load discoveries:", error)
    } finally {
      setLoading(l => ({ ...l, discoveries: false }))
    }
  }

  const loadHistory = async (type?: string) => {
    setLoading(l => ({ ...l, history: true }))
    try {
      const data = await api.getResearchHistory(undefined, type !== "all" ? type : undefined, 50)
      setHistory(data.history || [])
    } catch (error) {
      console.error("Failed to load history:", error)
    } finally {
      setLoading(l => ({ ...l, history: false }))
    }
  }

  const loadSummary = async () => {
    setLoading(l => ({ ...l, summary: true }))
    try {
      const data = await api.getResearchSummary(30)
      setSummary(data)
    } catch (error) {
      console.error("Failed to load summary:", error)
    } finally {
      setLoading(l => ({ ...l, summary: false }))
    }
  }

  const loadScheduled = async () => {
    try {
      const data = await api.getScheduledResearch()
      setScheduled(data.scheduled || [])
    } catch (error) {
      console.error("Failed to load scheduled:", error)
    }
  }

  const handleStartResearch = async (strategyId: string, strategyName: string, type: string) => {
    try {
      const result = await api.startResearch({
        strategy_id: strategyId,
        strategy_name: strategyName,
        research_type: type,
        epochs: 100,
      })
      console.log("Research started:", result.research_id)
      loadActive()
    } catch (error) {
      console.error("Failed to start research:", error)
    }
  }

  const handleApplyFindings = async (researchId: string) => {
    setApplying(researchId)
    try {
      const result = await api.applyResearchFindings(researchId)
      console.log("Applied findings:", result)
      loadDiscoveries()
      onApplySuccess?.()
    } catch (error) {
      console.error("Failed to apply findings:", error)
      alert("Failed to apply findings: " + (error instanceof Error ? error.message : String(error)))
    } finally {
      setApplying(null)
    }
  }

  const handleRunResearch = async (type: string = "hyperopt") => {
    if (!strategyId) {
      alert("No strategy selected")
      return
    }
    setStartingResearch(true)
    try {
      const result = await api.startResearch({
        strategy_id: strategyId,
        strategy_name: strategyName || strategyId,
        research_type: type,
        epochs: 100,
      })
      console.log("Research started:", result.research_id)
      loadActive()
    } catch (error) {
      console.error("Failed to start research:", error)
      alert("Failed to start research: " + (error instanceof Error ? error.message : String(error)))
    } finally {
      setStartingResearch(false)
    }
  }

  const getAppliedStatus = (d: any) => {
    if (d.applied) {
      return { text: "Applied", color: "text-green-400", icon: CheckCheck }
    }
    return { text: "New", color: "text-yellow-400", icon: null }
  }

  const formatTimestamp = (ts: string) => new Date(ts).toLocaleString()

  const getResearchTypeColor = (type: string) => {
    switch (type) {
      case "hyperopt": return "bg-purple-900 text-purple-300"
      case "backtest_comparison": return "bg-blue-900 text-blue-300"
      case "parameter_sensitivity": return "bg-green-900 text-green-300"
      case "strategy_discovery": return "bg-yellow-900 text-yellow-300"
      case "market_regime": return "bg-cyan-900 text-cyan-300"
      case "feature_importance": return "bg-indigo-900 text-indigo-300"
      default: return "bg-gray-800 text-gray-300"
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running": return "text-blue-400"
      case "completed": return "text-green-400"
      case "failed": return "text-red-400"
      default: return "text-gray-400"
    }
  }

  const getImprovementColor = (pct: number) => {
    if (pct >= 5) return "text-green-400 font-bold"
    if (pct >= 2) return "text-green-400"
    if (pct > 0) return "text-yellow-400"
    return "text-red-400"
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Research & Learning</h2>
        <div className="flex items-center gap-2">
          {strategyId && (
            <Button
              size="sm"
              onClick={() => handleRunResearch("hyperopt")}
              disabled={startingResearch}
              className="gap-2"
            >
              {startingResearch ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Run Research Now
                </>
              )}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={() => { loadActive(); loadDiscoveries(); loadSummary(); }}>
            Refresh
          </Button>
        </div>
      </div>

      {summary && (
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-gray-900 rounded-lg p-4">
            <div className="text-2xl font-bold">{summary.total_runs || 0}</div>
            <div className="text-sm text-gray-400">Total Research Runs</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4">
            <div className="text-2xl font-bold text-green-400">{summary.completed || 0}</div>
            <div className="text-sm text-gray-400">Completed</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4">
            <div className="text-2xl font-bold">
              {summary.avg_improvement ? `+${(summary.avg_improvement).toFixed(1)}%` : "0%"}
            </div>
            <div className="text-sm text-gray-400">Avg Improvement</div>
          </div>
          <div className="bg-gray-900 rounded-lg p-4">
            <div className="text-2xl font-bold text-yellow-400">{summary.running || 0}</div>
            <div className="text-sm text-gray-400">Currently Running</div>
          </div>
        </div>
      )}

      {activeResearch.length > 0 && (
        <div className="bg-blue-900/20 border border-blue-500 rounded-lg p-4">
          <h3 className="font-semibold mb-3 flex items-center gap-2">
            <span className="animate-pulse">⚪</span>
            Active Research
          </h3>
          <div className="space-y-3">
            {activeResearch.map((run) => (
              <div key={run.research_id} className="bg-gray-900 rounded p-3">
                <div className="flex items-start justify-between mb-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-xs px-2 py-0.5 rounded ${getResearchTypeColor(run.research_type)}`}>
                        {run.research_type}
                      </span>
                      <span className="text-sm font-mono">{run.strategy_name}</span>
                    </div>
                    <div className="text-xs text-gray-400">{run.hypothesis}</div>
                  </div>
                  <span className={`text-xs ${getStatusColor(run.status)}`}>
                    {run.status.toUpperCase()}
                  </span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2 mb-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full"
                    style={{ width: `${(run.epochs_completed / run.total_epochs) * 100}%` }}
                  />
                </div>
                <div className="text-xs text-gray-400 grid grid-cols-4 gap-4">
                  <div>Epoch: {run.epochs_completed}/{run.total_epochs}</div>
                  <div>Best Score: {run.current_best_score?.toFixed(4) || 0}</div>
                  <div>Started: {formatTimestamp(run.start_time)}</div>
                  <div>GPU Hours: {run.gpu_hours_used?.toFixed(2) || 0}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <Tabs defaultValue="discoveries" className="w-full">
        <TabsList className="grid w-full grid-cols-3">
          <TabsTrigger value="discoveries">Recent Discoveries</TabsTrigger>
          <TabsTrigger value="history">Research History</TabsTrigger>
          <TabsTrigger value="scheduled">Scheduled Research</TabsTrigger>
        </TabsList>

        <TabsContent value="discoveries" className="space-y-3">
          {loading.discoveries ? (
            <div className="text-center py-8 text-gray-400">Loading discoveries...</div>
          ) : discoveries.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              No discoveries yet. Research improvements will appear here.
            </div>
          ) : (
            <div className="space-y-3">
              {discoveries.map((d) => {
                const appliedStatus = getAppliedStatus(d)
                const AppliedIcon = appliedStatus.icon
                return (
                <div key={d.research_id} className="bg-gray-900 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs px-2 py-0.5 rounded ${getResearchTypeColor(d.research_type)}`}>
                          {d.research_type}
                        </span>
                        <span className="font-mono">{d.strategy_name}</span>
                        {AppliedIcon && (
                          <span className={`text-xs flex items-center gap-1 ${appliedStatus.color}`}>
                            <AppliedIcon className="h-3 w-3" />
                            {appliedStatus.text}
                          </span>
                        )}
                      </div>
                      <div className="text-sm font-semibold">{d.hypothesis}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <div className={`text-lg font-bold ${getImprovementColor(d.improvement)}`}>
                        +{d.improvement?.toFixed(1)}%
                      </div>
                      {d.applied && d.applied_at && (
                        <span className="text-xs text-gray-500">
                          {new Date(d.applied_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="text-sm text-gray-300 mb-2">{d.conclusion}</div>
                  {d.best_params && Object.keys(d.best_params).length > 0 && (
                    <details className="text-xs">
                      <summary className="cursor-pointer text-gray-400 hover:text-gray-200 mb-1">
                        Best Parameters Found
                      </summary>
                      <pre className="p-2 bg-black/50 rounded overflow-auto">
                        {JSON.stringify(d.best_params, null, 2)}
                      </pre>
                    </details>
                  )}
                  <div className="text-xs text-gray-400 mt-2">
                    Completed: {formatTimestamp(d.completed_at)}
                  </div>
                  {d.recommendations && d.recommendations.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-800">
                      <div className="text-xs font-semibold text-gray-400 mb-1">Recommendations:</div>
                      <ul className="list-disc list-inside text-xs space-y-1">
                        {d.recommendations.map((rec: string, i: number) => (
                          <li key={i} className="text-gray-300">{rec}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {!d.applied && (
                    <div className="mt-3 pt-3 border-t border-gray-800">
                      <Button
                        size="sm"
                        onClick={() => handleApplyFindings(d.research_id)}
                        disabled={applying === d.research_id}
                        className="gap-2"
                      >
                        {applying === d.research_id ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Applying...
                          </>
                        ) : (
                          <>
                            <CheckCircle className="h-4 w-4" />
                            Apply Findings
                          </>
                        )}
                      </Button>
                      <span className="text-xs text-gray-500 ml-3">
                        Updates strategy params & restarts if running
                      </span>
                    </div>
                  )}
                </div>
              )})}
            </div>
          )}
        </TabsContent>

        <TabsContent value="history" className="space-y-3">
          <div className="mb-4">
            <Select value={filter.type} onValueChange={v => { setFilter(f => ({ ...f, type: v })); loadHistory(v); }}>
              <SelectTrigger className="w-48">
                <SelectValue placeholder="Filter by type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="hyperopt">Hyperopt</SelectItem>
                <SelectItem value="backtest_comparison">Backtest Comparison</SelectItem>
                <SelectItem value="parameter_sensitivity">Parameter Sensitivity</SelectItem>
                <SelectItem value="strategy_discovery">Strategy Discovery</SelectItem>
                <SelectItem value="market_regime">Market Regime</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {loading.history ? (
            <div className="text-center py-8 text-gray-400">Loading history...</div>
          ) : history.length === 0 ? (
            <div className="text-center py-8 text-gray-400">No research history yet.</div>
          ) : (
            <div className="overflow-auto max-h-96">
              <table className="w-full text-sm">
                <thead className="text-gray-400 text-xs sticky top-0 bg-gray-900">
                  <tr>
                    <th className="text-left p-2">Started</th>
                    <th className="text-left p-2">Type</th>
                    <th className="text-left p-2">Strategy</th>
                    <th className="text-left p-2">Hypothesis</th>
                    <th className="text-left p-2">Status</th>
                    <th className="text-right p-2">Improvement</th>
                  </tr>
                </thead>
                <tbody>
                  {history.map((h) => (
                    <tr key={h.research_id} className="border-t border-gray-800 hover:bg-gray-800/50">
                      <td className="p-2 font-mono text-xs">{formatTimestamp(h.start_time)}</td>
                      <td className="p-2">
                        <span className={`text-xs px-2 py-0.5 rounded ${getResearchTypeColor(h.research_type)}`}>
                          {h.research_type}
                        </span>
                      </td>
                      <td className="p-2 font-mono text-xs">{h.strategy_name}</td>
                      <td className="p-2 text-xs max-w-xs truncate">{h.hypothesis}</td>
                      <td className={`p-2 ${getStatusColor(h.status)}`}>
                        {h.status.toUpperCase()}
                      </td>
                      <td className={`p-2 text-right font-mono ${getImprovementColor(h.improvement_pct || 0)}`}>
                        {h.improvement_pct ? `+${h.improvement_pct.toFixed(1)}%` : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="scheduled" className="space-y-3">
          {scheduled.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              No scheduled research. The system will automatically run research based on schedules.
            </div>
          ) : (
            <div className="space-y-2">
              {scheduled.map((s) => (
                <div key={s.schedule_id} className="bg-gray-900 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${getResearchTypeColor(s.research_type)}`}>
                        {s.research_type}
                      </span>
                      <span className="text-xs text-gray-400">Every {s.frequency}</span>
                    </div>
                    <span className={`text-xs ${s.enabled ? "text-green-400" : "text-gray-400"}`}>
                      {s.enabled ? "Enabled" : "Disabled"}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400 mt-2">
                    Next run: {formatTimestamp(s.next_run)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}