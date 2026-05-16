"""
Black-Scholes Greeks calculations.
Shared between server.py and portfolio.py to avoid circular imports.
"""

import math
from scipy.stats import norm

RISK_FREE_RATE = 0.05


def bs_gamma(S, K, T, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_delta(S, K, T, sigma, q=0.0, kind="call"):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        if kind == "call": return math.exp(-q * T) * norm.cdf(d1)
        else: return math.exp(-q * T) * (norm.cdf(d1) - 1)
    except Exception: return 0.0


def bs_vanna(S, K, T, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        result = -math.exp(-q * T) * norm.pdf(d1) * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_charm(S, K, T, sigma, q=0.0, kind="call"):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        pdf_d1 = norm.pdf(d1)
        cdf_d1 = norm.cdf(d1)
        charm = -math.exp(-q * T) * (q * cdf_d1 - pdf_d1 * (2 * q * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if kind == "put":
            charm = -math.exp(-q * T) * (-q * (1 - cdf_d1) - pdf_d1 * (2 * q * T - d2 * sigma * math.sqrt(T)) / (2 * T * sigma * math.sqrt(T)))
        if math.isnan(charm) or math.isinf(charm): return 0.0
        return charm
    except Exception: return 0.0


def bs_vomma(S, K, T, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        vega = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        result = vega * d1 * d2 / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_zomma(S, K, T, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)
        gamma = math.exp(-q * T) * norm.pdf(d1) / (S * sigma * math.sqrt(T))
        result = gamma * (d1 * d2 - 1) / sigma
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0


def bs_vega(S, K, T, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    try:
        d1 = (math.log(S / K) + (q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
        result = S * math.exp(-q * T) * norm.pdf(d1) * math.sqrt(T)
        if math.isnan(result) or math.isinf(result): return 0.0
        return result
    except Exception: return 0.0
