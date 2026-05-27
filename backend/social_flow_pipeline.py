"""
Social Sentiment & Options Flow Data Pipeline for Confluence Decoder

Integrates algorithms from scraped GitHub repos:
- shirosaidev/stocksight: VADER + TextBlob Twitter sentiment
- jasti/Stock-Predictor: SGDClassifier sentiment analysis
- Matteo-Ferrara/gex-tracker: GEX calculation from CBOE data
- Proshotv2/Gamma-Vanna-Options-Exposure: Gamma/Vanna exposure
- Buzzfund/UnusualOptions: Unusual options activity detection
- FullStackCraft/floe: Options analytics TypeScript library

Also handles X/Twitter data collection via xurl (when authenticated).
"""

import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

import numpy as np

logger = logging.getLogger(__name__)

# ============================================================
# Data Models
# ============================================================

@dataclass
@dataclass
@dataclass
@dataclass
class TwitterCollector:
    """
    Collects tweets using xurl CLI.
    Requires xurl to be authenticated (user must set up X API credentials).
    """
    
    def __init__(self):
        self.options_accounts = [
            "unusual_whales", "OptionsFlow", "squeezetrade",
            "TradeTheFlow", "volflow", "darkflowtrading",
        ]
        self.search_queries = [
            "options flow unusual activity",
            "gamma exposure GEX",
            "options sweep block trade",
            "0DTE options",
            "gamma squeeze",
        ]
    
    def _run_xurl(self, args: List[str]) -> Optional[str]:
        """Run xurl command and return output."""
        import subprocess
        try:
            result = subprocess.run(
                ["xurl"] + args,
                capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                return result.stdout
            logger.warning(f"xurl error: {result.stderr[:200]}")
            return None
        except FileNotFoundError:
            logger.warning("xurl not found. Install with: npm install -g @xdevplatform/xurl")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("xurl command timed out")
            return None
    
    def is_authenticated(self) -> bool:
        """Check if xurl is authenticated."""
        output = self._run_xurl(["auth", "status"])
        if output and "oauth2" in output.lower():
            return True
        return False
    
    def search_tweets(self, query: str, count: int = 20) -> List[Dict]:
        """Search for tweets using xurl."""
        output = self._run_xurl(["search", query, "-n", str(count)])
        if not output:
            return []
        
        try:
            data = json.loads(output)
            tweets = []
            if "data" in data:
                for t in data["data"]:
                    tweets.append({
                        "id": t.get("id", ""),
                        "text": t.get("text", ""),
                        "author": t.get("author_id", ""),
                        "created_at": t.get("created_at", ""),
                        "likes": t.get("public_metrics", {}).get("like_count", 0),
                        "retweets": t.get("public_metrics", {}).get("retweet_count", 0),
                    })
            return tweets
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse xurl search output: {output[:200]}")
            return []
    
    def get_user_timeline(self, username: str, count: int = 20) -> List[Dict]:
        """Get user timeline using xurl."""
        output = self._run_xurl(["timeline", "--of", username, "-n", str(count)])
        if not output:
            return []
        
        try:
            data = json.loads(output)
            tweets = []
            if "data" in data:
                for t in data["data"]:
                    tweets.append({
                        "id": t.get("id", ""),
                        "text": t.get("text", ""),
                        "author": username,
                        "created_at": t.get("created_at", ""),
                        "likes": t.get("public_metrics", {}).get("like_count", 0),
                        "retweets": t.get("public_metrics", {}).get("retweet_count", 0),
                    })
            return tweets
        except json.JSONDecodeError:
            return []
    
    def collect_options_sentiment(self, ticker: str = "SPY") -> List[Dict]:
        """Collect options-related tweets for a ticker."""
        all_tweets = []
        
        # Search for ticker + options
        queries = [
            f"${ticker} options",
            f"{ticker} gamma exposure",
            f"{ticker} unusual options",
            f"{ticker} options flow",
        ]
        
        for q in queries:
            tweets = self.search_tweets(q, count=10)
            all_tweets.extend(tweets)
            time.sleep(1)  # Rate limit
        
        return all_tweets


# ============================================================
# Utility: Save/Load reports
# ============================================================

def save_report(report: SocialFlowReport, path: str):
    """Save a report to JSON."""
    data = asdict(report)
    # Convert nested dataclasses
    if report.sentiment is not None:
        data["sentiment"] = asdict(report.sentiment)
    if data.get("flow_signals"):
        data["flow_signals"] = [asdict(s) for s in report.flow_signals]
    
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Report saved to {path}")


def load_report(path: str) -> Optional[Dict]:
    """Load a report from JSON."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
