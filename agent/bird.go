package main

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
)

func writeBirdConfigs(directory string, asn int, request PeerRequest, config Config) error {
	if err := os.MkdirAll(directory, 0755); err != nil {
		return err
	}
	for _, suffix := range []string{"", "_v4", "_v6"} {
		path := filepath.Join(directory, fmt.Sprintf("dn42_peer_%d%s.conf", asn, suffix))
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	if request.BGP.MPBGP {
		content := fmt.Sprintf(
			"protocol bgp 'dn42_peer_%d' from dnpeers {\n%s    neighbor %s as %d;\n    ipv4 {\n        extended next hop;\n    };\n};\n",
			asn, birdDirect(*request.BGP.IPv6), birdNeighbor(asn, *request.BGP.IPv6), asn,
		)
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d.conf", asn)), content, 0644)
	}
	if request.BGP.IPv4 != nil {
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d_v4' from dnpeers {\n    neighbor %s as %d;\n    ipv4 {};\n};\n", asn, request.BGP.IPv4.Neighbor, asn)
		if err := writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v4.conf", asn)), content, 0644); err != nil {
			return err
		}
	}
	if request.BGP.IPv6 != nil {
		content := fmt.Sprintf(
			"protocol bgp 'dn42_peer_%d_v6' from dnpeers {\n%s    neighbor %s as %d;\n    ipv6 {};\n};\n",
			asn, birdDirect(*request.BGP.IPv6), birdNeighbor(asn, *request.BGP.IPv6), asn,
		)
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v6.conf", asn)), content, 0644)
	}
	return nil
}

// birdNeighbor renders the neighbor clause, pinning a link-local address to the
// WireGuard interface it arrives on.
func birdNeighbor(asn int, ipv6 IPv6Request) string {
	if ipv6.LLA {
		return fmt.Sprintf("%s %% 'dn42_%d'", ipv6.Neighbor, asn)
	}
	return ipv6.Neighbor
}

// birdDirect pins a link-local session to direct mode. BIRD defaults every
// session whose remote AS matches the local one to multihop, and link-local
// addresses cannot be used with multihop at all, so a same-AS peer fails to
// load without this.
func birdDirect(ipv6 IPv6Request) string {
	if ipv6.LLA {
		return "    direct;\n"
	}
	return ""
}

func writeRootFile(path, content string, mode fs.FileMode) error {
	temporary, err := os.CreateTemp(filepath.Dir(path), ".autopeer-*")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if err := temporary.Chmod(mode); err != nil {
		return err
	}
	if _, err := temporary.WriteString(content); err != nil {
		return err
	}
	if err := temporary.Sync(); err != nil {
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return os.Rename(name, path)
}
