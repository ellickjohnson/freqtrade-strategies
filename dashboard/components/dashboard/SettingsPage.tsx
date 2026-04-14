"use client"

import { useState, useEffect } from "react"
import { api } from "@/lib/api"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Settings, Brain, FlaskConical, Bell, Server, RefreshCw, Loader2, Check, Play, Clock, Zap } from "lucide-react"
import { AutonomousConfig } from "./AutonomousConfig"

export function SettingsPage() {
  const [settings, setSettings] = useState({
    auto_research: true,
    auto_apply_improvements: false,
    research_frequency: "weekly",
    min_improvement_threshold: 5.0,
    max_concurrent_research: 3,
    freqai_enabled_globally: false,
    default_freqai_model: "lightgbm",
    slack_enabled: false,
    container_manager_available: false,
    base_port: 7070,
    // Research config
    research_epochs: 100,
    research_timerange: "20240101-",
    research_spaces: "buy,sell,roi,stoploss",
    research_min_trades: 100,
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    loadSettings()
  }, [])

  const loadSettings = async () => {
    try {
      const data = await api.getSettings()
      setSettings(prev => ({ ...prev, ...data }))
    } catch (error) {
      console.error("Failed to load settings:", error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    setSaved(false)
    try {
      await api.updateSettings(settings)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (error) {
      console.error("Failed to save settings:", error)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-green-500" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-slate-50">Settings</h2>
          <p className="text-slate-400">Configure research, FreqAI, and system settings</p>
        </div>
        <Button onClick={handleSave} disabled={saving} className="gap-2">
          {saving ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Saving...
            </>
          ) : saved ? (
            <>
              <Check className="h-4 w-4" />
              Saved
            </>
          ) : (
            <>
              <RefreshCw className="h-4 w-4" />
              Save Changes
            </>
          )}
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Research & Learning */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <FlaskConical className="h-5 w-5 text-purple-400" />
              </div>
              <div>
                <CardTitle>Research & Learning</CardTitle>
                <CardDescription>Configure autonomous research behavior</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Enable Auto Research</Label>
                <p className="text-xs text-slate-500">Run research experiments automatically</p>
              </div>
              <Switch
                checked={settings.auto_research}
                onCheckedChange={(checked) => setSettings(s => ({ ...s, auto_research: checked }))}
              />
            </div>

            <div className="space-y-2">
              <Label>Research Frequency</Label>
              <Select
                value={settings.research_frequency}
                onValueChange={(value) => setSettings(s => ({ ...s, research_frequency: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hourly">Every Hour</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                  <SelectItem value="monthly">Monthly</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Auto-Apply Improvements</Label>
                <p className="text-xs text-slate-500">Automatically apply findings above threshold</p>
              </div>
              <Switch
                checked={settings.auto_apply_improvements}
                onCheckedChange={(checked) => setSettings(s => ({ ...s, auto_apply_improvements: checked }))}
              />
            </div>

            <div className="space-y-2">
              <Label>Min Improvement Threshold (%)</Label>
              <Input
                type="number"
                step="0.5"
                value={settings.min_improvement_threshold}
                onChange={(e) => setSettings(s => ({ ...s, min_improvement_threshold: parseFloat(e.target.value) }))}
              />
              <p className="text-xs text-slate-500">Auto-apply only if improvement is above this value</p>
            </div>

            <div className="space-y-2">
              <Label>Max Concurrent Research</Label>
              <Input
                type="number"
                value={settings.max_concurrent_research}
                onChange={(e) => setSettings(s => ({ ...s, max_concurrent_research: parseInt(e.target.value) }))}
              />
              <p className="text-xs text-slate-500">Maximum simultaneous research tasks</p>
            </div>

            <div className="mt-4 pt-4 border-t border-slate-700">
              <h4 className="text-sm font-semibold text-slate-200 mb-3 flex items-center gap-2">
                <Zap className="h-4 w-4 text-yellow-400" />
                Research Configuration
              </h4>
              <div className="space-y-3">
                <div className="space-y-2">
                  <Label>Hyperopt Epochs</Label>
                  <Input
                    type="number"
                    value={settings.research_epochs}
                    onChange={(e) => setSettings(s => ({ ...s, research_epochs: parseInt(e.target.value) }))}
                  />
                  <p className="text-xs text-slate-500">Number of optimization iterations</p>
                </div>

                <div className="space-y-2">
                  <Label>Time Range</Label>
                  <Input
                    type="text"
                    value={settings.research_timerange}
                    onChange={(e) => setSettings(s => ({ ...s, research_timerange: e.target.value }))}
                    placeholder="20240101-"
                  />
                  <p className="text-xs text-slate-500">Format: YYYYMMDD-YYYYMMDD or YYYYMMDD- for to present</p>
                </div>

                <div className="space-y-2">
                  <Label>Parameter Spaces</Label>
                  <Select
                    value={settings.research_spaces}
                    onValueChange={(value) => setSettings(s => ({ ...s, research_spaces: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="buy,sell">Buy & Sell Only</SelectItem>
                      <SelectItem value="buy,sell,roi">Buy, Sell & ROI</SelectItem>
                      <SelectItem value="buy,sell,roi,stoploss">All Parameters</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-slate-500">Which parameters to optimize</p>
                </div>

                <div className="space-y-2">
                  <Label>Minimum Trades</Label>
                  <Input
                    type="number"
                    value={settings.research_min_trades}
                    onChange={(e) => setSettings(s => ({ ...s, research_min_trades: parseInt(e.target.value) }))}
                  />
                  <p className="text-xs text-slate-500">Require this many trades for valid results</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* FreqAI Settings */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-blue-500/20 rounded-lg">
                <Brain className="h-5 w-5 text-blue-400" />
              </div>
              <div>
                <CardTitle>FreqAI Settings</CardTitle>
                <CardDescription>Machine learning configuration</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Enable FreqAI Globally</Label>
                <p className="text-xs text-slate-500">Enable ML for all strategies by default</p>
              </div>
              <Switch
                checked={settings.freqai_enabled_globally}
                onCheckedChange={(checked) => setSettings(s => ({ ...s, freqai_enabled_globally: checked }))}
              />
            </div>

            <div className="space-y-2">
              <Label>Default FreqAI Model</Label>
              <Select
                value={settings.default_freqai_model}
                onValueChange={(value) => setSettings(s => ({ ...s, default_freqai_model: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="lightgbm">LightGBM (Fast)</SelectItem>
                  <SelectItem value="xgboost">XGBoost (Accurate)</SelectItem>
                  <SelectItem value="pytorch">PyTorch Neural Net</SelectItem>
                  <SelectItem value="catboost">CatBoost</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-slate-500">Default ML model for predictions</p>
            </div>

            <div className="mt-4 p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <h4 className="text-sm font-semibold text-slate-200 mb-2">What FreqAI Does</h4>
              <ul className="text-xs text-slate-400 space-y-1">
                <li>• Uses ML models for entry/exit predictions</li>
                <li>• Trains on historical data continuously</li>
                <li>• Shows feature importance and confidence</li>
                <li>• Adapts to changing market conditions</li>
                <li>• Logs all predictions for analysis</li>
              </ul>
            </div>
          </CardContent>
        </Card>

        {/* System Status */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-green-500/20 rounded-lg">
                <Server className="h-5 w-5 text-green-400" />
              </div>
              <div>
                <CardTitle>System Status</CardTitle>
                <CardDescription>Current system configuration</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg">
              <div>
                <Label className="text-slate-200">Docker Manager</Label>
                <p className="text-xs text-slate-500">Container orchestration</p>
              </div>
              <span className={`text-sm font-medium ${settings.container_manager_available ? "text-green-400" : "text-red-400"}`}>
                {settings.container_manager_available ? "Connected" : "Disconnected"}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg">
              <div>
                <Label className="text-slate-200">Slack Notifications</Label>
                <p className="text-xs text-slate-500">Alert notifications</p>
              </div>
              <span className={`text-sm font-medium ${settings.slack_enabled ? "text-green-400" : "text-slate-400"}`}>
                {settings.slack_enabled ? "Configured" : "Not Configured"}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-800/50 rounded-lg">
              <div>
                <Label className="text-slate-200">Base Port</Label>
                <p className="text-xs text-slate-500">Starting port for strategies</p>
              </div>
              <span className="text-sm font-mono text-slate-200">{settings.base_port}</span>
            </div>
          </CardContent>
        </Card>

        {/* Notifications */}
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="p-2 bg-yellow-500/20 rounded-lg">
                <Bell className="h-5 w-5 text-yellow-400" />
              </div>
              <div>
                <CardTitle>Notifications</CardTitle>
                <CardDescription>Configure alerts and notifications</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Trade Alerts</Label>
                <p className="text-xs text-slate-500">Notify on every trade</p>
              </div>
              <Switch defaultChecked />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Research Complete</Label>
                <p className="text-xs text-slate-500">Notify when research finishes</p>
              </div>
              <Switch defaultChecked />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Performance Warnings</Label>
                <p className="text-xs text-slate-500">Notify if performance drops</p>
              </div>
              <Switch defaultChecked />
            </div>

            <div className="flex items-center justify-between">
              <div>
                <Label className="text-slate-200">Model Training Updates</Label>
                <p className="text-xs text-slate-500">Notify on FreqAI training progress</p>
              </div>
              <Switch />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Research Types Reference */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle>Research Types</CardTitle>
          <CardDescription>Types of research the system can perform</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="font-semibold text-purple-400 mb-1">Hyperopt</div>
              <p className="text-xs text-slate-400">Optimizes strategy parameters using historical data to find the best configuration.</p>
            </div>
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="font-semibold text-blue-400 mb-1">Backtest Comparison</div>
              <p className="text-xs text-slate-400">Compares performance across different time periods or configurations.</p>
            </div>
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="font-semibold text-green-400 mb-1">Parameter Sensitivity</div>
              <p className="text-xs text-slate-400">Tests how parameter changes affect strategy performance and robustness.</p>
            </div>
            <div className="p-4 bg-slate-800/50 rounded-lg border border-slate-700">
              <div className="font-semibold text-yellow-400 mb-1">Strategy Discovery</div>
              <p className="text-xs text-slate-400">Automatically explores new strategy configurations and variations.</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Autonomous Agent Configuration */}
      <AutonomousConfig />
    </div>
  )
}