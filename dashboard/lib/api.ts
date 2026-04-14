import type { Strategy, BacktestResult, Trade, FreqAIInsights, PortfolioSummary, StrategyTemplate } from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

class APIClient {
  private baseURL: string
  
  constructor(baseURL: string = API_BASE) {
    this.baseURL = baseURL
  }
  
  private async request<T>(
    endpoint: string,
    options?: RequestInit
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })
    
    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(error.detail || `HTTP ${response.status}`)
    }
    
    return response.json()
  }
  
  // Strategies
  async getStrategies(): Promise<{ strategies: Strategy[] }> {
    return this.request('/api/strategies')
  }
  
  async getStrategy(strategyId: string): Promise<{ strategy: Strategy; container?: any; trades?: Trade[] }> {
    return this.request(`/api/strategies/${strategyId}`)
  }
  
  async createStrategy(data: {
    template_id: string
    name: string
    pairs: string[]
    exchange?: string
    dry_run?: boolean
    [key: string]: any
  }): Promise<{ strategy_id: string; status: string }> {
    return this.request('/api/strategies', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }
  
  async updateStrategy(
    strategyId: string,
    updates: Record<string, any>
  ): Promise<{ success: boolean }> {
    return this.request(`/api/strategies/${strategyId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }
  
  async deleteStrategy(strategyId: string): Promise<{ success: boolean }> {
    return this.request(`/api/strategies/${strategyId}`, {
      method: 'DELETE',
    })
  }
  
  async startStrategy(strategyId: string): Promise<any> {
    return this.request(`/api/strategies/${strategyId}/start`, {
      method: 'POST',
    })
  }
  
  async stopStrategy(strategyId: string): Promise<any> {
    return this.request(`/api/strategies/${strategyId}/stop`, {
      method: 'POST',
    })
  }
  
  async restartStrategy(strategyId: string): Promise<any> {
    return this.request(`/api/strategies/${strategyId}/restart`, {
      method: 'POST',
    })
  }
  
  async getStrategyLogs(
    strategyId: string,
    tail: number = 100
  ): Promise<{ logs: string[] }> {
    return this.request(`/api/strategies/${strategyId}/logs?tail=${tail}`)
  }
  
  async getStrategyTrades(
    strategyId: string,
    status: 'all' | 'open' | 'closed' = 'all',
    limit: number = 100
  ): Promise<{ trades: Trade[] }> {
    return this.request(
      `/api/strategies/${strategyId}/trades?status=${status}&limit=${limit}`
    )
  }
  
  // Backtest
  async runBacktest(data: {
    strategy_id: string
    timerange: string
    params?: Record<string, any>
  }): Promise<BacktestResult> {
    return this.request('/api/backtest', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }
  
  async getBacktestResults(
    strategyId?: string,
    limit: number = 50
  ): Promise<{ results: BacktestResult[] }> {
    const params = new URLSearchParams({ limit: String(limit) })
    if (strategyId) params.append('strategy_id', strategyId)
    return this.request(`/api/backtest/results?${params}`)
  }
  
  // Agent Reasoning
  async getStrategyReasoning(
    strategyId: string,
    hours: number = 24,
    limit: number = 100
  ): Promise<{ logs: any[] }> {
    return this.request(
      `/api/strategies/${strategyId}/reasoning?hours=${hours}&limit=${limit}`
    )
  }

  async getAgentLogs(
    strategyId: string,
    category?: string,
    level?: string,
    limit: number = 100,
    offset: number = 0
  ): Promise<{ logs: any[] }> {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) })
    if (category) params.append('category', category)
    if (level) params.append('level', level)
    return this.request(`/api/strategies/${strategyId}/agent-logs?${params}`)
  }

  // FreqAI
  async getFreqAIStatus(strategyId: string): Promise<FreqAIInsights> {
    return this.request(`/api/freqai/status?strategy_id=${strategyId}`)
  }

  async getFreqAIInsights(strategyId: string): Promise<{ history: any[] }> {
    return this.request(`/api/freqai/insights?strategy_id=${strategyId}`)
  }

  async getFreqAIModel(strategyId: string): Promise<any> {
    return this.request(`/api/freqai/model/${strategyId}`)
  }

  async getFreqAITraining(strategyId: string): Promise<any> {
    return this.request(`/api/freqai/training/${strategyId}`)
  }

  async getFreqAIPredictions(
    strategyId: string,
    limit: number = 100,
    outcomes: boolean = false
  ): Promise<{ predictions: any[] }> {
    return this.request(
      `/api/freqai/predictions/${strategyId}?limit=${limit}&outcomes=${outcomes}`
    )
  }

  async getFreqAIPerformance(strategyId: string): Promise<any> {
    return this.request(`/api/freqai/performance/${strategyId}`)
  }

  async getFreqAIFeatures(strategyId: string): Promise<{ evolution: any[] }> {
    return this.request(`/api/freqai/features/${strategyId}`)
  }

  // Research
  async getActiveResearch(): Promise<{ active: any[] }> {
    return this.request('/api/research/active')
  }

  async getResearchHistory(
    strategyId?: string,
    researchType?: string,
    limit: number = 50
  ): Promise<{ history: any[] }> {
    const params = new URLSearchParams({ limit: String(limit) })
    if (strategyId) params.append('strategy_id', strategyId)
    if (researchType) params.append('research_type', researchType)
    return this.request(`/api/research/history?${params}`)
  }

  async getResearchSummary(days: number = 30): Promise<any> {
    return this.request(`/api/research/summary?days=${days}`)
  }

  async getRecentDiscoveries(limit: number = 10): Promise<{ discoveries: any[] }> {
    return this.request(`/api/research/discoveries?limit=${limit}`)
  }

  async getScheduledResearch(): Promise<{ scheduled: any[] }> {
    return this.request('/api/research/scheduled')
  }

  // Portfolio
  async getPortfolio(): Promise<PortfolioSummary> {
    return this.request('/api/portfolio')
  }

  // Settings
  async getSettings(): Promise<any> {
    return this.request('/api/settings')
  }

  async updateSettings(settings: Record<string, any>): Promise<{ success: boolean }> {
    return this.request('/api/settings', {
      method: 'POST',
      body: JSON.stringify(settings),
    })
  }

  // Research Actions
  async startResearch(data: {
    strategy_id: string
    strategy_name?: string
    research_type: string
    epochs?: number
    timerange?: string
  }): Promise<{ research_id: string; status: string }> {
    return this.request('/api/research/start', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async cancelResearch(researchId: string): Promise<{ success: boolean }> {
    return this.request(`/api/research/cancel/${researchId}`, { method: 'POST' })
  }

  async applyResearchFindings(researchId: string): Promise<{ success: boolean; message: string; params: any; improvement: number }> {
    return this.request(`/api/research/${researchId}/apply`, { method: 'POST' })
  }

  async getApplicableResearch(strategyId?: string): Promise<{ applicable: any[] }> {
    const params = strategyId ? `?strategy_id=${strategyId}` : ''
    return this.request(`/api/research/applicable${params}`)
  }

  async scheduleResearch(data: {
    strategy_id: string
    research_type: string
    frequency: string
  }): Promise<{ schedule_id: string; status: string }> {
    return this.request('/api/research/schedule', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  // FreqAI Actions
  async enableFreqAI(
    strategyId: string,
    config?: { model?: string; train_period_days?: number; backtest_period_days?: number }
  ): Promise<{ success: boolean; message: string }> {
    return this.request(`/api/strategies/${strategyId}/enable-freqai`, {
      method: 'POST',
      body: JSON.stringify(config || {}),
    })
  }

  async disableFreqAI(strategyId: string): Promise<{ success: boolean; message: string }> {
    return this.request(`/api/strategies/${strategyId}/disable-freqai`, { method: 'POST' })
  }

  // Templates
  async getTemplates(): Promise<{ templates: Record<string, StrategyTemplate> }> {
    return this.request('/api/templates')
  }
  
  // Slack
  async testSlack(): Promise<{ success: boolean }> {
    return this.request('/api/slack/test', { method: 'POST' })
  }

  // Autonomous Agent
  async getAutonomousStatus(): Promise<any> {
    return this.request('/api/autonomous/status')
  }

  async startAutonomous(): Promise<{ status: string; message: string }> {
    return this.request('/api/autonomous/start', { method: 'POST' })
  }

  async stopAutonomous(): Promise<{ status: string; message: string }> {
    return this.request('/api/autonomous/stop', { method: 'POST' })
  }

  async getDecisions(params?: {
    agent_type?: string
    decision_type?: string
    since_hours?: number
    limit?: number
  }): Promise<{ decisions: any[] }> {
    const searchParams = new URLSearchParams()
    if (params?.agent_type) searchParams.append('agent_type', params.agent_type)
    if (params?.decision_type) searchParams.append('decision_type', params.decision_type)
    if (params?.since_hours) searchParams.append('since_hours', String(params.since_hours))
    if (params?.limit) searchParams.append('limit', String(params.limit))
    return this.request(`/api/autonomous/decisions?${searchParams.toString()}`)
  }

  async getDecision(decisionId: string): Promise<any> {
    return this.request(`/api/autonomous/decisions/${decisionId}`)
  }

  async getPendingApprovals(): Promise<{ approvals: any[] }> {
    return this.request('/api/autonomous/approvals')
  }

  async approveDecision(decisionId: string, reason?: string): Promise<any> {
    return this.request(`/api/autonomous/approvals/${decisionId}/approve`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  }

  async rejectDecision(decisionId: string, reason: string): Promise<any> {
    return this.request(`/api/autonomous/approvals/${decisionId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  }

  async getFindings(params?: {
    source?: string
    finding_type?: string
    since_hours?: number
    limit?: number
  }): Promise<{ findings: any[] }> {
    const searchParams = new URLSearchParams()
    if (params?.source) searchParams.append('source', params.source)
    if (params?.finding_type) searchParams.append('finding_type', params.finding_type)
    if (params?.since_hours) searchParams.append('since_hours', String(params.since_hours))
    if (params?.limit) searchParams.append('limit', String(params.limit))
    return this.request(`/api/autonomous/findings?${searchParams.toString()}`)
  }

  async applyFinding(findingId: string, strategyId: string): Promise<any> {
    return this.request(`/api/autonomous/findings/${findingId}/apply`, {
      method: 'POST',
      body: JSON.stringify({ strategy_id: strategyId }),
    })
  }

  async runHyperopt(data: {
    strategy_id: string
    epochs?: number
    timerange?: string
  }): Promise<any> {
    return this.request('/api/autonomous/hyperopt', {
      method: 'POST',
      body: JSON.stringify(data),
    })
  }

  async getHyperoptStatus(hyperoptId: string): Promise<any> {
    return this.request(`/api/autonomous/hyperopt/status/${hyperoptId}`)
  }

  async cancelHyperopt(hyperoptId: string): Promise<any> {
    return this.request(`/api/autonomous/hyperopt/${hyperoptId}/cancel`, { method: 'POST' })
  }

  async getStrategiesHealth(): Promise<{ strategies: any[] }> {
    return this.request('/api/autonomous/strategies/health')
  }

  async deprecateStrategy(strategyId: string, reason: string): Promise<any> {
    return this.request(`/api/autonomous/strategies/${strategyId}/deprecate`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  }

  async promoteStrategy(strategyId: string): Promise<any> {
    return this.request(`/api/autonomous/strategies/${strategyId}/promote`, { method: 'POST' })
  }

  async getRiskReport(): Promise<any> {
    return this.request('/api/autonomous/risk')
  }

  async searchMemory(query: string, limit?: number): Promise<{ results: any[] }> {
    const searchParams = new URLSearchParams({ query })
    if (limit) searchParams.append('limit', String(limit))
    return this.request(`/api/autonomous/memory/search?${searchParams.toString()}`)
  }

  async getMemorySummary(): Promise<any> {
    return this.request('/api/autonomous/memory/summary')
  }

  async getAutonomousConfig(): Promise<any> {
    return this.request('/api/autonomous/config')
  }

  async updateAutonomousConfig(config: Record<string, any>): Promise<any> {
    return this.request('/api/autonomous/config', {
      method: 'PUT',
      body: JSON.stringify(config),
    })
  }

  async getLLMUsage(): Promise<any> {
    return this.request('/api/autonomous/llm/usage')
  }

  // Activity Stream
  async getActivity(params?: {
    limit?: number
    agent?: string
    activity_type?: string
    since_hours?: number
  }): Promise<{ events: any[]; total: number }> {
    const searchParams = new URLSearchParams()
    if (params?.limit) searchParams.append('limit', String(params.limit))
    if (params?.agent) searchParams.append('agent', params.agent)
    if (params?.activity_type) searchParams.append('activity_type', params.activity_type)
    if (params?.since_hours) searchParams.append('since_hours', String(params.since_hours))
    return this.request(`/api/autonomous/activity?${searchParams.toString()}`)
  }

  async getResearchActivity(researchId: string): Promise<{ research_id: string; events: any[] }> {
    return this.request(`/api/autonomous/activity/${researchId}`)
  }

  // Health
  async healthCheck(): Promise<{ status: string }> {
    return this.request('/health')
  }
}

export const api = new APIClient()