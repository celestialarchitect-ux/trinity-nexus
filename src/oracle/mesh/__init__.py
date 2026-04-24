"""Oracle mesh — Ed25519-signed skill deltas between trusted peers.

Transport is plain HTTP/S (for v1 — libp2p gossip comes later). The important
parts are:
  - each node has an Ed25519 keypair; pubkey is its identity
  - skill files are signed + hash-chained so tampering is detected
  - a simple allowlist of peer pubkeys controls trust

Use:
    oracle mesh keygen            # create ~/.oracle/mesh/key.json
    oracle mesh export            # pack all skills + sign
    oracle mesh push PEER_URL     # send signed bundle
    oracle mesh pull PEER_URL     # fetch + verify + install
"""

from oracle.mesh.identity import (
    PeerIdentity,
    load_identity,
    new_identity,
    verify,
    sign,
)
from oracle.mesh.sync import (
    SkillBundle,
    build_bundle,
    install_bundle,
    push_bundle,
    pull_bundle,
)

__all__ = [
    "PeerIdentity",
    "SkillBundle",
    "build_bundle",
    "install_bundle",
    "load_identity",
    "new_identity",
    "pull_bundle",
    "push_bundle",
    "sign",
    "verify",
]
