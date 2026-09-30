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

func writeAndRead(t *testing.T, asn int, request PeerRequest, name string) string {
	t.Helper()
	directory := t.TempDir()
	if err := writeBirdConfigs(directory, asn, request, Config{}); err != nil {
		t.Fatalf("writeBirdConfigs: %v", err)
	}
	return readBirdConf(t, filepath.Join(directory, name))
}

func assertConf(t *testing.T, got, want string) {
	t.Helper()
	if got != want {
		t.Errorf("generated config mismatch\n got: %q\nwant: %q", got, want)
	}
}

// A peer whose ASN matches the local one is iBGP to BIRD, which defaults such
// sessions to multihop, and link-local addresses reject multihop outright.
// Declaring the link-local session direct is what keeps it loadable.
func TestWriteBirdConfigsMarksLinkLocalMPBGPAsDirect(t *testing.T) {
	got := writeAndRead(t, 4242422024, PeerRequest{
		BGP: BGPRequest{MPBGP: true, IPv6: &IPv6Request{LLA: true, Neighbor: "fe80::1234"}},
	}, "dn42_peer_4242422024.conf")

	assertConf(t, got, "protocol bgp 'dn42_peer_4242422024' from dnpeers {\n"+
		"    direct;\n"+
		"    neighbor fe80::1234 % 'dn42_4242422024' as 4242422024;\n"+
		"    ipv4 {\n"+
		"        extended next hop;\n"+
		"    };\n"+
		"};\n")
}

func TestWriteBirdConfigsLeavesGlobalIPv6Alone(t *testing.T) {
	got := writeAndRead(t, 4242423998, PeerRequest{
		BGP: BGPRequest{MPBGP: true, IPv6: &IPv6Request{Neighbor: "fd18:3e15:61d0::1"}},
	}, "dn42_peer_4242423998.conf")

	if strings.Contains(got, "direct;") {
		t.Errorf("a global IPv6 neighbor must not be pinned to direct mode:\n%s", got)
	}
	if !strings.Contains(got, "neighbor fd18:3e15:61d0::1 as 4242423998;") {
		t.Errorf("global neighbor lost its interface-free form:\n%s", got)
	}
}

// The dnpeers template enables both address families, so each half of an
// independent-session peer has to switch the other family off explicitly.
// Without it an IPv4-only peer quietly exchanges IPv6 routes too.
func TestWriteBirdConfigsClosesUnusedFamily(t *testing.T) {
	request := PeerRequest{BGP: BGPRequest{
		IPv4: &IPv4Request{Neighbor: "172.20.234.9"},
		IPv6: &IPv6Request{LLA: true, Neighbor: "fe80::9"},
	}}

	assertConf(t, writeAndRead(t, 4242423997, request, "dn42_peer_4242423997_v4.conf"),
		"protocol bgp 'dn42_peer_4242423997_v4' from dnpeers {\n"+
			"    neighbor 172.20.234.9 as 4242423997;\n"+
			"    ipv6 {\n"+
			"        import none;\n"+
			"        export none;\n"+
			"    };\n"+
			"};\n")

	assertConf(t, writeAndRead(t, 4242423997, request, "dn42_peer_4242423997_v6.conf"),
		"protocol bgp 'dn42_peer_4242423997_v6' from dnpeers {\n"+
			"    direct;\n"+
			"    neighbor fe80::9 % 'dn42_4242423997' as 4242423997;\n"+
			"    ipv4 {\n"+
			"        import none;\n"+
			"        export none;\n"+
			"    };\n"+
			"};\n")
}

func TestWriteBirdConfigsEmitsDescription(t *testing.T) {
	got := writeAndRead(t, 4242422024, PeerRequest{
		Description: "@someone https://example.test/peer",
		BGP:         BGPRequest{MPBGP: true, IPv6: &IPv6Request{LLA: true, Neighbor: "fe80::1234"}},
	}, "dn42_peer_4242422024.conf")

	if !strings.Contains(got, "    description \"@someone https://example.test/peer\";\n") {
		t.Errorf("description line missing:\n%s", got)
	}
	// The Jinja template puts it directly under the opening brace.
	if !strings.HasPrefix(got, "protocol bgp 'dn42_peer_4242422024' from dnpeers {\n    description ") {
		t.Errorf("description must lead the protocol block:\n%s", got)
	}
}

func TestBirdDescriptionEscapesQuotesAndBackslashes(t *testing.T) {
	// Matches the template's replace('\\','\\\\') | replace('"','\\"').
	cases := map[string]string{
		"":                   "",
		"plain":              "    description \"plain\";\n",
		`he said "hi"`:       `    description "he said \"hi\"";` + "\n",
		`back\slash`:         `    description "back\\slash";` + "\n",
		`both "and" back\ok`: `    description "both \"and\" back\\ok";` + "\n",
	}
	for description, want := range cases {
		if got := birdDescription(description); got != want {
			t.Errorf("birdDescription(%q)\n got: %q\nwant: %q", description, got, want)
		}
	}
}
