export type StrategyStatus = 'running' | 'stopped' | 'error' | 'starting' | 'stopping'
export type StrategyType = 'grid_dca' | 'oscillator_confluence' | 'scalping_quick' | 'breakout_momentum' | 'trend_momentum' | 'custom'
export type TradeAction = 'buy' | 'sell'
export type MarketRegime = 'ranging' | 'trending_up' | 'trending_down' | 'volatile'

export interface Strategy {
  id: string
  name: string
  strategy_type: StrategyType
  description?: string
  strategy_file: string
  config_path: string
  exchange: string
  pairs: string[]
  timeframe: string
  stake_amount: number
  max_open_trades: number
  dry_run: boolean
  stoploss: number
  trailing_stop: boolean
  use_freqai: boolean
  freqai_model?: string
  docker_port?: number
  container_id?: string
  container_name?: string
  container_status?: ContainerStatus
  enabled: boolean
  status: StrategyStatus
  created_at: string
  updated_at: string
  custom_params: Record<string, any>
}

export interface StrategyTemplate {
  id: string
  name: string
  strategy_type: StrategyType
  strategy_file: string
  description: string
  default_config: Record<string, any>
  params: TemplateParameter[]
}

export interface TemplateParameter {
  name: string
  label: string
  type: 'slider' | 'number' | 'select' | 'text' | 'boolean'
  min?: number
  max?: number
  default: any
  options?: { value: string; label: string }[]
}

export interface BacktestResult {
  id: string
  strategy_id: string
  run_at: string
  time_range: string
  config_snapshot: Record<string, any>
  results: Record<string, any>
  metrics: {
    total_trades: number
    profit_total_abs: number
    profit_total_percent: number
    profit_mean_percent: number
    win_rate: number
    drawdown?: number
    sharpe?: number
    sortino?: number
  }
}

export interface Trade {
  id: string
  strategy_id: string
  pair: string
  action: TradeAction
  open_rate: number
  close_rate?: number
  stake_amount: number
  amount: number
  open_date: string
  close_date?: string
  is_open: boolean
  close_profit?: number
  close_profit_abs?: number
  stop_loss?: number
  initial_stop_loss?: number
  exit_reason?: string
}

export interface FreqAIInsights {
  strategy_id: string
  model_type: string
  trained_at: string
  accuracy: number
  precision: number
  recall: number
  feature_importance: Array<{ name: string; importance: number }>
  regime: MarketRegime
  recent_predictions: Array<{
    timestamp: string
    pair: string
    prediction: 'long' | 'short'
    confidence: number
    outcome?: 'win' | 'loss' | 'pending'
  }>
}

export interface PortfolioSummary {
  total_pnl: number
  total_pnl_percent: number
  daily_pnl: number
  weekly_pnl: number
  monthly_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  open_trades: number
  strategies_active: number
  strategies_stopped: number
  last_updated: string
}

export interface WebSocketMessage {
  event: string
  data: any
  timestamp: string
}

export interface ContainerStatus {
  container_id: string
  container_name: string
  status: string
  started_at?: string
  image: string
  ports: Record<string, any>
}

export interface HealthCheck {
  healthy: boolean
  status: string
  api_responding?: boolean
  port?: number
  message?: string
}