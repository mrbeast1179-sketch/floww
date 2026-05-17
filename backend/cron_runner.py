#!/usr/bin/env python3
"""
Cron runner for Confluence Decoder scheduled jobs.

Usage: python cron_runner.py <job_name>
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def main():
    if len(sys.argv) < 2:
        print("Usage: python cron_runner.py <job_name>")
        print("Available jobs: data-collection, morning-briefing, retrain-models, health-check")
        sys.exit(1)
    
    job_name = sys.argv[1]
    
    if job_name == "data-collection":
        from cron_config import collect_data_job
        await collect_data_job()
    elif job_name == "morning-briefing":
        from cron_config import morning_briefing_job
        await morning_briefing_job()
    elif job_name == "retrain-models":
        from cron_config import retrain_models_job
        await retrain_models_job()
    elif job_name == "health-check":
        from cron_config import health_check_job
        await health_check_job()
    else:
        print(f"Unknown job: {job_name}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())