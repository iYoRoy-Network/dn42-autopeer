package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func readBirdConf(t *testing.T, path string) string {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	return string(data)
}

// A peer whose ASN matches the local one is iBGP to BIRD, which defaults such
// sessions to multihop, and link-local addresses reject multihop outright.
// Declaring the link-local session direct is what keeps it loadable.
func TestWriteBirdConfigsMarksLinkLocalMPBGPAsDirect(t *testing.T) {
	directory := t.TempDir()
	request := PeerRequest{BGP: BGPRequest{
		MPBGP: true,
		IPv6:  &IPv6Request{LLA: true, Neighbor: "fe80::1234"},
	}}

	if err := writeBirdConfigs(directory, 4242422024, request, Config{}); err != nil {
		t.Fatalf("writeBirdConfigs: %v", err)
	}

	got := readBirdConf(t, filepath.Join(directory, "dn42_peer_4242422024.conf"))
	want := "protocol bgp 'dn42_peer_4242422024' from dnpeers {\n" +
		"    direct;\n" +
		"    neighbor fe80::1234 % 'dn42_4242422024' as 4242422024;\n" +
		"    ipv4 {\n" +
		"        extended next hop;\n" +
		"    };\n" +
		"};\n"
	if got != want {
		t.Errorf("generated config mismatch\n got: %q\nwant: %q", got, want)
	}
}

func TestWriteBirdConfigsLeavesGlobalIPv6Alone(t *testing.T) {
	directory := t.TempDir()
	request := PeerRequest{BGP: BGPRequest{
		MPBGP: true,
		IPv6:  &IPv6Request{Neighbor: "fd18:3e15:61d0::1"},
	}}

	if err := writeBirdConfigs(directory, 4242423998, request, Config{}); err != nil {
		t.Fatalf("writeBirdConfigs: %v", err)
	}

	got := readBirdConf(t, filepath.Join(directory, "dn42_peer_4242423998.conf"))
	if strings.Contains(got, "direct;") {
		t.Errorf("a global IPv6 neighbor must not be pinned to direct mode:\n%s", got)
	}
	if !strings.Contains(got, "neighbor fd18:3e15:61d0::1 as 4242423998;") {
		t.Errorf("global neighbor lost its interface-free form:\n%s", got)
	}
}

func TestWriteBirdConfigsSplitsAndMarksLinkLocalSession(t *testing.T) {
	directory := t.TempDir()
	request := PeerRequest{BGP: BGPRequest{
		IPv4: &IPv4Request{Neighbor: "172.20.234.9"},
		IPv6: &IPv6Request{LLA: true, Neighbor: "fe80::9"},
	}}

	if err := writeBirdConfigs(directory, 4242423997, request, Config{}); err != nil {
		t.Fatalf("writeBirdConfigs: %v", err)
	}

	v6 := readBirdConf(t, filepath.Join(directory, "dn42_peer_4242423997_v6.conf"))
	if !strings.Contains(v6, "direct;") {
		t.Errorf("link-local v6 session is missing direct:\n%s", v6)
	}
	if !strings.Contains(v6, "neighbor fe80::9 % 'dn42_4242423997' as 4242423997;") {
		t.Errorf("link-local neighbor lost its interface binding:\n%s", v6)
	}
	v4 := readBirdConf(t, filepath.Join(directory, "dn42_peer_4242423997_v4.conf"))
	if strings.Contains(v4, "direct;") {
		t.Errorf("IPv4 sessions have no multihop default to override:\n%s", v4)
	}
}
