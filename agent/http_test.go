package main

import (
	"io"
	"testing"
)

const validPeerBody = `{
	"wireguard": {
		"public_key": "vKIhFMvKHDVEcRls1IH7si2MSia73H3lsXAWrrC+5zU=",
		"endpoint": "205.198.65.116:40004",
		"listen_port": 21771,
		"mtu": 1420
	},
	"bgp": {
		"mp_bgp": false,
		"ipv4": {"neighbor": "172.20.234.225"}
	}
}`

// A well-formed body used to come back as "failed: EOF" with a 422. The second
// Decode returns io.EOF to signal "no trailing content", which is the desired
// outcome, but the handler stored that sentinel in err instead of clearing it.
func TestDecodePeerRequestAcceptsSingleObject(t *testing.T) {
	request, err := decodePeerRequest([]byte(validPeerBody))
	if err != nil {
		t.Fatalf("valid body rejected: %v", err)
	}
	if request.WireGuard.ListenPort != 21771 {
		t.Errorf("listen port = %d, want 21771", request.WireGuard.ListenPort)
	}
	if request.WireGuard.MTU != 1420 {
		t.Errorf("mtu = %d, want 1420", request.WireGuard.MTU)
	}
	if request.BGP.IPv4 == nil || request.BGP.IPv4.Neighbor != "172.20.234.225" {
		t.Errorf("ipv4 neighbor not decoded: %+v", request.BGP.IPv4)
	}
	if request.BGP.IPv6 != nil {
		t.Errorf("unexpected ipv6 session: %+v", request.BGP.IPv6)
	}
}

func TestDecodePeerRequestAcceptsMPBGPv6(t *testing.T) {
	body := `{"wireguard":{"public_key":"vKIhFMvKHDVEcRls1IH7si2MSia73H3lsXAWrrC+5zU=",` +
		`"endpoint":"[fd00::1]:21771","listen_port":21771,"mtu":1420},` +
		`"bgp":{"mp_bgp":true,"ipv6":{"lla":true,"neighbor":"fe80::2024"}}}`
	request, err := decodePeerRequest([]byte(body))
	if err != nil {
		t.Fatalf("valid MP-BGP body rejected: %v", err)
	}
	if !request.BGP.MPBGP || request.BGP.IPv6 == nil || !request.BGP.IPv6.LLA {
		t.Errorf("mp-bgp session not decoded: %+v", request.BGP)
	}
}

func TestDecodePeerRequestRejectsBadBodies(t *testing.T) {
	cases := map[string]string{
		"empty body":       "",
		"whitespace only":  "   \n",
		"unknown field":    `{"wireguard":{"public_key":"k","endpoint":"1.2.3.4:1","listen_port":1,"mtu":1420,"surprise":1},"bgp":{}}`,
		"two objects":      validPeerBody + `{"wireguard":{}}`,
		"trailing garbage": validPeerBody + `oops`,
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := decodePeerRequest([]byte(body)); err == nil {
				t.Fatal("body accepted, want an error")
			}
		})
	}
}

// An empty body is a client bug, and "failed: EOF" told the operator nothing.
func TestDecodePeerRequestEmptyBodyIsNotBareEOF(t *testing.T) {
	_, err := decodePeerRequest(nil)
	if err == nil {
		t.Fatal("empty body accepted")
	}
	if err == io.EOF {
		t.Fatal("empty body still reports the bare io.EOF sentinel")
	}
}

// The peer description is forwarded so the generated BIRD config can carry it.
func TestDecodePeerRequestAcceptsDescription(t *testing.T) {
	body := `{"description":"@someone https://example.test/",` +
		`"wireguard":{"public_key":"k","endpoint":"1.2.3.4:1","listen_port":1,"mtu":1420},` +
		`"bgp":{"ipv4":{"neighbor":"172.20.0.1"}}}`
	request, err := decodePeerRequest([]byte(body))
	if err != nil {
		t.Fatalf("description rejected: %v", err)
	}
	if request.Description != "@someone https://example.test/" {
		t.Errorf("description = %q", request.Description)
	}
}
