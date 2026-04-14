from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class StrategyStatus(str, Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"


class TradeAction(str, Enum):
    BUY = "buy"
    SELL = "sell"


class MarketRegime(str, Enum):
    RANGING = "ranging"
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    VOLATILE = "volatile"


class StrategyType(str, Enum):
    GRID_DCA = "grid_dca"
    OSCILLATOR_CONFLUENCE = "oscillator_confluence"
    SCALPING_QUICK = "scalping_quick"
    BREAKOUT_MOMENTUM = "breakout_momentum"
    TREND_MOMENTUM = "trend_momentum"
    CUSTOM = "custom"


class StrategyConfig(BaseModel):
    id: str = Field(..., description="Unique strategy identifier")
    name: str = Field(..., description="Display name")
    strategy_type: StrategyType = Field(default=StrategyType.CUSTOM)
    description: Optional[str] = None

    strategy_file: str = Field(..., description="Strategy Python filename")
    config_path: str = Field(..., description="Path to config file")

    exchange: str = Field(default="kraken")
    pairs: List[str] = Field(default_factory=lambda: ["BTC/USDT"])
    timeframe: str = Field(default="15m")
    stake_amount: float = Field(default=100.0)
    max_open_trades: int = Field(default=3)
    dry_run: bool = Field(default=True)

    stoploss: float = Field(default=-0.10)
    trailing_stop: bool = Field(default=False)
    trailing_stop_positive: float = Field(default=0.01)
    trailing_stop_positive_offset: float = Field(default=0.02)
    trailing_only_offset_is_reached: bool = Field(default=False)

    use_freqai: bool = Field(default=False)
    freqai_model: Optional[str] = None

    docker_port: Optional[int] = Field(default=None, description="Assigned Docker port")
    container_id: Optional[str] = Field(default=None)
    container_name: Optional[str] = Field(default=None)

    enabled: bool = Field(default=True)
    status: StrategyStatus = Field(default=StrategyStatus.STOPPED)

    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    custom_params: Dict[str, Any] = Field(default_factory=dict)


class Trade(BaseModel):
    id: str
    strategy_id: str
    pair: str
    action: TradeAction
    open_rate: float
    close_rate: Optional[float] = None
    stake_amount: float
    amount: float
    open_date: datetime
    close_date: Optional[datetime] = None
    is_open: bool = True
    close_profit: Optional[float] = None
    close_profit_abs: Optional[float] = None
    stop_loss: Optional[float] = None
    initial_stop_loss: Optional[float] = None
    exit_reason: Optional[str] = None


class BacktestResult(BaseModel):
    id: str
    strategy_id: str
    run_at: datetime
    time_range: str
    config_snapshot: Dict[str, Any]
    results: Dict[str, Any]
    metrics: Dict[str, Any]


class FreqAIInsights(BaseModel):
    strategy_id: str
    model_type: str
    trained_at: datetime
    accuracy: float
    precision: float
    recall: float
    feature_importance: List[Dict[str, float]]
    regime: MarketRegime
    recent_predictions: List[Dict[str, Any]]


class TradeExplanation(BaseModel):
    trade_id: str
    pair: str
    action: TradeAction
    timestamp: datetime

    freqai_confidence: Optional[float] = None
    freqai_prediction: Optional[str] = None

    traditional_signals: List[Dict[str, Any]] = Field(default_factory=list)
    feature_contributions: List[Dict[str, float]] = Field(default_factory=list)

    market_regime: Optional[MarketRegime] = None
    supporting_indicators: Dict[str, Any] = Field(default_factory=dict)


class PortfolioSummary(BaseModel):
    total_pnl: float
    total_pnl_percent: float
    daily_pnl: float
    weekly_pnl: float
    monthly_pnl: float

    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    open_trades: int
    avg_trade_duration: float

    strategies_active: int
    strategies_stopped: int

    last_updated: datetime


class WebSocketMessage(BaseModel):
    event: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)


class StrategyTemplate(BaseModel):
    id: str
    name: str
    strategy_type: StrategyType
    strategy_file: str
    default_config: Dict[str, Any]
    description: str
    params: List[Dict[str, Any]]
