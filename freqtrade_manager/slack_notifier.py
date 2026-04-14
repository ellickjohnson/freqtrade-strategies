import httpx
import os
from typing import Optional, Dict, Any, List
from datetime import datetime


class SlackNotifier:
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("SLACK_WEBHOOK_URL")
        self.enabled = bool(self.webhook_url)

    async def send(
        self,
        message: str,
        blocks: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        if not self.enabled:
            return False

        payload = {"text": message}
        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url, json=payload, timeout=10.0
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Slack notification failed: {e}")
            return False

    async def send_strategy_started(
        self, strategy_name: str, pairs: List[str], port: int
    ) -> bool:
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🚀 Strategy Started: {strategy_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Pairs:*\n{', '.join(pairs)}"},
                    {"type": "mrkdwn", "text": f"*Port:*\n{port}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    },
                    {"type": "mrkdwn", "text": f"*Mode:*\nPaper Trading"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": "📈 Freqtrade Strategy Dashboard"}
                ],
            },
        ]
        return await self.send(f"Strategy {strategy_name} started", blocks=blocks)

    async def send_strategy_stopped(
        self, strategy_name: str, duration: Optional[str] = None
    ) -> bool:
        fields = [
            {"type": "mrkdwn", "text": f"*Strategy:*\n{strategy_name}"},
            {
                "type": "mrkdwn",
                "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            },
        ]

        if duration:
            fields.append({"type": "mrkdwn", "text": f"*Duration:*\n{duration}"})

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"⏹ Strategy Stopped: {strategy_name}",
                },
            },
            {"type": "section", "fields": fields},
        ]
        return await self.send(f"Strategy {strategy_name} stopped", blocks=blocks)

    async def send_backtest_complete(
        self,
        strategy_name: str,
        profit_pct: float,
        trades: int,
        win_rate: float,
        sharpe: Optional[float] = None,
    ) -> bool:
        profit_emoji = "📈" if profit_pct > 0 else "📉"
        profit_color = "good" if profit_pct > 0 else "danger"

        fields = [
            {"type": "mrkdwn", "text": f"*Profit:*\n{profit_emoji} {profit_pct:.2f}%"},
            {"type": "mrkdwn", "text": f"*Trades:*\n{trades}"},
            {"type": "mrkdwn", "text": f"*Win Rate:*\n{win_rate:.1f}%"},
        ]

        if sharpe:
            fields.append({"type": "mrkdwn", "text": f"*Sharpe:*\n{sharpe:.2f}"})

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"✅ Backtest Complete: {strategy_name}",
                },
            },
            {"type": "section", "fields": fields},
        ]

        return await self.send(f"Backtest {strategy_name} complete", blocks=blocks)

    async def send_freqai_trained(
        self, strategy_name: str, accuracy: float, features: List[Dict[str, float]]
    ) -> bool:
        top_features = features[:3]
        feature_text = "\n".join(
            [
                f"{i + 1}. {f['name']}: {f['importance']:.3f}"
                for i, f in enumerate(top_features)
            ]
        )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 FreqAI Model Trained: {strategy_name}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Accuracy:*\n{accuracy:.1f}%"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Time:*\n{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Top Features:*\n{feature_text}"},
            },
        ]

        return await self.send(f"FreqAI {strategy_name} trained", blocks=blocks)

    async def send_trade_alert(
        self,
        strategy_name: str,
        action: str,
        pair: str,
        price: float,
        reason: str,
        pnl: Optional[float] = None,
    ) -> bool:
        action_emoji = "💚" if action == "buy" else "💰"
        action_text = "Bought" if action == "buy" else "Sold"

        fields = [
            {"type": "mrkdwn", "text": f"*Strategy:*\n{strategy_name}"},
            {"type": "mrkdwn", "text": f"*Action:*\n{action_text}"},
            {"type": "mrkdwn", "text": f"*Pair:*\n{pair}"},
            {"type": "mrkdwn", "text": f"*Price:*\n${price:,.2f}"},
        ]

        if pnl is not None:
            pnl_emoji = "📈" if pnl > 0 else "📉"
            fields.append(
                {"type": "mrkdwn", "text": f"*P&L:*\n{pnl_emoji} ${pnl:,.2f}"}
            )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{action_emoji} Trade Alert: {pair}",
                },
            },
            {"type": "section", "fields": fields},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Reason:*\n{reason}"},
            },
        ]

        return await self.send(f"Trade {action} {pair}", blocks=blocks)

    async def send_error(
        self, strategy_name: str, error_message: str, error_type: Optional[str] = None
    ) -> bool:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"❌ Error: {strategy_name}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Strategy:*\n{strategy_name}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Type:*\n{error_type or 'Runtime Error'}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"```{error_message[:500]}```"},
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"⚠️ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    }
                ],
            },
        ]

        return await self.send(f"Error in {strategy_name}", blocks=blocks)

    async def send_daily_summary(
        self,
        total_pnl: float,
        daily_pnl: float,
        total_trades: int,
        win_rate: float,
        active_strategies: int,
    ) -> bool:
        pnl_emoji = "📈" if daily_pnl > 0 else "📉"

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 Daily Portfolio Summary"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Total P&L:*\n${total_pnl:,.2f}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Today:*\n{pnl_emoji} ${daily_pnl:,.2f}",
                    },
                    {"type": "mrkdwn", "text": f"*Total Trades:*\n{total_trades}"},
                    {"type": "mrkdwn", "text": f"*Win Rate:*\n{win_rate:.1f}%"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Active Strategies:*\n{active_strategies}",
                    },
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"📅 {datetime.now().strftime('%Y-%m-%d')}",
                    }
                ],
            },
        ]

        return await self.send("Daily summary", blocks=blocks)
