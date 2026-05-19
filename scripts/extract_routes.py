#!/usr/bin/env python3
"""
scripts/extract_routes.py

Extract route handlers from server.py into separate route modules.
Groups routes by domain based on URL patterns.
"""
import re
from pathlib import Path

SERVER_PY = Path('backend/server.py')
ROUTES_DIR = Path('backend/routes')

# Domain mapping based on URL patterns
DOMAIN_MAP = {
    'market_data': ['/tickers', '/heatmap/', '/trinity', '/gex-timeframes/', '/chain/', '/uoa/', '/spot/'],
    'analytics': ['/implied-pdf/', '/regime/', '/hedge-impulse/', '/pressure-cloud/', '/charm-integral/',
                  '/advanced/', '/gamma-flip/', '/daily-checklist', '/movers', '/history/', '/patterns/glossary',
                  '/contract/', '/flow/', '/api/analytics/'],
    'portfolio': ['/portfolio/', '/position-size'],
    'paper_trading': ['/api/paper-trading/'],
    'briefing': ['/api/briefing/'],
    'ml_training': ['/api/ml/'],
    'llm': ['/api/llm/'],
    'schwab': ['/schwab/'],
    'live_trading': ['/live/'],
    'memory': ['/memory/'],
    'admin': ['/api/errors/', '/api/performance/', '/databento/usage'],
}

def get_domain(url_path):
    """Determine which domain a route belongs to."""
    for domain, patterns in DOMAIN_MAP.items():
        for pattern in patterns:
            if pattern in url_path:
                return domain
    return 'root'  # Keep in server.py

def extract_routes():
    """Extract routes from server.py into separate modules."""
    content = SERVER_PY.read_text()
    
    # Find all route decorators and their handlers
    # Pattern: @api.get("/path") or @app.get("/path") followed by async def or def
    route_pattern = re.compile(
        r'(@(?:api|app)\.(?:get|post|put|delete|patch)\((?:"([^"]+)"|\'([^\']+)\')\)\n'
        r'(?:@[^\n]+\n)*'  # Additional decorators like @cache_response
        r'(?:async\s+)?def\s+(\w+)\s*\([^)]*\)[^:]*:\n'
        r'(?:\s+[^\n]+\n)*)',  # First few lines of function body
        re.MULTILINE
    )
    
    # Simpler approach: find all @api.get/post lines
    decorator_pattern = re.compile(r'@(?:api|app)\.(get|post|put|delete|patch)\((?:"([^"]+)"|\'([^\']+)\')')
    
    routes_by_domain = {}
    for match in decorator_pattern.finditer(content):
        method = match.group(1)
        path = match.group(2) or match.group(3)
        domain = get_domain(path)
        
        if domain not in routes_by_domain:
            routes_by_domain[domain] = []
        routes_by_domain[domain].append({
            'method': method,
            'path': path,
            'line': content[:match.start()].count('\n') + 1
        })
    
    # Print summary
    print("Route extraction plan:")
    print("=" * 60)
    total = 0
    for domain, routes in sorted(routes_by_domain.items()):
        print(f"\n{domain}.py ({len(routes)} routes):")
        for r in routes:
            print(f"  {r['method'].upper():6s} {r['path']}")
        total += len(routes)
    print(f"\nTotal routes: {total}")
    
    return routes_by_domain

if __name__ == '__main__':
    extract_routes()
