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
class TweetSentiment:
    """Single tweet with sentiment analysis."""
    id: str
    text: str
    author: str
    created_at: str
    likes: int = 0
    retweets: int = 0
    vader_compound: float = 0.0
    vader_pos: float = 0.0
    vader_neg: float = 0.0
    textblob_polarity: float = 0.0
    textblob_subjectivity: float = 0.0
    ticker_mentions: List[str] = field(default_factory=list)
    is_options_related: bool = False

@dataclass
class TickerSentiment:
    """Aggregated sentiment for a ticker."""
    ticker: str
    tweet_count: int = 0
    avg_vader: float = 0.0
    avg_textblob: float = 0.0
    bullish_count: int = 0
    bearish_count: int = 0
    neutral_count: int = 0
    total_likes: int = 0
    total_retweets: int = 0
    sentiment_label: str = "neutral"  # bullish, bearish, neutral
    confidence: float = 0.0
    top_tweets: List[Dict] = field(default_factory=list)
    updated_at: str = ""

@dataclass
class OptionsFlowSignal:
    """Unusual options activity signal."""
    ticker: str
    strike: float
    expiry: str
    option_type: str  # call or put
    volume: int
    open_interest: int
    premium_usd: float
    iv: float
    spot_price: float
    volume_oi_ratio: float = 0.0
    signal_type: str = ""  # sweep, block, unusual, dark_pool
    timestamp: str = ""
    source: str = ""

@dataclass
class SocialFlowReport:
    """Combined social + flow report for a ticker."""
    ticker: str
    generated_at: str = ""
    sentiment: Optional[TickerSentiment] = None
    flow_signals: List[OptionsFlowSignal] = field(default_factory=list)
    gex_summary: Dict[str, Any] = field(default_factory=dict)
    social_score: float = 0.0  # -1 to 1
    flow_score: float = 0.0    # -1 to 1
    combined_score: float = 0.0  # -1 to 1
    signals: List[str] = field(default_factory=list)


# ============================================================
# Twitter/X Sentiment Analyzer
# Based on: shirosaidev/stocksight + jasti/Stock-Predictor
# ============================================================

