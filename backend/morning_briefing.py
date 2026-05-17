"""
Morning Briefing Email System for Confluence Decoder.

Sends a daily email with:
- Current GEX regime
- Key levels (gamma flip, call/put walls)
- Recommended strategies
- Alert summary
- Market sentiment

Uses SendGrid (free tier: 100 emails/day) or SMTP.
"""

import os
import logging
from typing import Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def generate_briefing_data(ticker: str = "SPY") -> Dict[str, Any]:
    """Generate the morning briefing data."""
    from alert_engine import AlertEngine
    
    engine = AlertEngine()
    summary = engine.get_alert_summary(ticker)
    
    return {
        "ticker": ticker,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "regime": summary.get("regime", "unknown"),
        "spot": summary.get("spot", 0),
        "gamma_flip": summary.get("gamma_flip", 0),
        "call_wall": summary.get("call_wall", 0),
        "put_wall": summary.get("put_wall", 0),
        "net_gex": summary.get("net_gex", 0),
        "alert_count": summary.get("alert_count", 0),
        "high_priority": summary.get("high_priority", 0),
        "alerts": summary.get("alerts", []),
    }


def format_briefing_email(data: Dict[str, Any]) -> str:
    """Format the briefing data into an HTML email."""
    regime = data.get("regime", "unknown")
    is_positive = regime == "POSITIVE"
    regime_color = "#10b981" if is_positive else "#ef4444"
    regime_icon = "🟢" if is_positive else "🔴"
    
    alerts_html = ""
    for alert in data.get("alerts", [])[:5]:
        priority = alert.get("priority", "MEDIUM")
        icon = "🔴" if priority == "HIGH" else "🟡" if priority == "MEDIUM" else "🔵"
        alerts_html += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #1f2a3a;">{icon} {alert.get('type', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #1f2a3a;">{alert.get('message', '')[:80]}</td>
        </tr>
        """
    
    if not alerts_html:
        alerts_html = '<tr><td colspan="2" style="padding: 8px; text-align: center; color: #7f8da3;">No active alerts</td></tr>'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Morning Briefing - {data.get('ticker', 'SPY')}</title>
    </head>
    <body style="margin: 0; padding: 0; background: #07090d; color: #d5dde8; font-family: 'JetBrains Mono', monospace;">
        <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
            <!-- Header -->
            <div style="text-align: center; padding: 20px 0; border-bottom: 2px solid {regime_color};">
                <h1 style="margin: 0; font-size: 24px;">📊 Morning Briefing</h1>
                <p style="margin: 5px 0 0; color: #7f8da3; font-size: 12px;">{data.get('date', '')} · {data.get('ticker', 'SPY')}</p>
            </div>
            
            <!-- Regime -->
            <div style="padding: 20px 0; text-align: center;">
                <div style="display: inline-block; padding: 10px 20px; background: {regime_color}20; border: 1px solid {regime_color}40; border-radius: 8px;">
                    <span style="font-size: 18px;">{regime_icon} {regime} GAMMA</span>
                </div>
            </div>
            
            <!-- Key Levels -->
            <div style="padding: 10px 0;">
                <h3 style="margin: 0 0 10px; font-size: 14px; color: #7f8da3;">Key Levels</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr>
                        <td style="padding: 8px; color: #7f8da3;">Spot</td>
                        <td style="padding: 8px; text-align: right; font-weight: bold;">${data.get('spot', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #7f8da3;">Gamma Flip</td>
                        <td style="padding: 8px; text-align: right; color: #fbbf24; font-weight: bold;">${data.get('gamma_flip', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #7f8da3;">Call Wall</td>
                        <td style="padding: 8px; text-align: right; color: #38bdf8; font-weight: bold;">${data.get('call_wall', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #7f8da3;">Put Wall</td>
                        <td style="padding: 8px; text-align: right; color: #fb923c; font-weight: bold;">${data.get('put_wall', 0):.2f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 8px; color: #7f8da3;">Net GEX</td>
                        <td style="padding: 8px; text-align: right; color: {'#10b981' if data.get('net_gex', 0) >= 0 else '#ef4444'}; font-weight: bold;">{'+"' if data.get('net_gex', 0) >= 0 else ''}{data.get('net_gex', 0):,.0f}</td>
                    </tr>
                </table>
            </div>
            
            <!-- Alerts -->
            <div style="padding: 10px 0;">
                <h3 style="margin: 0 0 10px; font-size: 14px; color: #7f8da3;">Active Alerts ({data.get('alert_count', 0)})</h3>
                <table style="width: 100%; border-collapse: collapse; font-size: 11px;">
                    {alerts_html}
                </table>
            </div>
            
            <!-- Footer -->
            <div style="padding: 20px 0; text-align: center; border-top: 1px solid #1f2a3a; margin-top: 20px;">
                <p style="margin: 0; font-size: 10px; color: #4a5468;">
                    Confluence Decoder · Automated Morning Briefing<br>
                    This is not financial advice. Do your own research.
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html


async def send_briefing_email(
    to_email: str,
    ticker: str = "SPY",
) -> Dict[str, Any]:
    """Send the morning briefing email."""
    data = generate_briefing_data(ticker)
    html_content = format_briefing_email(data)
    
    # Try SendGrid first, then SMTP
    sendgrid_key = os.environ.get("SENDGRID_API_KEY")
    if sendgrid_key:
        return await _send_via_sendgrid(to_email, ticker, html_content, sendgrid_key)
    
    smtp_host = os.environ.get("SMTP_HOST")
    if smtp_host:
        return await _send_via_smtp(to_email, ticker, html_content)
    
    logger.warning("No email service configured (SENDGRID_API_KEY or SMTP_HOST)")
    return {"status": "skipped", "message": "No email service configured"}


async def _send_via_sendgrid(
    to_email: str,
    ticker: str,
    html_content: str,
    api_key: str,
) -> Dict[str, Any]:
    """Send email via SendGrid API."""
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "personalizations": [{"to": [{"email": to_email}]}],
                    "from": {"email": "briefing@confluence-decoder.app", "name": "Confluence Decoder"},
                    "subject": f"📊 Morning Briefing: {ticker} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    "content": [{"type": "text/html", "value": html_content}],
                },
                timeout=30,
            )
            
            if response.status_code == 202:
                logger.info(f"Briefing email sent to {to_email}")
                return {"status": "sent", "service": "sendgrid"}
            else:
                logger.error(f"SendGrid error: {response.status_code} {response.text}")
                return {"status": "error", "message": f"SendGrid {response.status_code}"}
    
    except Exception as e:
        logger.error(f"SendGrid send failed: {e}")
        return {"status": "error", "message": str(e)}


async def _send_via_smtp(
    to_email: str,
    ticker: str,
    html_content: str,
) -> Dict[str, Any]:
    """Send email via SMTP."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    
    try:
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        smtp_user = os.environ.get("SMTP_USER", "")
        smtp_pass = os.environ.get("SMTP_PASS", "")
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"📊 Morning Briefing: {ticker} - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg.attach(MIMEText(html_content, "html"))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        
        logger.info(f"Briefing email sent to {to_email} via SMTP")
        return {"status": "sent", "service": "smtp"}
    
    except Exception as e:
        logger.error(f"SMTP send failed: {e}")
        return {"status": "error", "message": str(e)}