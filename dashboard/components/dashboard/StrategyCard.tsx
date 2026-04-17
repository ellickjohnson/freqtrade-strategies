'use client'

import { useState } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { formatCurrency, formatPercent, getStatusBgColor, getStatusColor } from '@/lib/utils'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Play, Square, Settings, Trash2, BarChart2, Brain, Loader2, Eye } from 'lucide-react'
import type { Strategy } from '@/lib/types'
import { StrategyDetailModal } from './StrategyDetailModal'

interface StrategyCardProps {
  strategy: Strategy
  onUpdate: () => void
}

export default function StrategyCard({ strategy, onUpdate }: StrategyCardProps) {
  const [actionLoading, setActionLoading] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [showDelete, setShowDelete] = useState(false)
  const [showBacktest, setShowBacktest] = useState(false)
  const [showDetails, setShowDetails] = useState(false)
  const [configUpdates, setConfigUpdates] = useState<Record<string, any>>({})
  const [backtestTimerange, setBacktestTimerange] = useState('20240101-20240131')
  
  async function handleStart() {
    try {
      setActionLoading(true)
      await api.startStrategy(strategy.id)
      await onUpdate()
    } catch (error) {
      console.error('Failed to start strategy:', error)
      alert('Failed to start strategy: ' + (error instanceof Error ? error.message : String(error)))
    } finally {
      setActionLoading(false)
    }
  }
  
  async function handleStop() {
    try {
      setActionLoading(true)
      await api.stopStrategy(strategy.id)
      await onUpdate()
    } catch (error) {
      console.error('Failed to stop strategy:', error)
      alert('Failed to stop strategy: ' + (error instanceof Error ? error.message : String(error)))
    } finally {
      setActionLoading(false)
    }
  }
  
  async function handleDelete() {
    try {
      setActionLoading(true)
      await api.deleteStrategy(strategy.id)
      setShowDelete(false)
      await onUpdate()
    } catch (error) {
      console.error('Failed to delete strategy:', error)
      alert('Failed to delete strategy: ' + (error instanceof Error ? error.message : String(error)))
    } finally {
      setActionLoading(false)
    }
  }
  
  async function handleUpdateConfig() {
    try {
      setActionLoading(true)
      await api.updateStrategy(strategy.id, configUpdates)
      setShowConfig(false)
      setConfigUpdates({})
      await onUpdate()
    } catch (error) {
      console.error('Failed to update strategy:', error)
      alert('Failed to update strategy: ' + (error instanceof Error ? error.message : String(error)))
    } finally {
      setActionLoading(false)
    }
  }
  
  async function handleRunBacktest() {
    try {
      setActionLoading(true)
      await api.runBacktest({
        strategy_id: strategy.id,
        timerange: backtestTimerange,
      })
      setShowBacktest(false)
      alert('Backtest started! Check results in a few moments.')
    } catch (error) {
      console.error('Failed to run backtest:', error)
      alert('Failed to run backtest: ' + (error instanceof Error ? error.message : String(error)))
    } finally {
      setActionLoading(false)
    }
  }
  
  const isRunning = strategy.status === 'running'
  const isStopped = strategy.status === 'stopped' || strategy.status === 'error'
  
  return (
    <>
      <Card className="glass hover:border-slate-700 transition-all">
        <CardContent className="pt-6">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h3 className="font-semibold text-slate-50">{strategy.name}</h3>
                {strategy.use_freqai && (
                  <Brain className="h-4 w-4 text-purple-400" />
                )}
              </div>
              <p className="text-xs text-slate-500">
                {strategy.strategy_file} &bull; {strategy.timeframe}
              </p>
            </div>
            
            <div className={`px-2 py-1 rounded text-xs font-medium ${getStatusBgColor(strategy.status)} ${getStatusColor(strategy.status)}`}>
              {strategy.status}
            </div>
          </div>
          
          <div className="grid grid-cols-3 gap-3 mb-4">
            <div>
              <p className="text-xs text-slate-400 mb-1">P&amp;L</p>
              <p className="text-lg font-bold text-slate-50">
                {formatCurrency(strategy.profit_pct ?? 0)}
              </p>
            </div>
            
            <div>
              <p className="text-xs text-slate-400 mb-1">Win Rate</p>
              <p className="text-lg font-bold text-slate-50">
                {formatPercent(strategy.win_rate ?? 0, 0)}
              </p>
            </div>
            
            <div>
              <p className="text-xs text-slate-400 mb-1">Trades</p>
              <p className="text-lg font-bold text-slate-50">
                {strategy.total_trades ?? 0}
              </p>
            </div>
          </div>
          
          <div className="mb-4">
            <div className="flex flex-wrap gap-1">
              {strategy.pairs.slice(0, 3).map((pair) => (
                <span
                  key={pair}
                  className="px-2 py-0.5 bg-slate-800 rounded text-xs text-slate-300"
                >
                  {pair}
                </span>
              ))}
              {strategy.pairs.length > 3 && (
                <span className="px-2 py-0.5 bg-slate-800 rounded text-xs text-slate-400">
                  +{strategy.pairs.length - 3} more
                </span>
              )}
            </div>
          </div>
          
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowDetails(true)}
              className="cursor-pointer"
            >
              <Eye className="h-4 w-4 mr-1" />
              Details
            </Button>
            
            {isStopped && (
              <Button
                size="sm"
                onClick={handleStart}
                disabled={actionLoading}
                className="flex-1 cursor-pointer"
              >
                {actionLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Play className="h-4 w-4 mr-1" />
                    Start
                  </>
                )}
              </Button>
            )}
            
            {isRunning && (
              <Button
                size="sm"
                variant="destructive"
                onClick={handleStop}
                disabled={actionLoading}
                className="flex-1 cursor-pointer"
              >
                {actionLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <>
                    <Square className="h-4 w-4 mr-1" />
                    Stop
                  </>
                )}
              </Button>
            )}
            
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowConfig(true)}
              className="cursor-pointer"
            >
              <Settings className="h-4 w-4" />
            </Button>
            
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowBacktest(true)}
              className="cursor-pointer"
            >
              <BarChart2 className="h-4 w-4" />
            </Button>
            
            <Button
              size="sm"
              variant="outline"
              onClick={() => setShowDelete(true)}
              className="cursor-pointer text-red-400 hover:text-red-300"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Config Dialog */}
      <Dialog open={showConfig} onOpenChange={setShowConfig}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Configure Strategy</DialogTitle>
            <DialogDescription>
              Update {strategy.name} configuration
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <Label>Max Open Trades</Label>
              <Input
                type="number"
                defaultValue={strategy.max_open_trades}
                onChange={(e) =>
                  setConfigUpdates({
                    ...configUpdates,
                    max_open_trades: parseInt(e.target.value),
                  })
                }
              />
            </div>
            <div>
              <Label>Stake Amount (USDT)</Label>
              <Input
                type="number"
                defaultValue={strategy.stake_amount}
                onChange={(e) =>
                  setConfigUpdates({
                    ...configUpdates,
                    stake_amount: parseFloat(e.target.value),
                  })
                }
              />
            </div>
            <div>
              <Label>Stop Loss (%)</Label>
              <Input
                type="number"
                step="0.01"
                defaultValue={strategy.stoploss * 100}
                onChange={(e) =>
                  setConfigUpdates({
                    ...configUpdates,
                    stoploss: parseFloat(e.target.value) / 100,
                  })
                }
              />
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setShowConfig(false)}>
              Cancel
            </Button>
            <Button onClick={handleUpdateConfig} disabled={actionLoading}>
              {actionLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Backtest Dialog */}
      <Dialog open={showBacktest} onOpenChange={setShowBacktest}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Run Backtest</DialogTitle>
            <DialogDescription>
              Backtest {strategy.name} with historical data
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 mt-4">
            <div>
              <Label>Time Range</Label>
              <Input
                value={backtestTimerange}
                onChange={(e) => setBacktestTimerange(e.target.value)}
                placeholder="20240101-20240131"
              />
              <p className="text-xs text-slate-400 mt-1">
                Format: YYYYMMDD-YYYYMMDD
              </p>
            </div>
          </div>
          <DialogFooter className="mt-4">
            <Button variant="outline" onClick={() => setShowBacktest(false)}>
              Cancel
            </Button>
            <Button onClick={handleRunBacktest} disabled={actionLoading}>
              {actionLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Run Backtest
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation */}
      <AlertDialog open={showDelete} onOpenChange={setShowDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Strategy</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete "{strategy.name}"? This action
              cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-red-600 hover:bg-red-700"
            >
              {actionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                'Delete'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Strategy Detail Modal */}
      <StrategyDetailModal
        strategy={strategy}
        open={showDetails}
        onOpenChange={setShowDetails}
        onUpdate={onUpdate}
      />
    </>
  )
}