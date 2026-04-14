'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Settings,
  Brain,
  Shield,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Save
} from 'lucide-react'

interface AgentConfig {
  interval_minutes: number
  auto_apply_improvements: boolean
  paper_trading_only: boolean
  max_portfolio_drawdown: number
  max_position_size_pct: number
  min_sharpe_ratio: number
  min_improvement_threshold: number
  llm_model: string
}

interface LLMUsage {
  total_input_tokens: number
  total_output_tokens: number
  request_count: number
  daily_budget: number
  budget_remaining: number
}

export function AutonomousConfig() {
  const [config, setConfig] = useState<AgentConfig>({
    interval_minutes: 5,
    auto_apply_improvements: false,
    paper_trading_only: true,
    max_portfolio_drawdown: 15,
    max_position_size_pct: 10,
    min_sharpe_ratio: 0.5,
    min_improvement_threshold: 5,
    llm_model: 'claude-sonnet-4-6',
  })
  const [llmUsage, setLLMUsage] = useState<LLMUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => {
    fetchConfig()
    fetchLLMUsage()
  }, [])

  const fetchConfig = async () => {
    try {
      setLoading(true)
      const data = await api.getAutonomousConfig()
      setConfig(data)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch config')
    } finally {
      setLoading(false)
    }
  }

  const fetchLLMUsage = async () => {
    try {
      const data = await api.getLLMUsage()
      setLLMUsage(data)
    } catch (e) {
      console.error('Failed to fetch LLM usage:', e)
    }
  }

  const saveConfig = async () => {
    try {
      setSaving(true)
      setError(null)
      setSuccess(null)

      await api.updateAutonomousConfig(config)
      setSuccess('Configuration saved successfully!')
      setTimeout(() => setSuccess(null), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  const handleSliderChange = (key: keyof AgentConfig, value: number[]) => {
    setConfig(prev => ({ ...prev, [key]: value[0] }))
  }

  const handleSwitchChange = (key: keyof AgentConfig, value: boolean) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <Card>
        <CardContent className="py-8 flex items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin" />
          <span className="ml-2">Loading configuration...</span>
        </CardContent>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Autonomous Agent Configuration
          </CardTitle>
          <CardDescription>
            Configure the autonomous financial engineering agent settings
          </CardDescription>
        </CardHeader>
      </Card>

      {/* LLM Usage */}
      {llmUsage && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Brain className="h-5 w-5" />
              LLM Usage
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div>
                <p className="text-sm text-muted-foreground">Input Tokens</p>
                <p className="text-lg font-medium">{llmUsage.total_input_tokens.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Output Tokens</p>
                <p className="text-lg font-medium">{llmUsage.total_output_tokens.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Requests</p>
                <p className="text-lg font-medium">{llmUsage.request_count}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Daily Budget</p>
                <p className="text-lg font-medium">{llmUsage.daily_budget.toLocaleString()}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Remaining</p>
                <p className="text-lg font-medium text-green-500">{llmUsage.budget_remaining.toLocaleString()}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Agent Behavior */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Agent Behavior</CardTitle>
          <CardDescription>
            Control how the autonomous agent operates
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label>Run Interval (minutes)</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[config.interval_minutes]}
                onValueChange={(v) => handleSliderChange('interval_minutes', v)}
                min={1}
                max={60}
                step={1}
                className="flex-1"
              />
              <span className="w-12 text-center font-medium">{config.interval_minutes}</span>
            </div>
            <p className="text-sm text-muted-foreground">
              How often the agent checks for opportunities
            </p>
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Auto-Apply Improvements</Label>
              <p className="text-sm text-muted-foreground">
                Automatically apply improvements above threshold
              </p>
            </div>
            <Switch
              checked={config.auto_apply_improvements}
              onCheckedChange={(v) => handleSwitchChange('auto_apply_improvements', v)}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label>Paper Trading Only</Label>
              <p className="text-sm text-muted-foreground">
                Only run strategies in paper trading mode
              </p>
            </div>
            <Switch
              checked={config.paper_trading_only}
              onCheckedChange={(v) => handleSwitchChange('paper_trading_only', v)}
            />
          </div>

          <div className="space-y-2">
            <Label>Min Improvement Threshold (%)</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[config.min_improvement_threshold]}
                onValueChange={(v) => handleSliderChange('min_improvement_threshold', v)}
                min={1}
                max={20}
                step={0.5}
                className="flex-1"
              />
              <span className="w-12 text-center font-medium">{config.min_improvement_threshold}%</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Minimum improvement to apply changes
            </p>
          </div>

          <div className="space-y-2">
            <Label>LLM Model</Label>
            <Select
              value={config.llm_model}
              onValueChange={(v) => setConfig(prev => ({ ...prev, llm_model: v }))}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="claude-sonnet-4-6">Claude Sonnet 4.6 (Recommended)</SelectItem>
                <SelectItem value="claude-sonnet-4-5">Claude Sonnet 4.5</SelectItem>
                <SelectItem value="claude-opus-4-6">Claude Opus 4.6 (Most Capable)</SelectItem>
                <SelectItem value="gpt-4o">GPT-4o</SelectItem>
                <SelectItem value="gpt-4-turbo">GPT-4 Turbo</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Risk Limits */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Risk Limits
          </CardTitle>
          <CardDescription>
            Safety limits that the agent must respect
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label>Max Portfolio Drawdown (%)</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[config.max_portfolio_drawdown]}
                onValueChange={(v) => handleSliderChange('max_portfolio_drawdown', v)}
                min={5}
                max={30}
                step={1}
                className="flex-1"
              />
              <span className="w-12 text-center font-medium">{config.max_portfolio_drawdown}%</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Stop all trading if drawdown exceeds this limit
            </p>
          </div>

          <div className="space-y-2">
            <Label>Max Position Size (%)</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[config.max_position_size_pct]}
                onValueChange={(v) => handleSliderChange('max_position_size_pct', v)}
                min={1}
                max={25}
                step={1}
                className="flex-1"
              />
              <span className="w-12 text-center font-medium">{config.max_position_size_pct}%</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Maximum size of any single position
            </p>
          </div>

          <div className="space-y-2">
            <Label>Min Sharpe Ratio</Label>
            <div className="flex items-center gap-4">
              <Slider
                value={[config.min_sharpe_ratio * 10]}
                onValueChange={(v) => setConfig(prev => ({ ...prev, min_sharpe_ratio: v[0] / 10 }))}
                min={0}
                max={30}
                step={1}
                className="flex-1"
              />
              <span className="w-12 text-center font-medium">{config.min_sharpe_ratio.toFixed(1)}</span>
            </div>
            <p className="text-sm text-muted-foreground">
              Minimum Sharpe ratio to keep a strategy running
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Safety Warning */}
      {!config.paper_trading_only && (
        <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-6 w-6 text-yellow-500" />
            <div>
              <p className="font-bold text-yellow-700 dark:text-yellow-300">Live Trading Enabled</p>
              <p className="text-sm text-yellow-600 dark:text-yellow-400">
                The agent will make real trades with real money. Ensure you understand the risks.
              </p>
            </div>
          </div>
        </div>
      )}

      {config.auto_apply_improvements && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-center gap-3">
            <Brain className="h-6 w-6 text-blue-500" />
            <div>
              <p className="font-bold text-blue-700 dark:text-blue-300">Auto-Apply Enabled</p>
              <p className="text-sm text-blue-600 dark:text-blue-400">
                Improvements above {config.min_improvement_threshold}% will be applied automatically.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error/Success Messages */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4 text-red-600 dark:text-red-300">
          {error}
        </div>
      )}

      {success && (
        <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4 text-green-600 dark:text-green-300 flex items-center gap-2">
          <CheckCircle2 className="h-5 w-5" />
          {success}
        </div>
      )}

      {/* Save Button */}
      <Button onClick={saveConfig} disabled={saving} className="w-full">
        {saving ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin mr-2" />
            Saving...
          </>
        ) : (
          <>
            <Save className="h-4 w-4 mr-2" />
            Save Configuration
          </>
        )}
      </Button>
    </div>
  )
}