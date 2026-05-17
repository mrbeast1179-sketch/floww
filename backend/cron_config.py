"""
Cron job configuration for Confluence Decoder.

Sets up scheduled tasks:
1. Data collection every 5 minutes during market hours (9:30 AM - 4:00 PM ET)
2. Morning briefing email at 8:00 AM ET
3. ML model retraining daily at 6:00 PM ET
4. Health check every hour
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def collect_data_job():
    """Collect GEX data for all tickers."""
    from data_collector import collect_multiple_tickers
    from dotenv import load_dotenv
    load_dotenv()
    
    tickers = os.environ.get("COLLECT_TICKERS", "SPY,QQQ,IWM,DIA").split(",")
    results = await collect_multiple_tickers(tickers)
    
    success = sum(1 for r in results if r.get("status") == "stored")
    print(f"Data collection: {success}/{len(tickers)} tickers stored")


async def morning_briefing_job():
    """Send morning briefing email."""
    from morning_briefing import send_briefing_email
    from dotenv import load_dotenv
    load_dotenv()
    
    to_email = os.environ.get("BRIEFING_EMAIL", "")
    if not to_email:
        print("No briefing email configured")
        return
    
    result = await send_briefing_email(to_email, "SPY")
    print(f"Morning briefing: {result.get('status', 'unknown')}")


async def retrain_models_job():
    """Retrain ML models on latest data."""
    from ml_price_prediction import train_price_direction_model
    from dotenv import load_dotenv
    load_dotenv()
    
    tickers = os.environ.get("ML_TICKERS", "SPY,QQQ").split(",")
    for ticker in tickers:
        result = await train_price_direction_model(ticker)
        print(f"Model training {ticker}: {result.get('status', 'unknown')}")


async def health_check_job():
    """Run health check and log results."""
    import httpx
    from dotenv import load_dotenv
    load_dotenv()
    
    backend_url = os.environ.get("BACKEND_URL", "http://localhost:8000")
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{backend_url}/health", timeout=10)
            data = r.json()
            print(f"Health check: {data.get('status', 'unknown')}")
    except Exception as e:
        print(f"Health check failed: {e}")


# Cron schedule configuration
CRON_JOBS = [
    {
        "name": "data-collection",
        "schedule": "*/5 9-16 * * 1-5",  # Every 5 min, 9AM-4PM, Mon-Fri
        "job": collect_data_job,
    },
    {
        "name": "morning-briefing",
        "schedule": "0 8 * * 1-5",  # 8:00 AM, Mon-Fri
        "job": morning_briefing_job,
    },
    {
        "name": "retrain-models",
        "schedule": "0 18 * * 1-5",  # 6:00 PM, Mon-Fri
        "job": retrain_models_job,
    },
    {
        "name": "health-check",
        "schedule": "0 * * * *",  # Every hour
        "job": health_check_job,
    },
]


def setup_cron_jobs():
    """Set up cron jobs using the system crontab."""
    import subprocess
    
    for job_config in CRON_JOBS:
        name = job_config["name"]
        schedule = job_config["schedule"]
        
        # Build the command
        python_path = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
        script_path = os.path.join(os.path.dirname(__file__), "cron_runner.py")
        
        command = f"{python_path} {script_path} {name}"
        
        # Add to crontab
        cron_line = f"{schedule} {command} >> /tmp/confluence-cron.log 2>&1"
        
        print(f"Cron job: {name}")
        print(f"  Schedule: {schedule}")
        print(f"  Command: {command}")
        print(f"  Cron line: {cron_line}")
        print()


if __name__ == "__main__":
    setup_cron_jobs()