class TwitterSentimentAnalyzer:
    """
    Analyzes Twitter sentiment for stock tickers.
    Uses VADER (from stocksight) + TextBlob (from Stock-Predictor).
    """
    
    def __init__(self):
        self.vader = None
        self._init_vader()
        
        # Options-related keywords for filtering
        self.options_keywords = [
            "options", "call", "put", "strike", "expiry", "expiration",
            "gamma", "delta", "theta", "vega", "vanna", "charm",
            "gex", "vannex", "dex", "iv", "implied vol", "volatility",
            "sweep", "block trade", "unusual activity", "dark pool",
            "0dte", "otm", "itm", "atm", "premium", "open interest",
            "max pain", "pin risk", "assignment", "exercise",
            "spread", "iron condor", "straddle", "strangle",
            "butterfly", "calendar", "diagonal", "vertical",
            "dealer hedging", "gamma squeeze", "short squeeze",
        ]
        
        # Bullish/bearish keywords
        self.bullish_keywords = [
            "bullish", "long", "calls", "buy", "bounce", "breakout",
            "moon", "rocket", "pump", "rally", "support", "accumulate",
            "undervalued", "cheap", "dip buy", "oversold", "reversal up",
        ]
        
        self.bearish_keywords = [
            "bearish", "short", "puts", "sell", "crash", "breakdown",
            "dump", "drop", "resistance", "overbought", "bubble",
            "overvalued", "top", "reversal down", "capitulation",
        ]
    
    def _init_vader(self):
        """Initialize VADER sentiment analyzer."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer  # type: ignore
            self.vader = SentimentIntensityAnalyzer()
            logger.info("VADER sentiment analyzer initialized")
        except ImportError:
            logger.warning("vaderSentiment not installed. Install with: pip install vaderSentiment")
            self.vader = None
    
    def analyze_text(self, text: str) -> Dict[str, float]:
        """Analyze sentiment of a single text."""
        result = {
            "vader_compound": 0.0,
            "vader_pos": 0.0,
            "vader_neg": 0.0,
            "textblob_polarity": 0.0,
            "textblob_subjectivity": 0.0,
        }
        
        # VADER analysis
        if self.vader:
            scores = self.vader.polarity_scores(text)
            result["vader_compound"] = scores["compound"]
            result["vader_pos"] = scores["pos"]
            result["vader_neg"] = scores["neg"]
        
        # TextBlob analysis
        try:
            from textblob import TextBlob  # type: ignore
            blob = TextBlob(text)
            result["textblob_polarity"] = blob.sentiment.polarity
            result["textblob_subjectivity"] = blob.sentiment.subjectivity
        except ImportError:
            pass
        
        return result
    
    def is_options_related(self, text: str) -> bool:
        """Check if tweet is options-related."""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.options_keywords)
    
    def extract_ticker_mentions(self, text: str) -> List[str]:
        """Extract stock ticker mentions from text."""
        import re
        # Match $TICKER or #TICKER patterns
        tickers = re.findall(r'[$#]([A-Z]{1,5})\b', text)
        # Also match common tickers mentioned without $/$
        common_tickers = ["SPY", "QQQ", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT", "GOOG", "AMD", "SPX"]
        text_upper = text.upper()
        for t in common_tickers:
            if t in text_upper and t not in tickers:
                tickers.append(t)
        return list(set(tickers))
    
    def classify_sentiment(self, vader_compound: float, textblob_polarity: float) -> str:
        """Classify overall sentiment."""
        # Weighted average: VADER 60%, TextBlob 40%
        combined = vader_compound * 0.6 + textblob_polarity * 0.4
        if combined > 0.15:
            return "bullish"
        elif combined < -0.15:
            return "bearish"
        return "neutral"
    
    def analyze_tweets(self, tweets: List[Dict]) -> List[TweetSentiment]:
        """Analyze a list of tweets."""
        results = []
        for tweet in tweets:
            text = tweet.get("text", "")
            if not text:
                continue
            
            sentiment = self.analyze_text(text)
            tickers = self.extract_ticker_mentions(text)
            is_options = self.is_options_related(text)
            
            results.append(TweetSentiment(
                id=tweet.get("id", str(hash(text) % 100000)),
                text=text[:500],
                author=tweet.get("author", "unknown"),
                created_at=tweet.get("created_at", ""),
                likes=tweet.get("likes", 0),
                retweets=tweet.get("retweets", 0),
                **sentiment,
                ticker_mentions=tickers,
                is_options_related=is_options,
            ))
        
        return results
    
    def aggregate_ticker_sentiment(self, analyzed_tweets: List[TweetSentiment], ticker: str) -> TickerSentiment:
        """Aggregate sentiment for a specific ticker."""
        ticker_tweets = [t for t in analyzed_tweets if ticker in t.ticker_mentions]
        
        if not ticker_tweets:
            return TickerSentiment(ticker=ticker)
        
        avg_vader = float(np.mean([t.vader_compound for t in ticker_tweets]))
        avg_textblob = float(np.mean([t.textblob_polarity for t in ticker_tweets]))
        
        bullish = sum(1 for t in ticker_tweets if self.classify_sentiment(t.vader_compound, t.textblob_polarity) == "bullish")
        bearish = sum(1 for t in ticker_tweets if self.classify_sentiment(t.vader_compound, t.textblob_polarity) == "bearish")
        neutral = len(ticker_tweets) - bullish - bearish
        
        # Determine overall sentiment
        if bullish > bearish * 1.5:
            label = "bullish"
        elif bearish > bullish * 1.5:
            label = "bearish"
        else:
            label = "neutral"
        
        confidence = float(abs(avg_vader) * 0.6 + abs(avg_textblob) * 0.4)
        
        # Top tweets by engagement
        top = sorted(ticker_tweets, key=lambda t: t.likes + t.retweets, reverse=True)[:5]
        
        return TickerSentiment(
            ticker=ticker,
            tweet_count=len(ticker_tweets),
            avg_vader=round(avg_vader, 4),
            avg_textblob=round(avg_textblob, 4),
            bullish_count=bullish,
            bearish_count=bearish,
            neutral_count=neutral,
            total_likes=sum(t.likes for t in ticker_tweets),
            total_retweets=sum(t.retweets for t in ticker_tweets),
            sentiment_label=label,
            confidence=round(confidence, 4),
            top_tweets=[{"text": t.text, "author": t.author, "likes": t.likes, "sentiment": self.classify_sentiment(t.vader_compound, t.textblob_polarity)} for t in top],
            updated_at=datetime.utcnow().isoformat(),
        )


# ============================================================
# Options Flow Detector
# Based on: Buzzfund/UnusualOptions + FullStackCraft/floe
# ============================================================

class OptionsFlowDetector:
    """
    Detects unusual options activity and flow signals.
    Based on algorithms from Buzzfund/UnusualOptions and FullStackCraft/floe.
    """
    
    def __init__(self):
        self.min_premium = 50000  # Minimum premium to flag (USD)
        self.min_volume_oi_ratio = 2.0  # Volume/OI ratio threshold
        self.sweep_keywords = ["sweep", "swept", "split"]
        self.block_keywords = ["block", "blk"]
    
    def detect_unusual_volume(self, contracts: List[Dict]) -> List[Dict]:
        """Detect contracts with unusual volume relative to OI."""
        unusual = []
        for c in contracts:
            volume = c.get("volume", 0) or 0
            oi = c.get("oi", 0) or 0
            if oi > 0 and volume / oi > self.min_volume_oi_ratio:
                unusual.append({
                    **c,
                    "volume_oi_ratio": round(volume / oi, 2),
                    "signal_type": "unusual_volume",
                })
        return unusual
    
    def detect_large_premiums(self, contracts: List[Dict], spot: float) -> List[Dict]:
        """Detect large premium trades."""
        large = []
        for c in contracts:
            volume = c.get("volume", 0) or 0
            # Estimate premium: volume * mid_price * 100
            mid = c.get("mid", 0) or ((c.get("bid", 0) or 0) + (c.get("ask", 0) or 0)) / 2
            if mid <= 0:
                mid = c.get("last", 0) or 0
            premium = volume * mid * 100
            
            if premium >= self.min_premium:
                large.append({
                    **c,
                    "estimated_premium": round(premium, 0),
                    "signal_type": "large_premium",
                })
        return large
    
    def detect_sweeps(self, contracts: List[Dict]) -> List[Dict]:
        """Detect sweep orders (multiple strikes at once)."""
        # Group by timestamp (within 60 seconds)
        from collections import defaultdict
        
        time_groups = defaultdict(list)
        for c in contracts:
            ts = c.get("timestamp", c.get("last_trade_time", ""))
            if ts:
                # Round to nearest minute
                try:
                    minute_key = ts[:16] if len(ts) >= 16 else ts
                    time_groups[minute_key].append(c)
                except:
                    pass
        
        sweeps = []
        for ts, group in time_groups.items():
            if len(group) >= 3:  # 3+ strikes at same time = likely sweep
                total_premium = sum(
                    (c.get("volume", 0) or 0) * ((c.get("mid", 0) or 0) or (c.get("last", 0) or 0)) * 100
                    for c in group
                )
                if total_premium >= self.min_premium:
                    sweeps.append({
                        "timestamp": ts,
                        "contracts": len(group),
                        "total_premium": round(total_premium, 0),
                        "strikes": [c.get("strike", 0) for c in group],
                        "types": list(set(c.get("type", "") for c in group)),
                        "signal_type": "sweep",
                    })
        
        return sweeps
    
    def detect_dark_pool_indicators(self, contracts: List[Dict]) -> List[Dict]:
        """Detect potential dark pool prints (large size, mid-price fills)."""
        dark_pool = []
        for c in contracts:
            volume = c.get("volume", 0) or 0
            bid = c.get("bid", 0) or 0
            ask = c.get("ask", 0) or 0
            last = c.get("last", 0) or 0
            
            if bid > 0 and ask > 0 and last > 0:
                mid = (bid + ask) / 2
                spread = ask - bid
                
                # Dark pool indicator: large volume at mid-price
                if volume > 100 and abs(last - mid) < spread * 0.1:
                    dark_pool.append({
                        **c,
                        "mid_price": round(mid, 2),
                        "spread": round(spread, 2),
                        "signal_type": "dark_pool_indicator",
                    })
        
        return dark_pool
    
    def analyze_flow(self, ticker: str, contracts: List[Dict], spot: float) -> List[OptionsFlowSignal]:
        """Run all flow detection algorithms on options chain data."""
        signals = []
        
        # Unusual volume
        for c in self.detect_unusual_volume(contracts):
            signals.append(OptionsFlowSignal(
                ticker=ticker,
                strike=c.get("strike", 0),
                expiry=c.get("expiry", ""),
                option_type=c.get("type", ""),
                volume=c.get("volume", 0),
                open_interest=c.get("oi", 0),
                premium_usd=c.get("estimated_premium", 0),
                iv=c.get("iv", 0) or 0,
                spot_price=spot,
                volume_oi_ratio=c.get("volume_oi_ratio", 0),
                signal_type=c["signal_type"],
                timestamp=c.get("timestamp", datetime.utcnow().isoformat()),
                source="unusual_volume_detector",
            ))
        
        # Large premiums
        for c in self.detect_large_premiums(contracts, spot):
            signals.append(OptionsFlowSignal(
                ticker=ticker,
                strike=c.get("strike", 0),
                expiry=c.get("expiry", ""),
                option_type=c.get("type", ""),
                volume=c.get("volume", 0),
                open_interest=c.get("oi", 0),
                premium_usd=c.get("estimated_premium", 0),
                iv=c.get("iv", 0) or 0,
                spot_price=spot,
                signal_type=c["signal_type"],
                timestamp=c.get("timestamp", datetime.utcnow().isoformat()),
                source="large_premium_detector",
            ))
        
        return signals


# ============================================================
# GEX Calculator (Enhanced from scraped repos)
# Based on: Matteo-Ferrara/gex-tracker + Proshotv2/Gamma-Vanna
# ============================================================

class EnhancedGEXCalculator:
    """
    Enhanced GEX calculation combining algorithms from:
    - Matteo-Ferrara/gex-tracker: CBOE data scraping + GEX surface
    - Proshotv2/Gamma-Vanna-Options-Exposure: Vanna exposure + adjusted GEX
    """
    
    def __init__(self):
        self.call_gex_cache = {}
        self.put_gex_cache = {}
    
    def compute_gex_by_strike(self, spot: float, contracts: List[Dict]) -> List[Dict]:
        """
        Compute GEX by strike with vanna adjustment.
        Enhanced version combining gex-tracker and Gamma-Vanna algorithms.
        """
        from bs_greeks import bs_gamma, bs_vanna
        
        results = []
        for c in contracts:
            strike = c.get("strike", 0)
            oi = c.get("oi", 0) or 0
            iv = c.get("iv", 0) or 0
            T = c.get("T", 0) or c.get("dte", 0) / 365.0
            option_type = c.get("type", "call")
            
            if strike <= 0 or iv <= 0 or T <= 0:
                continue
            
            gamma = bs_gamma(spot, strike, T, iv / 100.0)
            vanna = bs_vanna(spot, strike, T, iv / 100.0)
            
            # Standard GEX: gamma * OI * spot * contract_multiplier
            if option_type == "call":
                gex = gamma * oi * spot * 0.01  # Call GEX is positive
            else:
                gex = -gamma * oi * spot * 0.01  # Put GEX is negative
            
            # Vanna exposure (from Proshotv2)
            vanna_exposure = vanna * oi * spot * 0.01
            
            results.append({
                "strike": strike,
                "expiry": c.get("expiry", ""),
                "type": option_type,
                "oi": oi,
                "iv": iv,
                "gamma": round(gamma, 6),
                "vanna": round(vanna, 6),
                "gex": round(gex, 0),
                "vanna_exposure": round(vanna_exposure, 0),
                "dte": c.get("dte", 0),
            })
        
        return sorted(results, key=lambda x: x["strike"])
    
    def compute_total_gex(self, gex_by_strike: List[Dict]) -> Dict[str, float]:
        """Compute total GEX metrics."""
        total_call_gex = sum(g["gex"] for g in gex_by_strike if g["type"] == "call")
        total_put_gex = sum(g["gex"] for g in gex_by_strike if g["type"] == "put")
        net_gex = total_call_gex + total_put_gex
        total_vanna = sum(g["vanna_exposure"] for g in gex_by_strike)
        
        return {
            "total_call_gex": round(total_call_gex, 0),
            "total_put_gex": round(total_put_gex, 0),
            "net_gex": round(net_gex, 0),
            "total_vanna_exposure": round(total_vanna, 0),
            "gex_ratio": round(total_call_gex / abs(total_put_gex), 2) if total_put_gex != 0 else float("inf"),
        }
    
    def find_gamma_flip(self, gex_by_strike: List[Dict], spot: float) -> Optional[float]:
        """
        Find gamma flip level where cumulative GEX changes sign.
        Enhanced from gex-tracker algorithm.
        """
        if not gex_by_strike:
            return None
        
        # Sort by strike
        sorted_strikes = sorted(gex_by_strike, key=lambda x: x["strike"])
        
        # Compute cumulative GEX
        cumulative = 0
        flip_point = None
        for s in sorted_strikes:
            cumulative += s["gex"]
            if cumulative > 0 and flip_point is None:
                flip_point = s["strike"]
        
        return flip_point
    
    def compute_gex_surface(self, spot: float, contracts_by_expiry: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """
        Compute GEX surface across expirations.
        From Matteo-Ferrara/gex-tracker's print_gex_surface.
        """
        surface = {}
        for expiry, contracts in contracts_by_expiry.items():
            gex_data = self.compute_gex_by_strike(spot, contracts)
            totals = self.compute_total_gex(gex_data)
            surface[expiry] = {
                "gex_by_strike": gex_data,
                "totals": totals,
            }
        
        return surface


# ============================================================
# Social + Flow Report Generator
# ============================================================

class SocialFlowPipeline:
    """
    Main pipeline that combines social sentiment + options flow + GEX.
    """
    
    def __init__(self):
        self.sentiment_analyzer = TwitterSentimentAnalyzer()
        self.flow_detector = OptionsFlowDetector()
        self.gex_calculator = EnhancedGEXCalculator()
    
    async def generate_report(self, ticker: str, spot: float, contracts: List[Dict],
                               tweets: Optional[List[Dict]] = None) -> SocialFlowReport:
        """Generate a complete social + flow report for a ticker."""
        report = SocialFlowReport(
            ticker=ticker,
            generated_at=datetime.utcnow().isoformat(),
        )
        
        # 1. Sentiment analysis
        if tweets:
            analyzed = self.sentiment_analyzer.analyze_tweets(tweets)
            report.sentiment = self.sentiment_analyzer.aggregate_ticker_sentiment(analyzed, ticker)
            report.social_score = report.sentiment.avg_vader * 0.6 + report.sentiment.avg_textblob * 0.4
        
        # 2. Options flow detection
        report.flow_signals = self.flow_detector.analyze_flow(ticker, contracts, spot)
        
        # Flow score: bullish if more call signals, bearish if more put signals
        call_signals = sum(1 for s in report.flow_signals if s.option_type == "call")
        put_signals = sum(1 for s in report.flow_signals if s.option_type == "put")
        total_signals = call_signals + put_signals
        if total_signals > 0:
            report.flow_score = (call_signals - put_signals) / total_signals
        
        # 3. GEX summary
        gex_data = self.gex_calculator.compute_gex_by_strike(spot, contracts)
        report.gex_summary = self.gex_calculator.compute_total_gex(gex_data)
        report.gex_summary["gamma_flip"] = self.gex_calculator.find_gamma_flip(gex_data, spot)
        
        # 4. Combined score
        report.combined_score = report.social_score * 0.3 + report.flow_score * 0.4
        # GEX regime factor: negative GEX amplifies flow signals
        if report.gex_summary.get("net_gex", 0) < 0:
            report.combined_score *= 1.2
        
        # 5. Generate signals
        report.signals = self._generate_signals(report)
        
        return report
    
    def _generate_signals(self, report: SocialFlowReport) -> List[str]:
        """Generate human-readable signals."""
        signals = []
        
        # Sentiment signals
        if report.sentiment:
            if report.sentiment.sentiment_label == "bullish" and report.sentiment.confidence > 0.3:
                signals.append(f"🟢 Social sentiment bullish ({report.sentiment.tweet_count} tweets, {report.sentiment.bullish_count}B/{report.sentiment.bearish_count}Be)")
            elif report.sentiment.sentiment_label == "bearish" and report.sentiment.confidence > 0.3:
                signals.append(f"🔴 Social sentiment bearish ({report.sentiment.tweet_count} tweets, {report.sentiment.bullish_count}B/{report.sentiment.bearish_count}Be)")
        
        # Flow signals
        sweeps = [s for s in report.flow_signals if s.signal_type == "sweep"]
        large = [s for s in report.flow_signals if s.signal_type == "large_premium"]
        unusual = [s for s in report.flow_signals if s.signal_type == "unusual_volume"]
        
        if sweeps:
            total_premium = sum(s.premium_usd for s in sweeps)
            signals.append(f"⚡ {len(sweeps)} sweep orders detected (${total_premium:,.0f} total premium)")
        if large:
            total_premium = sum(s.premium_usd for s in large)
            signals.append(f"💰 {len(large)} large premium trades (${total_premium:,.0f} total)")
        if unusual:
            signals.append(f"📊 {len(unusual)} contracts with unusual volume/OI ratio")
        
        # GEX signals
        if report.gex_summary.get("net_gex", 0) < 0:
            signals.append("⚠️ Negative GEX regime — dealers amplify moves")
        else:
            signals.append("✅ Positive GEX regime — dealers dampen volatility")
        
        gamma_flip = report.gex_summary.get("gamma_flip")
        if gamma_flip:
            signals.append(f"🔄 Gamma flip at {gamma_flip}")
        
        return signals


# ============================================================
# X/Twitter Data Collector (uses xurl when authenticated)
# ============================================================

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
