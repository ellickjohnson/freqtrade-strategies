"use client"

import { useState, useEffect } from "react"
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Strategy, Trade } from "@/lib/types"
import { api } from "@/lib/api"
import { formatCurrency, formatPercent } from "@/lib/utils"
import { LogViewer } from "./LogViewer"
import { FreqAIInsightsPanel } from "./FreqAIInsightsPanel"
import { Brain, Loader2, RefreshCw } from "lucide-react"

interface StrategyDetailModalProps {
  strategy: Strategy | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onUpdate?: () => void
}

export function StrategyDetailModal({ strategy, open, onOpenChange, onUpdate }: StrategyDetailModalProps) {
  const [activeTab, setActiveTab] = useState("overview")
  const [trades, setTrades] = useState<Trade[]>([])
  const [containerLogs, setContainerLogs] = useState<string[]>([])
  const [reasoningLogs, setReasoningLogs] = useState<any[]>([])
  const [decisions, setDecisions] = useState<any[]>([])
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [loading, setLoading] = useState({ trades: false, logs: false, freqai: false, reasoning: false, decisions: false })
  const [freqaiModel, setFreqaiModel] = useState("lightgbm")
  const [freqaiEnabled, setFreqaiEnabled] = useState(false)

  useEffect(() => {
    if (strategy && open) {
      loadTrades()
      loadLogs()
      loadReasoning()
      loadDecisions()
      setFreqaiEnabled(strategy.use_freqai || false)
    }
  }, [strategy, open])

  const loadTrades = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, trades: true }))
    try {
      const result = await api.getStrategyTrades(strategy.id, "all", 50)
      setTrades(result.trades || [])
    } catch (error) {
      console.error("Failed to load trades:", error)
    } finally {
      setLoading(l => ({ ...l, trades: false }))
      setLastRefresh(new Date())
    }
  }

  const loadLogs = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, logs: true }))
    try {
      const result = await api.getStrategyLogs(strategy.id, 100)
      setContainerLogs(result.logs || [])
    } catch (error) {
      console.error("Failed to load logs:", error)
    } finally {
      setLoading(l => ({ ...l, logs: false }))
    }
  }

  const loadReasoning = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, reasoning: true }))
    try {
      const result = await api.getStrategyReasoning(strategy.id, 24, 100)
      setReasoningLogs(result.logs || [])
    } catch (error) {
      console.error("Failed to load reasoning:", error)
    } finally {
      setLoading(l => ({ ...l, reasoning: false }))
      setLastRefresh(new Date())
    }
  }

  const loadDecisions = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, decisions: true }))
    try {
      const result = await api.getDecisions({ limit: 50, since_hours: 72 })
      const filtered = (result.decisions || []).filter(
        (d: any) => {
          const target = d.metadata?.target || d.context?.strategies?.[0] || ""
          return target === strategy.id || JSON.stringify(d.context || {}).includes(strategy.id)
        }
      )
      setDecisions(filtered)
    } catch (error) {
      console.error("Failed to load decisions:", error)
    } finally {
      setLoading(l => ({ ...l, decisions: false }))
    }
  }

  const handleRefresh = async () => {
    await Promise.all([loadTrades(), loadLogs(), loadReasoning(), loadDecisions()])
  }

  const handleEnableFreqAI = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, freqai: true }))
    try {
      await api.enableFreqAI(strategy.id, { model: freqaiModel, train_period_days: 90, backtest_period_days: 7 })
      setFreqaiEnabled(true)
      onUpdate?.()
    } catch (error) {
      console.error("Failed to enable FreqAI:", error)
    } finally {
      setLoading(l => ({ ...l, freqai: false }))
    }
  }

  const handleDisableFreqAI = async () => {
    if (!strategy) return
    setLoading(l => ({ ...l, freqai: true }))
    try {
      await api.disableFreqAI(strategy.id)
      setFreqaiEnabled(false)
      onUpdate?.()
    } catch (error) {
      console.error("Failed to disable FreqAI:", error)
    } finally {
      setLoading(l => ({ ...l, freqai: false }))
    }
  }

  if (!strategy) return null

  const formatDate = (date: string) =>
    new Date(date).toLocaleString()

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running": return "text-green-500"
      case "stopped": return "text-red-500"
      case "error": return "text-yellow-500"
      default: return "text-gray-500"
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[90vh] overflow-hidden">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-xl font-bold flex items-center gap-3">
              <span>{strategy.name}</span>
              <span className={`text-sm font-normal ${getStatusColor(strategy.status)}`}>
                {strategy.status.toUpperCase()}
              </span>
            </DialogTitle>
            <div className="flex items-center gap-3">
              {lastRefresh && (
                <span className="text-xs text-gray-400">
                  Last refresh: {lastRefresh.toLocaleTimeString()}
                </span>
              )}
              <Button variant="outline" size="sm" onClick={handleRefresh}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="h-full flex flex-col">
          <TabsList className="grid w-full grid-cols-6">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="reasoning">Reasoning</TabsTrigger>
            <TabsTrigger value="trades">Trades</TabsTrigger>
            <TabsTrigger value="freqai">FreqAI</TabsTrigger>
            <TabsTrigger value="logs">Container Logs</TabsTrigger>
            <TabsTrigger value="backtest">Backtest</TabsTrigger>
          </TabsList>

          <div className="flex-1 overflow-auto mt-4">
            <TabsContent value="overview" className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="space-y-2">
                  <h3 className="font-semibold text-sm text-gray-500">Configuration</h3>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Strategy:</span>
                      <span className="font-mono">{strategy.strategy_file}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Exchange:</span>
                      <span className="font-mono uppercase">{strategy.exchange}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Timeframe:</span>
                      <span className="font-mono">{strategy.timeframe}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Max Trades:</span>
                      <span className="font-mono">{strategy.max_open_trades}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Stake:</span>
                      <span className="font-mono">{formatCurrency(strategy.stake_amount)}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Stop Loss:</span>
                      <span className="font-mono text-red-400">{(strategy.stoploss * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                </div>

                <div className="space-y-2">
                  <h3 className="font-semibold text-sm text-gray-500">Pairs</h3>
                  <div className="flex flex-wrap gap-1">
                    {strategy.pairs.map(pair => (
                      <span key={pair} className="px-2 py-1 bg-gray-800 rounded text-xs font-mono">
                        {pair}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <h3 className="font-semibold text-sm text-gray-500">Performance</h3>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Win Rate:</span>
                      <span className="font-mono">{strategy.win_rate != null ? formatPercent(strategy.win_rate, 0) : '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Total P&amp;L:</span>
                      <span className="font-mono">{strategy.profit_pct != null ? formatCurrency(strategy.profit_pct) : '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Sharpe Ratio:</span>
                      <span className="font-mono">{strategy.sharpe != null ? strategy.sharpe.toFixed(2) : '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Max Drawdown:</span>
                      <span className="font-mono">{strategy.max_drawdown != null ? formatPercent(strategy.max_drawdown, 0) : '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Total Trades:</span>
                      <span className="font-mono">{strategy.total_trades ?? '--'}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Open Trades:</span>
                      <span className="font-mono">{trades.filter(t => t.is_open).length}</span>
                    </div>
                  </div>
                </div>
              </div>

              {strategy.container_status && (
                <div className="mt-4 p-3 bg-gray-900 rounded-lg">
                  <h3 className="font-semibold text-sm text-gray-500 mb-2">Container Status</h3>
                  <div className="grid grid-cols-3 gap-4 text-sm">
                    <div>
                      <span className="text-gray-400">Container ID:</span>
                      <div className="font-mono text-xs truncate">{strategy.container_status.container_id}</div>
                    </div>
                    <div>
                      <span className="text-gray-400">Port:</span>
                      <div className="font-mono">{strategy.docker_port}</div>
                    </div>
                    <div>
                      <span className="text-gray-400">Status:</span>
                      <div className={`font-mono ${getStatusColor(strategy.container_status.status)}`}>
                        {strategy.container_status.status}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {strategy.custom_params && Object.keys(strategy.custom_params).length > 0 && (
                <div className="mt-4">
                  <h3 className="font-semibold text-sm text-gray-500 mb-2">Custom Parameters</h3>
                  <div className="p-3 bg-gray-900 rounded-lg">
                    <pre className="text-xs font-mono overflow-auto">
                      {JSON.stringify(strategy.custom_params, null, 2)}
                    </pre>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="reasoning">
              <div className="space-y-4">
                <h3 className="font-semibold text-sm text-gray-500">Autonomous Agent Decisions</h3>
                {loading.decisions ? (
                  <div className="text-center py-8 text-gray-400">Loading decisions...</div>
                ) : decisions.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">No autonomous decisions for this strategy yet</div>
                ) : (
                  <div className="space-y-3">
                    {decisions.map((decision: any) => {
                      const decisionType = decision.decision_type || "unknown"
                      const confidence = decision.confidence ?? 0
                      const reasoning = decision.reasoning_chain?.join("\n→ ") || decision.conclusion || ""
                      const outcome = decision.outcome || "pending"
                      const timestamp = decision.timestamp || decision.created_at || ""
                      const params = decision.metadata?.parameters || {}
                      const target = decision.metadata?.target || ""

                      const getTypeColor = (type: string) => {
                        switch (type) {
                          case "adjust_parameters": return "bg-blue-500/20 text-blue-400 border-blue-500/30"
                          case "run_hyperopt": return "bg-purple-500/20 text-purple-400 border-purple-500/30"
                          case "stop_strategy": return "bg-red-500/20 text-red-400 border-red-500/30"
                          case "no_action": return "bg-gray-500/20 text-gray-400 border-gray-500/30"
                          case "create_strategy": return "bg-green-500/20 text-green-400 border-green-500/30"
                          default: return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30"
                        }
                      }

                      return (
                        <div key={decision.id} className="p-3 bg-gray-900 rounded-lg border border-gray-800">
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-xs font-medium border ${getTypeColor(decisionType)}`}>
                                {decisionType.replace(/_/g, " ")}
                              </span>
                              <span className="text-xs text-gray-500">
                                {confidence ? `${(confidence * 100).toFixed(0)}% confidence` : ""}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className={`px-2 py-0.5 rounded text-xs ${
                                outcome.includes("success") || outcome.includes("adjusted") || outcome.includes("applied")
                                  ? "bg-green-500/20 text-green-400"
                                  : outcome.includes("pending")
                                  ? "bg-yellow-500/20 text-yellow-400"
                                  : "bg-gray-500/20 text-gray-400"
                              }`}>
                                {outcome}
                              </span>
                              {timestamp && (
                                <span className="text-xs text-gray-500">
                                  {new Date(timestamp).toLocaleString()}
                                </span>
                              )}
                            </div>
                          </div>
                          {reasoning && (
                            <p className="text-sm text-gray-300 mb-2 whitespace-pre-wrap">{reasoning}</p>
                          )}
                          {Object.keys(params).length > 0 && (
                            <div className="mt-2 p-2 bg-gray-800 rounded text-xs font-mono">
                              <span className="text-gray-500 mr-1">params:</span>
                              {Object.entries(params).map(([k, v]) => (
                                <span key={k} className="mr-3">
                                  <span className="text-blue-400">{k}</span>=<span className="text-green-400">{JSON.stringify(v)}</span>
                                </span>
                              ))}
                            </div>
                          )}
                          {target && target !== strategy?.id && (
                            <p className="text-xs text-gray-500 mt-1">target: {target}</p>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

                {reasoningLogs.length > 0 && (
                  <>
                    <h3 className="font-semibold text-sm text-gray-500 mt-4">Agent Reasoning Logs</h3>
                    <LogViewer strategyId={strategy.id} category="reasoning" />
                  </>
                )}
              </div>
            </TabsContent>

            <TabsContent value="trades" className="space-y-2">
              {loading.trades ? (
                <div className="text-center py-8 text-gray-400">Loading trades...</div>
              ) : trades.length === 0 ? (
                <div className="text-center py-8 text-gray-400">No trades yet</div>
              ) : (
                <div className="overflow-auto max-h-96">
                  <table className="w-full text-sm">
                    <thead className="text-gray-400 text-xs">
                      <tr>
                        <th className="text-left p-2">Pair</th>
                        <th className="text-left p-2">Side</th>
                        <th className="text-right p-2">Open Rate</th>
                        <th className="text-right p-2">Close Rate</th>
                        <th className="text-right p-2">Profit</th>
                        <th className="text-left p-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.map((trade) => (
                        <tr key={trade.id} className="border-t border-gray-800">
                          <td className="p-2 font-mono">{trade.pair}</td>
                          <td className="p-2">
                            <span className={trade.is_open ? "text-blue-400" : "text-green-400"}>
                              {trade.is_open ? "OPEN" : "CLOSED"}
                            </span>
                          </td>
                          <td className="p-2 text-right font-mono">{trade.open_rate?.toFixed(8)}</td>
                          <td className="p-2 text-right font-mono">{trade.close_rate?.toFixed(8) || "-"}</td>
                          <td className={`p-2 text-right font-mono ${(trade.close_profit || 0) >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {trade.close_profit ? `${(trade.close_profit * 100).toFixed(2)}%` : "-"}
                          </td>
                          <td className="p-2">
                            <span className={trade.is_open ? "text-yellow-400" : "text-green-400"}>
                              {trade.is_open ? "Active" : "Completed"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>

            <TabsContent value="freqai">
              {freqaiEnabled ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between p-3 bg-green-900/30 border border-green-500 rounded-lg">
                    <div className="flex items-center gap-2">
                      <Brain className="h-5 w-5 text-purple-400" />
                      <span className="font-semibold">FreqAI Enabled</span>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={handleDisableFreqAI}
                      disabled={loading.freqai}
                    >
                      {loading.freqai ? <Loader2 className="h-4 w-4 animate-spin" /> : "Disable FreqAI"}
                    </Button>
                  </div>
                  <FreqAIInsightsPanel strategyId={strategy.id} />
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="p-4 bg-gray-900 rounded-lg">
                    <div className="flex items-center gap-2 mb-3">
                      <Brain className="h-5 w-5 text-purple-400" />
                      <h3 className="font-semibold">Enable FreqAI</h3>
                    </div>
                    <p className="text-sm text-gray-300 mb-4">
                      FreqAI uses machine learning to improve trading predictions. When enabled:
                    </p>
                    <ul className="text-sm text-gray-400 list-disc list-inside space-y-1 mb-4">
                      <li>ML models analyze market patterns for entry/exit signals</li>
                      <li>Models train on historical data and improve over time</li>
                      <li>Feature importance shows which indicators matter most</li>
                      <li>Confidence scores help filter low-quality signals</li>
                    </ul>
                    <div className="space-y-3">
                      <div>
                        <label className="text-sm text-gray-500 mb-1 block">Select Model</label>
                        <Select value={freqaiModel} onValueChange={setFreqaiModel}>
                          <SelectTrigger className="w-48">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="lightgbm">LightGBM (Fast)</SelectItem>
                            <SelectItem value="xgboost">XGBoost (Accurate)</SelectItem>
                            <SelectItem value="pytorch">Pytorch Neural Net</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>
                      <Button onClick={handleEnableFreqAI} disabled={loading.freqai}>
                        {loading.freqai ? (
                          <>
                            <Loader2 className="h-4 w-4 animate-spin mr-2" />
                            Enabling...
                          </>
                        ) : (
                          <>
                            <Brain className="h-4 w-4 mr-2" />
                            Enable FreqAI
                          </>
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              )}
            </TabsContent>

            <TabsContent value="logs">
              <div className="h-96 overflow-auto">
                {loading.logs ? (
                  <div className="text-center py-8 text-gray-400">Loading logs...</div>
                ) : containerLogs.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">No logs available</div>
                ) : (
                  <pre className="text-xs font-mono bg-black p-3 rounded-lg overflow-auto">
                    {containerLogs.join("\n")}
                  </pre>
                )}
              </div>
            </TabsContent>

            <TabsContent value="backtest">
              <div className="space-y-4">
                <div className="p-4 bg-gray-900 rounded-lg">
                  <h3 className="font-semibold mb-3">Run Research</h3>
                  <p className="text-sm text-gray-400 mb-4">
                    Start automated research to find better parameters for this strategy.
                  </p>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={async () => {
                        if (!strategy) return
                        try {
                          const result = await api.startResearch({
                            strategy_id: strategy.id,
                            strategy_name: strategy.name,
                            research_type: "hyperopt",
                            epochs: 100,
                          })
                          alert(`Research started: ${result.research_id}`)
                        } catch (error) {
                          console.error(error)
                          alert("Failed to start research")
                        }
                      }}
                    >
                      Start Hyperopt
                    </Button>
                    <Button
                      variant="outline"
                      onClick={async () => {
                        if (!strategy) return
                        try {
                          const result = await api.startResearch({
                            strategy_id: strategy.id,
                            strategy_name: strategy.name,
                            research_type: "backtest_comparison",
                          })
                          alert(`Research started: ${result.research_id}`)
                        } catch (error) {
                          console.error(error)
                          alert("Failed to start research")
                        }
                      }}
                    >
                      Backtest Comparison
                    </Button>
                  </div>
                </div>
                <div className="text-center py-4 text-gray-400">
                  View research results in the Research Activity section below
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}