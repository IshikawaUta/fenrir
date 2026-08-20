"""
fenrir.pagination — Pagination utilities for list endpoints.

Provides query-parameter based pagination helpers that integrate with
Fenrir's dependency injection and produce standardised response envelopes.

Usage::

    from fenrir import Fenrir, Depends
    from fenrir.pagination import PaginationParams, paginate

    app = Fenrir()

    def get_items():
        return [{"id": i} for i in range(100)]

    @app.get("/items")
    async def list_items(pagination: PaginationParams = Depends()):
        items = get_items()
        return paginate(items, pagination)

    # Or using the query-param shortcut:
    @app.get("/items2")
    async def list_items2(page: int = 1, size: int = 20):
        return paginate(get_items(), page=page, size=size)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    """Query parameters for pagination, injectable via ``Depends()``."""
    page: int = Field(default=1, ge=1, description="Page number (1-based)")
    size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


class PaginationLinks(BaseModel):
    self_url: str = ""
    first_url: str = ""
    last_url: str = ""
    next_url: Optional[str] = None
    prev_url: Optional[str] = None


class PaginatedResponse(BaseModel):
    """Standardised paginated response envelope."""
    items: List[Any]
    total: int
    page: int
    size: int
    pages: int
    has_next: bool
    has_prev: bool
    links: Optional[PaginationLinks] = None


def paginate(
    items: Sequence[Any],
    page: int = 1,
    size: int = 20,
    base_url: str = "",
) -> Dict[str, Any]:
    """Paginate a sequence of items and return a paginated response dict.

    Can be used with either a ``PaginationParams`` object or plain ints::

        # With PaginationParams
        return paginate(items, page=pagination.page, size=pagination.size)

        # With plain ints
        return paginate(items, page=1, size=20)
    """
    total = len(items)
    if size <= 0:
        size = 1
    pages = max(1, math.ceil(total / size))
    page = max(1, min(page, pages))
    start = (page - 1) * size
    end = start + size
    page_items = list(items[start:end])

    has_next = page < pages
    has_prev = page > 1

    def _build_url(page_num: int) -> str:
        if not base_url:
            return ""  # pragma: no cover
        from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)
        # Flatten single-value lists and update page/size
        params["page"] = [str(page_num)]
        params["size"] = [str(size)]
        new_query = urlencode(params, doseq=True)
        return urlunparse(parsed._replace(query=new_query))

    links = PaginationLinks(
        self_url=_build_url(page),
        first_url=_build_url(1),
        last_url=_build_url(pages),
        next_url=_build_url(page + 1) if has_next else None,
        prev_url=_build_url(page - 1) if has_prev else None,
    ) if base_url else None

    result: Dict[str, Any] = {
        "items": page_items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages,
        "has_next": has_next,
        "has_prev": has_prev,
    }
    if links:
        result["links"] = links.model_dump()
    return result


def paginate_dict(
    items: Sequence[Dict[str, Any]],
    page: int = 1,
    size: int = 20,
    base_url: str = "",
) -> Dict[str, Any]:
    """Same as ``paginate`` but typed specifically for dict items."""
    return paginate(items, page=page, size=size, base_url=base_url)
