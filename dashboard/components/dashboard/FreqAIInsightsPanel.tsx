"use client"

import { useState, useEffect } from "react"
import { api } from "@/lib/api"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

interface FreqAIInsightsPanelProps {
  strategyId: string
}

export function FreqAIInsightsPanel({ strategyId }: FreqAIInsightsPanelProps) {
  const [model, setModel] = useState<any>(null)
  const [training, setTraining] = useState<any>(null)
  const [predictions, setPredictions] = useState<any[]>([])
  const [performance, setPerformance] = useState<any>(null)
  const [features, setFeatures] = useState<any[]>([])
  const [loading, setLoading] = useState({
    model: false,
    predictions: false,
    performance: false,
    features: false,
  })

  useEffect(() => {
    loadModel()
    loadPredictions()
    loadPerformance()
    loadFeatures()
  }, [strategyId])

  const loadModel = async () => {
    setLoading(l => ({ ...l, model: true }))
    try {
      const data = await api.getFreqAIModel(strategyId)
      setModel(data)
      const trainingData = await api.getFreqAITraining(strategyId)
      setTraining(trainingData)
    } catch (error) {
      console.error("Failed to load FreqAI model:", error)
    } finally {
      setLoading(l => ({ ...l, model: false }))
    }
  }

  const loadPredictions = async () => {
    setLoading(l => ({ ...l, predictions: true }))
    try {
      const data = await api.getFreqAIPredictions(strategyId, 20, true)
      setPredictions(data.predictions || [])
    } catch (error) {
      console.error("Failed to load predictions:", error)
    } finally {
      setLoading(l => ({ ...l, predictions: false }))
    }
  }

  const loadPerformance = async () => {
    setLoading(l => ({ ...l, performance: true }))
    try {
      const data = await api.getFreqAIPerformance(strategyId)
      setPerformance(data)
    } catch (error) {
      console.error("Failed to load performance:", error)
    } finally {
      setLoading(l => ({ ...l, performance: false }))
    }
  }

  const loadFeatures = async () => {
    setLoading(l => ({ ...l, features: true }))
    try {
      const data = await api.getFreqAIFeatures(strategyId)
      setFeatures(data.evolution || [])
    } catch (error) {
      console.error("Failed to load features:", error)
    } finally {
      setLoading(l => ({ ...l, features: false }))
    }
  }

  const formatTimestamp = (ts: string) => new Date(ts).toLocaleString()

  const getDirectionColor = (dir: string) => {
    if (dir === "BUY" || dir === "long") return "text-green-400"
    if (dir === "SELL" || dir === "short") return "text-red-400"
    return "text-gray-400"
  }

  if (loading.model && !model) {
    return <div className="text-center py-8 text-gray-400">Loading FreqAI data...</div>
  }

  return (
    <div className="space-y-4">
      <Tabs defaultValue="model" className="w-full">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="model">Model Status</TabsTrigger>
          <TabsTrigger value="predictions">Predictions</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="features">Features</TabsTrigger>
        </TabsList>

        <TabsContent value="model" className="space-y-4">
          {model && Object.keys(model).length > 0 ? (
            <>
              {training && training.status === "running" && (
                <div className="bg-blue-900/30 border border-blue-500 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold">Training in Progress</span>
                    <span className="text-xs text-gray-400">
                      Epoch {training.current_epoch} / {training.total_epochs}
                    </span>
                  </div>
                  <div className="w-full bg-gray-800 rounded-full h-2 mb-2">
                    <div
                      className="bg-blue-500 h-2 rounded-full"
                      style={{ width: `${(training.current_epoch / training.total_epochs) * 100}%` }}
                    />
                  </div>
                  <div className="text-xs text-gray-400 grid grid-cols-3 gap-4">
                    <div>Current Loss: {training.current_loss?.toFixed(6)}</div>
                    <div>Best Loss: {training.best_loss?.toFixed(6)}</div>
                    <div>Accuracy: {(training.validation_accuracy * 100).toFixed(1)}%</div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-gray-900 rounded-lg p-3">
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Model Info</h4>
                  <div className="space-y-1 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-500">Type:</span>
                      <span className="font-mono">{model.model_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Version:</span>
                      <span className="font-mono">{model.version}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Status:</span>
                      <span className="font-mono">{model.status}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Train Period:</span>
                      <span className="font-mono">{model.train_period_days} days</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Data Points:</span>
                      <span className="font-mono">{model.data_points_used?.toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                <div className="bg-gray-900 rounded-lg p-3">
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Latest Prediction</h4>
                  {model.last_prediction ? (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-gray-500">Signal:</span>
                        <span className={`font-mono text-lg ${getDirectionColor(model.prediction_direction || "HOLD")}`}>
                          {(model.last_prediction * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Confidence:</span>
                        <span className="font-mono">
                          {model.prediction_confidence ? (model.prediction_confidence * 100).toFixed(0) : 0}%
                        </span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-gray-500">Time:</span>
                        <span className="font-mono text-xs">{formatTimestamp(model.prediction_time)}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="text-center text-gray-500 text-sm">No predictions yet</div>
                  )}
                </div>
              </div>

              {model.features_importance && Object.keys(model.features_importance).length > 0 && (
                <div className="bg-gray-900 rounded-lg p-3">
                  <h4 className="text-sm font-semibold text-gray-400 mb-2">Top Features</h4>
                  <div className="space-y-1">
                    {Object.entries(model.features_importance)
                      .sort((a, b) => Math.abs(b[1] as number) - Math.abs(a[1] as number))
                      .slice(0, 5)
                      .map(([feature, importance]) => (
                        <div key={feature} className="flex items-center gap-2">
                          <div className="flex-1">
                            <div className="text-sm font-mono">{feature}</div>
                            <div className="w-full bg-gray-800 rounded-full h-1.5">
                              <div
                                className="bg-purple-500 h-1.5 rounded-full"
                                style={{ width: `${Math.abs(importance as number) * 100}%` }}
                              />
                            </div>
                          </div>
                          <div className="text-xs text-gray-400">{(importance as number).toFixed(3)}</div>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-8 text-gray-400">
              No FreqAI model data available yet. The model will appear after training begins.
            </div>
          )}
        </TabsContent>

        <TabsContent value="predictions">
          {loading.predictions ? (
            <div className="text-center py-8 text-gray-400">Loading predictions...</div>
          ) : predictions.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              No predictions yet. FreqAI predictions will appear here as the model runs.
            </div>
          ) : (
            <div className="overflow-auto max-h-96">
              <table className="w-full text-sm">
                <thead className="text-gray-400 text-xs sticky top-0 bg-gray-900">
                  <tr>
                    <th className="text-left p-2">Time</th>
                    <th className="text-left p-2">Pair</th>
                    <th className="text-left p-2">Direction</th>
                    <th className="text-right p-2">Confidence</th>
                    <th className="text-right p-2">Actual</th>
                    <th className="text-right p-2">P/L</th>
                  </tr>
                </thead>
                <tbody>
                  {predictions.map((pred, idx) => (
                    <tr key={pred.prediction_id || idx} className="border-t border-gray-800 hover:bg-gray-800/50">
                      <td className="p-2 font-mono text-xs">{formatTimestamp(pred.timestamp)}</td>
                      <td className="p-2 font-mono">{pred.pair}</td>
                        <td className={`p-2 font-semibold ${getDirectionColor(pred.direction)}`}>
                          {pred.direction}
                        </td>
                        <td className="p-2 text-right font-mono">
                          {(pred.confidence * 100).toFixed(0)}%
                        </td>
                        <td className="p-2 text-right">
                          {pred.actual_direction ? (
                            <span className={getDirectionColor(pred.actual_direction)}>
                              {pred.actual_direction}
                            </span>
                          ) : (
                            <span className="text-gray-500">-</span>
                          )}
                        </td>
                        <td className={`p-2 text-right font-mono ${pred.profit_loss >= 0 ? "text-green-400" : "text-red-400"}`}>
                          {pred.profit_loss != null ? `${(pred.profit_loss * 100).toFixed(2)}%` : "-"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          <TabsContent value="performance">
            {loading.performance ? (
              <div className="text-center py-8 text-gray-400">Loading performance...</div>
            ) : !performance ? (
              <div className="text-center py-8 text-gray-400">
                No performance data yet. Metrics will appear after the model makes predictions.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-4 gap-4">
                  <div className="bg-gray-900 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold">
                      {performance.accuracy?.accuracy ? (performance.accuracy.accuracy * 100).toFixed(1) : 0}%
                    </div>
                    <div className="text-xs text-gray-400">Prediction Accuracy</div>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold text-green-400">
                      {performance.accuracy?.avg_profit ? (performance.accuracy.avg_profit * 100).toFixed(2) : 0}%
                    </div>
                    <div className="text-xs text-gray-400">Avg Profit</div>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold">
                      {performance.accuracy?.total_predictions || 0}
                    </div>
                    <div className="text-xs text-gray-400">Total Predictions</div>
                  </div>
                  <div className="bg-gray-900 rounded-lg p-3 text-center">
                    <div className="text-2xl font-bold">
                      {performance.accuracy?.correct_predictions || 0}
                    </div>
                    <div className="text-xs text-gray-400">Correct</div>
                  </div>
                </div>

                {performance.history && performance.history.length > 0 && (
                  <div className="bg-gray-900 rounded-lg p-3">
                    <h4 className="text-sm font-semibold text-gray-400 mb-2">Model Evolution</h4>
                    <div className="overflow-auto max-h-48">
                      <table className="w-full text-xs">
                        <thead className="text-gray-500 sticky top-0 bg-gray-900">
                          <tr>
                            <th className="text-left p-1">Version</th>
                            <th className="text-right p-1">Accuracy</th>
                            <th className="text-right p-1">Sharpe</th>
                            <th className="text-right p-1">Win Rate</th>
                            <th className="text-right p-1">Trades</th>
                            <th className="text-left p-1">Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {performance.history.slice(0, 10).map((h: any) => (
                            <tr key={h.model_id} className="border-t border-gray-800">
                              <td className="p-1 font-mono">{h.version}</td>
                              <td className="p-1 text-right">{h.accuracy?.toFixed(2)}</td>
                              <td className="p-1 text-right">{h.sharpe_ratio?.toFixed(2)}</td>
                              <td className="p-1 text-right">{(h.win_rate * 100).toFixed(1)}%</td>
                              <td className="p-1 text-right">{h.total_trades}</td>
                              <td className="p-1 text-xs">{formatTimestamp(h.training_end)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="features">
            {loading.features ? (
              <div className="text-center py-8 text-gray-400">Loading features...</div>
            ) : features.length === 0 ? (
              <div className="text-center py-8 text-gray-400">
                No feature importance data yet. Will appear after model training.
              </div>
            ) : (
              <div className="space-y-3">
                <div className="text-xs text-gray-400">
                  Feature importance evolution over last {features.length} model versions
                </div>
                {features.slice(0, 5).map((f: any) => (
                  <div key={f.model_id} className="bg-gray-900 rounded-lg p-3">
                    <div className="flex justify-between items-center mb-2">
                      <span className="font-mono text-sm">{f.version}</span>
                      <span className="text-xs text-gray-400">{formatTimestamp(f.training_end)}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(f.features_importance || {})
                        .sort((a, b) => Math.abs(b[1] as number) - Math.abs(a[1] as number))
                        .slice(0, 6)
                        .map(([feature, importance]) => (
                          <div key={feature} className="flex items-center gap-1">
                            <div className="text-xs font-mono truncate flex-1">{feature}</div>
                            <div className="w-16 bg-gray-800 rounded-full h-1.5">
                              <div
                                className="bg-purple-500 h-1.5 rounded-full"
                                style={{ width: `${Math.abs(importance as number) * 100}%` }}
                              />
                            </div>
                          </div>
                        ))}
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