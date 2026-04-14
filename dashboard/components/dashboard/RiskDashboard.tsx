'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import {
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Activity,
  Shield,
  AlertCircle,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Loader2
} from 'lucide-react'

interface RiskMetric {
  name: string
  value: number
  threshold: number
  status: 'ok' | 'warning' | 'critical'
  description: string
}

interface RiskReport {
  timestamp: string
  portfolio_drawdown: number
  daily_pnl: number
  total_exposure: number
  positions_at_risk: Array<{
    strategy_id: string
    pair: string
    profit_pct: number
    exposure_pct: number
    risk_factors: string[]
  }>
  var_estimate: number
  risk_score: number
  alerts: Array<{
    level: string
    type: string
    message: string
    recommendation: string
  }>
  recommendations: string[]
  circuit_breaker_triggered: boolean
  circuit_breaker_reason: string | null
}

export function RiskDashboard() {
  const [riskReport, setRiskReport] = useState<RiskReport | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchRiskReport()
    const interval = setInterval(fetchRiskReport, 60000) // Every minute
    return () => clearInterval(interval)
  }, [])

  const fetchRiskReport = async () => {
    try {
      setLoading(true)
      const data = await api.getRiskReport()
      setRiskReport(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch risk report')
    } finally {
      setLoading(false)
    }
  }

  const getRiskScoreColor = (score: number) => {
    if (score < 30) return 'text-green-500'
    if (score < 60) return 'text-yellow-500'
    return 'text-red-500'
  }

  const getRiskScoreBackground = (score: number) => {
    if (score < 30) return 'bg-green-500'
    if (score < 60) return 'bg-yellow-500'
    return 'bg-red-500'
  }

  const getAlertIcon = (level: string) => {
    switch (level) {
      case 'critical': return <XCircle className="h-4 w-4 text-red-500" />
      case 'warning': return <AlertTriangle className="h-4 w-4 text-yellow-500" />
      default: return <AlertCircle className="h-4 w-4 text-blue-500" />
    }
  }

  if (loading && !riskReport) {
    return (
      <Card>
        <CardContent className="py-8 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span className="ml-2">Loading risk metrics...</span>
        </CardContent>
      </Card>
    )
  }

  if (!riskReport) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No risk data available. Start some strategies to see risk metrics.
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Circuit Breaker Alert */}
      {riskReport.circuit_breaker_triggered && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-6 w-6 text-red-500" />
            <div>
              <p className="font-bold text-red-700 dark:text-red-300">Circuit Breaker Active</p>
              <p className="text-sm text-red-600 dark:text-red-400">{riskReport.circuit_breaker_reason}</p>
            </div>
          </div>
        </div>
      )}

      {/* Risk Score Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Risk Score</p>
                <p className={`text-3xl font-bold ${getRiskScoreColor(riskReport.risk_score)}`}>
                  {riskReport.risk_score.toFixed(0)}
                </p>
              </div>
              <Shield className={`h-8 w-8 ${getRiskScoreColor(riskReport.risk_score)}`} />
            </div>
            <div className="mt-2 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className={`h-full ${getRiskScoreBackground(riskReport.risk_score)}`}
                style={{ width: `${riskReport.risk_score}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Drawdown</p>
                <p className={`text-3xl font-bold ${riskReport.portfolio_drawdown > 10 ? 'text-red-500' : 'text-green-500'}`}>
                  {riskReport.portfolio_drawdown.toFixed(2)}%
                </p>
              </div>
              {riskReport.portfolio_drawdown > 0 ? (
                <TrendingDown className="h-8 w-8 text-red-500" />
              ) : (
                <TrendingUp className="h-8 w-8 text-green-500" />
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Daily P&L</p>
                <p className={`text-3xl font-bold ${riskReport.daily_pnl < 0 ? 'text-red-500' : 'text-green-500'}`}>
                  {riskReport.daily_pnl < 0 ? '' : '+'}{riskReport.daily_pnl.toFixed(2)}
                </p>
              </div>
              <Activity className="h-8 w-8 text-blue-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground">Exposure</p>
                <p className="text-3xl font-bold">{riskReport.total_exposure.toFixed(1)}%</p>
              </div>
              <Activity className="h-8 w-8 text-purple-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Positions at Risk */}
      {riskReport.positions_at_risk.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-yellow-500" />
              Positions at Risk
            </CardTitle>
            <CardDescription>
              Positions that exceed risk thresholds
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {riskReport.positions_at_risk.map((pos, i) => (
                <div key={i} className="border rounded-lg p-4">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{pos.strategy_id.slice(0, 8)}</Badge>
                      <span className="font-medium">{pos.pair}</span>
                    </div>
                    <span className={pos.profit_pct < 0 ? 'text-red-500' : 'text-green-500'}>
                      {pos.profit_pct.toFixed(2)}%
                    </span>
                  </div>
                  <div className="text-sm text-muted-foreground">
                    Exposure: {pos.exposure_pct.toFixed(1)}%
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {pos.risk_factors.map((factor, j) => (
                      <Badge key={j} variant="destructive" className="text-xs">
                        {factor}
                      </Badge>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Alerts */}
      {riskReport.alerts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Alerts</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {riskReport.alerts.map((alert, i) => (
                <div key={i} className="flex items-start gap-3 p-3 border rounded-lg">
                  {getAlertIcon(alert.level)}
                  <div className="flex-1">
                    <p className="font-medium">{alert.message}</p>
                    <p className="text-sm text-muted-foreground">{alert.recommendation}</p>
                  </div>
                  <Badge variant={alert.level === 'critical' ? 'destructive' : 'secondary'}>
                    {alert.type}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Recommendations */}
      {riskReport.recommendations.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Risk Recommendations</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {riskReport.recommendations.map((rec, i) => (
                <li key={i} className="flex items-start gap-2">
                  <CheckCircle2 className="h-4 w-4 text-green-500 mt-0.5" />
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* VaR Information */}
      <Card>
        <CardHeader>
          <CardTitle>Value at Risk (VaR)</CardTitle>
          <CardDescription>95% confidence daily risk estimate</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-3xl font-bold">{riskReport.var_estimate.toFixed(2)}%</p>
              <p className="text-sm text-muted-foreground">
                Expected maximum daily loss at 95% confidence
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm text-muted-foreground">Last updated</p>
              <p className="text-sm">{new Date(riskReport.timestamp).toLocaleString()}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Refresh Button */}
      <Button variant="outline" onClick={fetchRiskReport} disabled={loading}>
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin mr-2" />
        ) : (
          <RefreshCw className="h-4 w-4 mr-2" />
        )}
        Refresh Risk Metrics
      </Button>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-600 dark:text-red-300">
          {error}
        </div>
      )}
    </div>
  )
}