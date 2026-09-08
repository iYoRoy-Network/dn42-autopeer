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
		neighbor := request.BGP.IPv6.Neighbor
		if request.BGP.IPv6.LLA {
			neighbor += fmt.Sprintf(" %% 'dn42_%d'", asn)
		}
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d' from dnpeers {\n    neighbor %s as %d;\n    ipv4 {\n        extended next hop;\n    };\n};\n", asn, neighbor, asn)
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d.conf", asn)), content, 0644)
	}
	if request.BGP.IPv4 != nil {
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d_v4' from dnpeers {\n    neighbor %s as %d;\n    ipv4 {};\n};\n", asn, request.BGP.IPv4.Neighbor, asn)
		if err := writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v4.conf", asn)), content, 0644); err != nil {
			return err
		}
	}
	if request.BGP.IPv6 != nil {
		neighbor := request.BGP.IPv6.Neighbor
		if request.BGP.IPv6.LLA {
			neighbor += fmt.Sprintf(" %% 'dn42_%d'", asn)
		}
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d_v6' from dnpeers {\n    neighbor %s as %d;\n    ipv6 {};\n};\n", asn, neighbor, asn)
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v6.conf", asn)), content, 0644)
	}
	return nil
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
