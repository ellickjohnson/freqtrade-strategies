import { create } from 'zustand'
import type { Strategy, Trade, BacktestResult, FreqAIInsights, PortfolioSummary } from './types'

interface StrategyStore {
  // State
  strategies: Strategy[]
  selectedStrategy: Strategy | null
  trades: Trade[]
  backtestResults: BacktestResult[]
  freqaiInsights: FreqAIInsights | null
  portfolio: PortfolioSummary | null
  logs: Record<string, string[]>
  errors: Record<string, string>
  isLoading: boolean
  
  // Actions
  setStrategies: (strategies: Strategy[]) => void
  addStrategy: (strategy: Strategy) => void
  updateStrategy: (strategyId: string, updates: Partial<Strategy>) => void
  removeStrategy: (strategyId: string) => void
  setSelectedStrategy: (strategy: Strategy | null) => void
  
  setTrades: (trades: Trade[]) => void
  addTrade: (trade: Trade) => void
  updateTrade: (trade: Partial<Trade>) => void
  
  setBacktestResults: (results: BacktestResult[]) => void
  addBacktestResult: (result: BacktestResult) => void
  
  setFreqAIInsights: (insights: FreqAIInsights) => void
  
  setPortfolio: (portfolio: PortfolioSummary) => void
  
  addLog: (log: { strategy_id: string; message: string; timestamp: string }) => void
  clearLogs: (strategyId?: string) => void
  
  setError: (error: { strategy_id?: string; message: string }) => void
  clearErrors: () => void
  
  setLoading: (loading: boolean) => void
  
  // Real-time updates
  updateStrategyStatus: (data: { strategy_id: string; status: string }) => void
}

export const useStrategyStore = create<StrategyStore>((set, get) => ({
  // Initial state
  strategies: [],
  selectedStrategy: null,
  trades: [],
  backtestResults: [],
  freqaiInsights: null,
  portfolio: null,
  logs: {},
  errors: {},
  isLoading: false,
  
  // Strategy actions
  setStrategies: (strategies) => set({ strategies }),
  
  addStrategy: (strategy) =>
    set((state) => ({
      strategies: [strategy, ...state.strategies],
    })),
  
  updateStrategy: (strategyId, updates) =>
    set((state) => ({
      strategies: state.strategies.map((s) =>
        s.id === strategyId ? { ...s, ...updates } : s
      ),
      selectedStrategy:
        state.selectedStrategy?.id === strategyId
          ? { ...state.selectedStrategy, ...updates }
          : state.selectedStrategy,
    })),
  
  removeStrategy: (strategyId) =>
    set((state) => ({
      strategies: state.strategies.filter((s) => s.id !== strategyId),
      selectedStrategy:
        state.selectedStrategy?.id === strategyId ? null : state.selectedStrategy,
    })),
  
  setSelectedStrategy: (strategy) => set({ selectedStrategy: strategy }),
  
  // Trade actions
  setTrades: (trades) => set({ trades }),
  
  addTrade: (trade) =>
    set((state) => ({
      trades: [trade, ...state.trades],
    })),
  
  updateTrade: (trade) =>
    set((state) => ({
      trades: state.trades.map((t) =>
        t.id === trade.id ? { ...t, ...trade } : t
      ),
    })),
  
  // Backtest actions
  setBacktestResults: (results) => set({ backtestResults: results }),
  
  addBacktestResult: (result) =>
    set((state) => ({
      backtestResults: [result, ...state.backtestResults].slice(0, 50),
    })),
  
  // FreqAI actions
  setFreqAIInsights: (insights) => set({ freqaiInsights: insights }),
  
  // Portfolio actions
  setPortfolio: (portfolio) => set({ portfolio }),
  
  // Log actions
  addLog: (log) =>
    set((state) => {
      const logs = { ...state.logs }
      if (!logs[log.strategy_id]) {
        logs[log.strategy_id] = []
      }
      logs[log.strategy_id] = [
        log.message,
        ...logs[log.strategy_id].slice(0, 99),
      ]
      return { logs }
    }),
  
  clearLogs: (strategyId) =>
    set((state) => {
      if (strategyId) {
        const logs = { ...state.logs }
        delete logs[strategyId]
        return { logs }
      }
      return { logs: {} }
    }),
  
  // Error actions
  setError: (error) =>
    set((state) => ({
      errors: {
        ...state.errors,
        [error.strategy_id || 'global']: error.message,
      },
    })),
  
  clearErrors: () => set({ errors: {} }),
  
  // Loading actions
  setLoading: (loading) => set({ isLoading: loading }),
  
  // Real-time updates
  updateStrategyStatus: (data) =>
    set((state) => ({
      strategies: state.strategies.map((s) =>
        s.id === data.strategy_id ? { ...s, status: data.status as any } : s
      ),
    })),
}))