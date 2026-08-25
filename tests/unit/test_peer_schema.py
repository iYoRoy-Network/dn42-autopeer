import pytest
from pydantic import ValidationError

from autopeer.domain.peer import PeerCreateRequest, canonical_endpoint, listen_port_for_asn


def test_listen_port_matches_dn42_asn_tail():
    assert listen_port_for_asn(4242423128) == 23128


def test_endpoint_canonicalizes_ipv6_brackets():
    assert canonical_endpoint("[2001:db8::1]:22024") == "[2001:db8::1]:22024"


def test_endpoint_rejects_unbracketed_ipv6():
    with pytest.raises(ValueError):
        canonical_endpoint("2001:db8::1:22024")


def test_peer_request_rejects_single_family_until_template_supports_it():
    with pytest.raises(ValidationError):
        PeerCreateRequest.model_validate(
            {
                "wireguard": {
                    "public_key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
                    "endpoint": "example.com:22024",
                },
                "bgp": {
                    "transport": {"mode": "ipv6_link_local", "remote_address": "fe80::1"},
                    "address_families": ["ipv6"],
                },
            }
        )
