import pickle
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import os


class FreqAIAdapter:
    def __init__(self, user_data_dir: str = "/user_data"):
        self.models_dir = Path(user_data_dir) / "models"
        self.user_data_dir = Path(user_data_dir)

    def get_model_path(self, strategy_id: str) -> Optional[Path]:
        strategy_models = self.models_dir / strategy_id
        if not strategy_models.exists():
            return None

        model_files = sorted(
            strategy_models.glob("*.pkl"), key=lambda p: p.stat().st_mtime, reverse=True
        )

        if not model_files:
            return None

        return model_files[0]

    def get_latest_model_info(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        model_path = self.get_model_path(strategy_id)
        if not model_path:
            return None

        try:
            with open(model_path, "rb") as f:
                model = pickle.load(f)

            metadata_path = model_path.with_suffix(".metadata.json")
            metadata = {}
            if metadata_path.exists():
                with open(metadata_path, "r") as f:
                    metadata = json.load(f)

            model_type = type(model).__name__

            feature_importance = []
            if hasattr(model, "feature_importances_"):
                feature_importance = self._extract_feature_importance(model)
            elif hasattr(model, "coef_"):
                feature_importance = self._extract_coefficient_importance(model)

            return {
                "model_path": str(model_path),
                "model_type": model_type,
                "trained_at": datetime.fromtimestamp(model_path.stat().st_mtime),
                "feature_importance": feature_importance,
                "accuracy": metadata.get("accuracy"),
                "precision": metadata.get("precision"),
                "recall": metadata.get("recall"),
                "metadata": metadata,
            }
        except Exception as e:
            print(f"Error loading model: {e}")
            return None

    def _extract_feature_importance(self, model) -> List[Dict[str, float]]:
        if not hasattr(model, "feature_importances_"):
            return []

        importances = model.feature_importances_
        feature_names = getattr(
            model,
            "feature_names_in_",
            [f"feature_{i}" for i in range(len(importances))],
        )

        feature_importance = [
            {"name": str(name), "importance": float(imp)}
            for name, imp in zip(feature_names, importances)
        ]

        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

        return feature_importance

    def _extract_coefficient_importance(self, model) -> List[Dict[str, float]]:
        if not hasattr(model, "coef_"):
            return []

        coefficients = abs(model.coef_).mean(axis=0)
        feature_names = getattr(
            model,
            "feature_names_in_",
            [f"feature_{i}" for i in range(len(coefficients))],
        )

        feature_importance = [
            {"name": str(name), "importance": float(coef)}
            for name, coef in zip(feature_names, coefficients)
        ]

        feature_importance.sort(key=lambda x: x["importance"], reverse=True)

        return feature_importance

    def get_explainability(
        self, strategy_id: str, trade_data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        model_info = self.get_latest_model_info(strategy_id)
        if not model_info:
            return {"error": "No model found"}

        feature_importance = model_info["feature_importance"]

        explanation = {
            "model_type": model_info["model_type"],
            "confidence": model_info.get("accuracy"),
            "top_features": feature_importance[:5] if feature_importance else [],
            "contributions": [],
        }

        if trade_data and feature_importance:
            total_importance = sum(f["importance"] for f in feature_importance)

            for feature in feature_importance[:10]:
                feature_name = feature["name"]
                feature_value = trade_data.get("indicators", {}).get(feature_name)

                if feature_value is not None:
                    contribution = (
                        feature["importance"] / total_importance
                        if total_importance > 0
                        else 0
                    )
                    explanation["contributions"].append(
                        {
                            "feature": feature_name,
                            "value": feature_value,
                            "importance": feature["importance"],
                            "contribution_pct": round(contribution * 100, 2),
                        }
                    )

        return explanation

    def get_recent_predictions(
        self, strategy_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        predictions_path = self.user_data_dir / strategy_id / "freqai_predictions.json"

        if not predictions_path.exists():
            return []

        try:
            with open(predictions_path, "r") as f:
                predictions = json.load(f)

            return predictions[-limit:]
        except Exception as e:
            print(f"Error reading predictions: {e}")
            return []

    def get_training_history(self, strategy_id: str) -> List[Dict[str, Any]]:
        training_path = self.models_dir / strategy_id / "training_history.json"

        if not training_path.exists():
            return []

        try:
            with open(training_path, "r") as f:
                history = json.load(f)

            return history
        except Exception as e:
            print(f"Error reading training history: {e}")
            return []

    def detect_market_regime(
        self, strategy_id: str, indicators: Dict[str, float]
    ) -> str:
        adx = indicators.get("adx", 20)
        atr = indicators.get("atr", 0)
        volume_mean = indicators.get("volume_mean", 1)
        current_volume = indicators.get("volume", 1)
        ema_trend = indicators.get("close") - indicators.get(
            "ema_200", indicators.get("close", 0)
        )

        volume_ratio = current_volume / volume_mean if volume_mean > 0 else 1

        if adx > 25:
            if ema_trend > 0:
                return "trending_up"
            else:
                return "trending_down"
        elif volume_ratio > 2:
            return "volatile"
        else:
            return "ranging"

    def get_regime_explanation(self, regime: str) -> Dict[str, Any]:
        explanations = {
            "trending_up": {
                "description": "Strong upward trend detected",
                "characteristics": [
                    "ADX > 25",
                    "Price above EMA200",
                    "Momentum bullish",
                ],
                "strategy_hint": "Trend-following strategies preferred",
                "risk_level": "medium",
            },
            "trending_down": {
                "description": "Strong downward trend detected",
                "characteristics": [
                    "ADX > 25",
                    "Price below EMA200",
                    "Momentum bearish",
                ],
                "strategy_hint": "Consider short positions or stay out",
                "risk_level": "high",
            },
            "ranging": {
                "description": "Low volatility, sideways movement",
                "characteristics": ["ADX < 25", "Price oscillating", "Low volume"],
                "strategy_hint": "Mean reversion strategies work well",
                "risk_level": "low",
            },
            "volatile": {
                "description": "High volatility, unpredictable movement",
                "characteristics": [
                    "Volume spike",
                    "Wide price swings",
                    "Uncertain direction",
                ],
                "strategy_hint": "Use tight stop losses, reduce position size",
                "risk_level": "high",
            },
        }

        return explanations.get(
            regime,
            {
                "description": "Unknown market regime",
                "characteristics": [],
                "strategy_hint": "Exercise caution",
                "risk_level": "unknown",
            },
        )

    def analyze_trade_reasoning(
        self, strategy_id: str, trade_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        model_info = self.get_latest_model_info(strategy_id)

        explanation = {
            "trade_id": trade_info.get("id"),
            "pair": trade_info.get("pair"),
            "action": trade_info.get("action"),
            "timestamp": datetime.now(),
            "freqai_confidence": None,
            "freqai_prediction": None,
            "traditional_signals": [],
            "feature_contributions": [],
            "market_regime": None,
            "supporting_indicators": {},
        }

        if model_info:
            explanation["freqai_confidence"] = model_info.get("accuracy")
            explanation["model_type"] = model_info.get("model_type")

            if model_info.get("feature_importance"):
                explanation["feature_contributions"] = model_info["feature_importance"][
                    :5
                ]

        indicators = trade_info.get("indicators", {})

        signals = []

        rsi = indicators.get("rsi")
        if rsi:
            if rsi < 30:
                signals.append(
                    {
                        "indicator": "RSI",
                        "value": rsi,
                        "signal": "Oversold",
                        "strength": "strong" if rsi < 25 else "moderate",
                    }
                )
            elif rsi > 70:
                signals.append(
                    {
                        "indicator": "RSI",
                        "value": rsi,
                        "signal": "Overbought",
                        "strength": "strong" if rsi > 75 else "moderate",
                    }
                )

        macd = indicators.get("macd")
        macd_signal = indicators.get("macd_signal")
        if macd and macd_signal:
            if macd > macd_signal:
                signals.append(
                    {
                        "indicator": "MACD",
                        "value": macd,
                        "signal": "Bullish crossover",
                        "strength": "moderate",
                    }
                )
            else:
                signals.append(
                    {
                        "indicator": "MACD",
                        "value": macd,
                        "signal": "Bearish crossover",
                        "strength": "moderate",
                    }
                )

        close = indicators.get("close")
        ema_20 = indicators.get("ema_20")
        if close and ema_20:
            if close > ema_20:
                signals.append(
                    {
                        "indicator": "EMA20",
                        "value": close - ema_20,
                        "signal": "Price above EMA",
                        "strength": "weak",
                    }
                )

        explanation["traditional_signals"] = signals

        regime = self.detect_market_regime(strategy_id, indicators)
        explanation["market_regime"] = regime
        explanation["regime_explanation"] = self.get_regime_explanation(regime)

        explanation["supporting_indicators"] = {
            "rsi": rsi,
            "macd": macd,
            "volume_ratio": indicators.get("volume", 1)
            / indicators.get("volume_mean", 1),
            "atr": indicators.get("atr"),
            "adx": indicators.get("adx"),
        }

        return explanation
