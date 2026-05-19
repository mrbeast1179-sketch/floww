"""
backend/routes/ml_training.py

ML training and prediction routes.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

router = APIRouter()


@router.post("/api/ml/train/{ticker}")
async def ml_train(ticker: str, request: dict = None):
    from server import train_model_endpoint
    result = await train_model_endpoint(ticker.upper(), request or {})
    return result


@router.get("/api/ml/predict/{ticker}")
async def ml_predict(ticker: str):
    from server import predict_endpoint
    result = await predict_endpoint(ticker.upper())
    return result


@router.get("/api/ml/features/{ticker}")
async def ml_features(ticker: str):
    from server import get_features_endpoint
    result = await get_features_endpoint(ticker.upper())
    return result


@router.get("/api/ml/data/{ticker}")
async def ml_data(ticker: str, days: int = 30):
    from server import get_training_data_endpoint
    result = await get_training_data_endpoint(ticker.upper(), days)
    return result


@router.post("/api/ml/collect/{ticker}")
async def ml_collect(ticker: str):
    from server import collect_data_endpoint
    result = await collect_data_endpoint(ticker.upper())
    return result


@router.post("/api/ml/collect-all")
async def ml_collect_all():
    from server import collect_all_data_endpoint
    result = await collect_all_data_endpoint()
    return result


@router.post("/api/ml/train-price/{ticker}")
async def ml_train_price(ticker: str, request: dict = None):
    from server import train_price_model_endpoint
    result = await train_price_model_endpoint(ticker.upper(), request or {})
    return result


@router.get("/api/ml/predict-price/{ticker}")
async def ml_predict_price(ticker: str):
    from server import predict_price_endpoint
    result = await predict_price_endpoint(ticker.upper())
    return result


@router.post("/api/ml/train-advanced/{ticker}")
async def ml_train_advanced(ticker: str, request: dict = None):
    from server import train_advanced_model_endpoint
    result = await train_advanced_model_endpoint(ticker.upper(), request or {})
    return result


@router.get("/api/ml/model-info/{ticker}")
async def ml_model_info(ticker: str):
    from server import get_model_info_endpoint
    result = await get_model_info_endpoint(ticker.upper())
    return result
