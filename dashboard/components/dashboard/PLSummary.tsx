'use client'

import { useStrategyStore } from '@/lib/store'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { TrendingUp, TrendingDown, Activity, DollarSign, BarChart2 } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'

export default function PLSummary() {
  const { portfolio } = useStrategyStore()
  
  if (!portfolio) {
    return (
      <div className="glass rounded-lg p-6">
        <p className="text-slate-400">Loading portfolio summary...</p>
      </div>
    )
  }
  
  const isPositive = (portfolio.total_pnl ?? 0) >= 0
  const dailyIsPositive = (portfolio.daily_pnl ?? 0) >= 0
  
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
      <Card className="glass">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400 mb-1">Total P&L</p>
              <p className="text-2xl font-bold text-slate-50">
                {formatCurrency(portfolio.total_pnl)}
              </p>
              <p className={`text-sm ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
                {formatPercent(portfolio.total_pnl_percent)}
              </p>
            </div>
            <div className={`p-3 rounded-lg ${isPositive ? 'bg-green-400/10' : 'bg-red-400/10'}`}>
              {isPositive ? (
                <TrendingUp className="h-6 w-6 text-green-400" />
              ) : (
                <TrendingDown className="h-6 w-6 text-red-400" />
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      
      <Card className="glass">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400 mb-1">Daily P&L</p>
              <p className={`text-2xl font-bold ${dailyIsPositive ? 'text-green-400' : 'text-red-400'}`}>
                {formatCurrency(portfolio.daily_pnl)}
              </p>
            </div>
            <div className={`p-3 rounded-lg ${dailyIsPositive ? 'bg-green-400/10' : 'bg-red-400/10'}`}>
              {dailyIsPositive ? (
                <Activity className="h-6 w-6 text-green-400" />
              ) : (
                <Activity className="h-6 w-6 text-red-400" />
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      
      <Card className="glass">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400 mb-1">Win Rate</p>
              <p className="text-2xl font-bold text-slate-50">
                {formatPercent(portfolio.win_rate, 1)}
              </p>
              <p className="text-xs text-slate-500">
                {portfolio.winning_trades} / {portfolio.total_trades} trades
              </p>
            </div>
            <div className="p-3 rounded-lg bg-blue-400/10">
              <BarChart2 className="h-6 w-6 text-blue-400" />
            </div>
          </div>
        </CardContent>
      </Card>
      
      <Card className="glass">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400 mb-1">Open Trades</p>
              <p className="text-2xl font-bold text-slate-50">
                {portfolio.open_trades}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-purple-400/10">
              <DollarSign className="h-6 w-6 text-purple-400" />
            </div>
          </div>
        </CardContent>
      </Card>
      
      <Card className="glass">
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-slate-400 mb-1">Active Strategies</p>
              <p className="text-2xl font-bold text-slate-50">
                {portfolio.strategies_active} / {portfolio.strategies_active + portfolio.strategies_stopped}
              </p>
            </div>
            <div className="p-3 rounded-lg bg-cyan-400/10">
              <Activity className="h-6 w-6 text-cyan-400" />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}