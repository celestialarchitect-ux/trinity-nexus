"""mDNS-based peer discovery for Trinity Nexus mesh.

Lightweight compared to full libp2p: announces this node on the local
network as `_trinity-nexus._tcp.local.` and listens for other nodes.
Works across Mac / Windows / Linux without a central server.

Usage:
  nexus mesh discover              scan for 5s, print peers found
  nexus mesh listen [--port 8899]  stay resident, announce self
"""

from __future__ import annotations

import json
import socket
import time
from dataclasses import dataclass


SERVICE_TYPE = "_trinity-nexus._tcp.local."


@dataclass
class DiscoveredPeer:
    name: str
    host: str
    port: int
    pubkey: str = ""
    label: str = ""


def _have_zeroconf() -> bool:
    try:
        import zeroconf  # noqa: F401
        return True
    except ImportError:
        return False


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "nexus"


def discover(timeout: float = 5.0) -> list[DiscoveredPeer]:
    """Scan the LAN for Trinity Nexus peers. Returns a list of what's found."""
    if not _have_zeroconf():
        return []

    from zeroconf import ServiceBrowser, Zeroconf

    found: dict[str, DiscoveredPeer] = {}

    class _Listener:
        def update_service(self, zc, t, name):
            self.add_service(zc, t, name)

        def remove_service(self, zc, t, name):
            found.pop(name, None)

        def add_service(self, zc, t, name):
            info = zc.get_service_info(t, name, timeout=2000)
            if not info:
                return
            host = socket.inet_ntoa(info.addresses[0]) if info.addresses else ""
            props: dict = {}
            for k, v in (info.properties or {}).items():
                try:
                    key = k.decode() if isinstance(k, bytes) else k
                    val = v.decode() if isinstance(v, bytes) else v
                    props[key] = val
                except Exception:
                    continue
            found[name] = DiscoveredPeer(
                name=name,
                host=host,
                port=info.port or 0,
                pubkey=props.get("pubkey", ""),
                label=props.get("label", ""),
            )

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, SERVICE_TYPE, _Listener())
        time.sleep(timeout)
    finally:
        zc.close()
    return list(found.values())


def announce(port: int = 8899) -> object | None:
    """Announce this node on the LAN. Returns the Zeroconf handle (caller closes)."""
    if not _have_zeroconf():
        return None

    from zeroconf import IPVersion, ServiceInfo, Zeroconf

    from nexus.mesh.identity import load_identity

    ident = load_identity()
    pubkey = ident.pubkey_b64 if ident else ""
    label = (ident.label if ident else _hostname())[:60]

    name = f"{label}-{(pubkey or _hostname())[:8]}.{SERVICE_TYPE}"
    ip = socket.gethostbyname(socket.gethostname())

    info = ServiceInfo(
        SERVICE_TYPE,
        name,
        addresses=[socket.inet_aton(ip)],
        port=port,
        properties={
            "pubkey": pubkey,
            "label": label,
        },
        server=f"{socket.gethostname()}.local.",
    )
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    zc.register_service(info)
    return zc
