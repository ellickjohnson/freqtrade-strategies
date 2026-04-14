"use client"

import { useState, useEffect } from "react"
import { api } from "@/lib/api"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Button } from "@/components/ui/button"

interface LogViewerProps {
  strategyId: string
  category?: "reasoning" | "all"
}

export function LogViewer({ strategyId, category = "all" }: LogViewerProps) {
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState({
    category: "all",
    level: "all",
  })
  const [autoRefresh, setAutoRefresh] = useState(false)

  useEffect(() => {
    loadLogs()
  }, [strategyId, filter])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(loadLogs, 5000)
    return () => clearInterval(interval)
  }, [autoRefresh, strategyId, filter])

  const loadLogs = async () => {
    setLoading(true)
    try {
      const result = category === "reasoning"
        ? await api.getStrategyReasoning(strategyId, 24, 100)
        : await api.getAgentLogs(
            strategyId,
            filter.category !== "all" ? filter.category : undefined,
            filter.level !== "all" ? filter.level : undefined,
            100
          )
      setLogs(result.logs || [])
    } catch (error) {
      console.error("Failed to load logs:", error)
    } finally {
      setLoading(false)
    }
  }

  const formatTimestamp = (ts: string) => {
    return new Date(ts).toLocaleTimeString()
  }

  const getLevelColor = (level: string) => {
    switch (level) {
      case "info": return "text-blue-400"
      case "warning": return "text-yellow-400"
      case "error": return "text-red-400"
      case "critical": return "text-red-500 font-bold"
      default: return "text-gray-400"
    }
  }

  const getCategoryColor = (cat: string) => {
    switch (cat) {
      case "trade_signal": return "bg-green-900 text-green-300"
      case "strategy_analysis": return "bg-blue-900 text-blue-300"
      case "freqai_prediction": return "bg-purple-900 text-purple-300"
      case "risk_management": return "bg-orange-900 text-orange-300"
      case "market_analysis": return "bg-cyan-900 text-cyan-300"
      case "research": return "bg-indigo-900 text-indigo-300"
      default: return "bg-gray-800 text-gray-300"
    }
  }

  const getImpactColor = (impact: string) => {
    switch (impact) {
      case "high": return "border-l-4 border-red-500"
      case "medium": return "border-l-4 border-yellow-500"
      case "low": return "border-l-4 border-blue-500"
      default: return "border-l-4 border-gray-600"
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          {category === "all" && (
            <>
              <Select value={filter.category} onValueChange={v => setFilter(f => ({ ...f, category: v }))}>
                <SelectTrigger className="w-40">
                  <SelectValue placeholder="Category" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Categories</SelectItem>
                  <SelectItem value="trade_signal">Trade Signals</SelectItem>
                  <SelectItem value="strategy_analysis">Analysis</SelectItem>
                  <SelectItem value="freqai_prediction">FreqAI</SelectItem>
                  <SelectItem value="risk_management">Risk</SelectItem>
                  <SelectItem value="market_analysis">Market</SelectItem>
                  <SelectItem value="research">Research</SelectItem>
                </SelectContent>
              </Select>

              <Select value={filter.level} onValueChange={v => setFilter(f => ({ ...f, level: v }))}>
                <SelectTrigger className="w-32">
                  <SelectValue placeholder="Level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Levels</SelectItem>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                  <SelectItem value="critical">Critical</SelectItem>
                </SelectContent>
              </Select>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={autoRefresh ? "default" : "outline"}
            onClick={() => setAutoRefresh(!autoRefresh)}
          >
            {autoRefresh ? "Auto-refresh ON" : "Auto-refresh OFF"}
          </Button>
          <Button size="sm" variant="outline" onClick={loadLogs}>
            Refresh
          </Button>
        </div>
      </div>

      {loading && logs.length === 0 ? (
        <div className="text-center py-8 text-gray-400">Loading reasoning logs...</div>
      ) : logs.length === 0 ? (
        <div className="text-center py-8 text-gray-400">
          No reasoning logs yet. Agent decisions will appear here as the strategy runs.
        </div>
      ) : (
        <div className="space-y-2 max-h-96 overflow-auto">
          {logs.map((log, idx) => (
            <div
              key={log.id || idx}
              className={`p-3 bg-gray-900 rounded-lg ${getImpactColor(log.impact)}`}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 font-mono">
                    {formatTimestamp(log.timestamp)}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded ${getCategoryColor(log.category)}`}>
                    {log.category?.replace("_", " ").toUpperCase()}
                  </span>
                  <span className={`text-xs font-semibold ${getLevelColor(log.level)}`}>
                    {log.level?.toUpperCase()}
                  </span>
                </div>
                {log.confidence && (
                  <span className="text-xs text-gray-400">
                    Confidence: {(log.confidence * 100).toFixed(0)}%
                  </span>
                )}
              </div>

              <div className="font-semibold text-sm mb-1">{log.title}</div>
              <div className="text-sm text-gray-300 mb-2">{log.message}</div>

              {log.reasoning && (
                <div className="text-xs text-gray-400 bg-black/30 p-2 rounded mb-2">
                  <div className="font-semibold mb-1">Reasoning:</div>
                  <div className="whitespace-pre-wrap">{log.reasoning}</div>
                </div>
              )}

              {log.data && Object.keys(log.data).length > 0 && (
                <details className="text-xs">
                  <summary className="cursor-pointer text-gray-400 hover:text-gray-200">
                    View Details
                  </summary>
                  <pre className="mt-2 p-2 bg-black/50 rounded overflow-auto max-h-32">
                    {JSON.stringify(log.data, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}