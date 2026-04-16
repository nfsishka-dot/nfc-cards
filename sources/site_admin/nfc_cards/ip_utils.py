"""Определение IP клиента для rate limit и аудита (с учётом доверенного reverse proxy)."""
from __future__ import annotations

import ipaddress
from typing import Iterable, Union

from django.conf import settings
from django.http import HttpRequest

_Net = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _remote_addr(request: HttpRequest) -> str:
    return (request.META.get("REMOTE_ADDR") or "").strip()


def _xff_first_hop(request: HttpRequest) -> str:
    xff = (request.META.get("HTTP_X_FORWARDED_FOR") or "").strip()
    if not xff:
        return ""
    return xff.split(",")[0].strip()


def _addr_in_networks(addr: str, networks: Iterable[_Net]) -> bool:
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return any(ip in net for net in networks)


def client_ip_for_request(request: HttpRequest) -> str:
    """
    Если REMOTE_ADDR входит в доверенные сети (DJANGO_TRUSTED_PROXY_CIDRS),
    берём первый hop из X-Forwarded-For. Иначе — только REMOTE_ADDR (защита от подделки XFF).
    """
    remote = _remote_addr(request)
    networks = getattr(settings, "TRUSTED_PROXY_NETWORKS", ())
    xff_first = _xff_first_hop(request)
    if xff_first and networks and remote and _addr_in_networks(remote, networks):
        return (xff_first or remote or "unknown")[:45]
    return (remote or "unknown")[:45]
