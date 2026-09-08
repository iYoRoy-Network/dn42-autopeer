package main

import (
	"fmt"
	"log"
	"os"
	"path/filepath"
)

func (a *Agent) removePeer(asn int) error {
	interfaceName := fmt.Sprintf("dn42_%d", asn)
	if _, err := run("systemctl", "disable", "--now", "wg-quick@"+interfaceName); err != nil {
		log.Printf("stop WireGuard %s: %v", interfaceName, err)
	}
	for _, suffix := range []string{"", "_v4", "_v6"} {
		path := filepath.Join(a.config.BirdPeerDir, fmt.Sprintf("dn42_peer_%d%s.conf", asn, suffix))
		if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
			return err
		}
	}
	if _, err := run("birdc", "configure"); err != nil {
		return err
	}
	if err := os.Remove(a.peerConfigPath(asn)); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}
