package main

import (
	"crypto/ed25519"
	"regexp"
	"sync"
	"time"
)

const (
	maxBodyBytes  = 64 << 10
	timestampSkew = 5 * time.Minute
	asnMin        = 4242420001
	asnMax        = 4242423999
)

var asnPattern = regexp.MustCompile(`^[0-9]+$`)
var hostPattern = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
var wireGuardAllowedIPs = []string{"10.0.0.0/8", "172.20.0.0/14", "172.31.0.0/16", "fd00::/8", "fe00::/8"}

type Config struct{ ListenAddr, CAFile, CertificateFile, PrivateKeyFile, SigningPublicKey, StateDir, WireGuardPrivateKey, OwnV4, OwnV6, BirdPeerDir string }
type Agent struct {
	config Config
	key    ed25519.PublicKey
	nonces *NonceStore
}
type NonceStore struct {
	mu      sync.Mutex
	entries map[string]time.Time
}
type WireGuardRequest struct {
	PublicKey  string `json:"public_key"`
	Endpoint   string `json:"endpoint"`
	ListenPort int    `json:"listen_port"`
	MTU        int    `json:"mtu"`
}
type IPv4Request struct {
	Neighbor string `json:"neighbor"`
}
type IPv6Request struct {
	LLA      bool   `json:"lla"`
	Neighbor string `json:"neighbor"`
}
type BGPRequest struct {
	MPBGP bool         `json:"mp_bgp"`
	IPv4  *IPv4Request `json:"ipv4,omitempty"`
	IPv6  *IPv6Request `json:"ipv6,omitempty"`
}
type PeerRequest struct {
	WireGuard WireGuardRequest `json:"wireguard"`
	BGP       BGPRequest       `json:"bgp"`
}
