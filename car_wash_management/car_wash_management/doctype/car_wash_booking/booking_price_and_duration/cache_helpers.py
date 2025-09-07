from typing import Tuple, Any
from functools import lru_cache
import time

from .repository import (
    get_valid_service_ids,
    get_service_docs,
    get_service_prices_by_tariff,
)
from .tariffs import ensure_tariff_valid_for_car_wash


def ttl_lru_cache(seconds: int, maxsize: int = 128):
    """LRU cache with time-bucketed TTL. Recomputes once per TTL window per key."""
    def decorator(func):
        @lru_cache(maxsize=maxsize)
        def cached(time_bucket: int, *args, **kwargs):
            return func(*args, **kwargs)

        def wrapper(*args, **kwargs):
            bucket = int(time.time() // seconds)
            return cached(bucket, *args, **kwargs)

        wrapper.cache_clear = cached.cache_clear
        return wrapper
    return decorator


def _make_service_ids_tuple(service_counter) -> Tuple[str, ...]:
    """Stable, hashable key for caching by service ids."""
    return tuple(sorted(service_counter.keys()))


@ttl_lru_cache(30, maxsize=2048)
def _cached_get_valid_service_ids(service_ids: Tuple[str, ...]):
    # Return as tuple to keep cache-friendly; callers can list() it
    return tuple(get_valid_service_ids(list(service_ids)))


@ttl_lru_cache(30, maxsize=4096)
def _cached_get_service_docs(service_ids: Tuple[str, ...]):
    return get_service_docs(list(service_ids))


@ttl_lru_cache(30, maxsize=8192)
def _cached_get_service_prices_by_tariff(service_ids: Tuple[str, ...], tariff_id: str):
    return get_service_prices_by_tariff(list(service_ids), tariff_id)


def _normalize_tariff_key(tariff: Any) -> str:
    """Normalize various tariff representations to a stable, hashable key."""
    try:
        name = getattr(tariff, "name", None)
        return str(name if name is not None else tariff)
    except Exception:
        return str(tariff)


@ttl_lru_cache(30, maxsize=2048)
def _cached_ensure_tariff_valid_for_car_wash_key(tariff_key: str, car_wash: str):
    return ensure_tariff_valid_for_car_wash(tariff_key, car_wash)


def _ensure_tariff_valid_cached(tariff: Any, car_wash: str):
    return _cached_ensure_tariff_valid_for_car_wash_key(_normalize_tariff_key(tariff), car_wash)


