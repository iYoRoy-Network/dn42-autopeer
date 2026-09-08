package main

import (
	"errors"
	"fmt"
	"path/filepath"
	"strconv"
	"strings"
)

func (a *Agent) applyPeer(asn int, request PeerRequest) error {
	interfaceName := fmt.Sprintf("dn42_%d", asn)
	configText, err := renderWireGuardConfig(interfaceName, a.config, request)
	if err != nil {
		return err
	}
	configPath := a.peerConfigPath(asn)
	if err := writeRootFile(configPath, configText, 0600); err != nil {
		return err
	}
	if _, err := run("systemctl", "enable", "wg-quick@"+interfaceName); err != nil {
		return err
	}
	if _, err := run("systemctl", "restart", "wg-quick@"+interfaceName); err != nil {
		return err
	}
	if err := writeBirdConfigs(a.config.BirdPeerDir, asn, request, a.config); err != nil {
		return err
	}
	if _, err := run("birdc", "configure"); err != nil {
		return err
	}
	return nil
}

func (a *Agent) peerConfigPath(asn int) string {
	return filepath.Join("/etc/wireguard", fmt.Sprintf("dn42_%d.conf", asn))
}

func renderWireGuardConfig(interfaceName string, config Config, request PeerRequest) (string, error) {
	if !validWireGuardKey(config.WireGuardPrivateKey) {
		return "", errors.New("invalid WireGuard private key")
	}
	var b strings.Builder
	b.WriteString("[Interface]\n")
	b.WriteString("PrivateKey = ")
	b.WriteString(config.WireGuardPrivateKey)
	b.WriteString("\nListenPort = ")
	b.WriteString(strconv.Itoa(request.WireGuard.ListenPort))
	b.WriteString("\nMTU = ")
	b.WriteString(strconv.Itoa(request.WireGuard.MTU))
	b.WriteString("\nTable = off\n")
	if request.BGP.IPv4 != nil {
		b.WriteString("Address = ")
		b.WriteString(config.OwnV4)
		b.WriteString("/32\n")
		b.WriteString("PostUp = ip -4 addr replace ")
		b.WriteString(config.OwnV4)
		b.WriteString("/32 peer ")
		b.WriteString(request.BGP.IPv4.Neighbor)
		b.WriteString("/32 dev %i || true\n")
		b.WriteString("PostDown = ip -4 addr del ")
		b.WriteString(config.OwnV4)
		b.WriteString("/32 dev %i || true\n")
	}
	if request.BGP.IPv6 != nil {
		if request.BGP.IPv6.LLA {
			b.WriteString("Address = fe80::2024/64\n")
		} else {
			b.WriteString("Address = ")
			b.WriteString(config.OwnV6)
			b.WriteString("/128\n")
			b.WriteString("PostUp = ip -6 addr replace ")
			b.WriteString(config.OwnV6)
			b.WriteString("/128 peer ")
			b.WriteString(request.BGP.IPv6.Neighbor)
			b.WriteString("/128 dev %i || true\n")
			b.WriteString("PostDown = ip -6 addr del ")
			b.WriteString(config.OwnV6)
			b.WriteString("/128 dev %i || true\n")
		}
	}
	b.WriteString("\n[Peer]\nPublicKey = ")
	b.WriteString(request.WireGuard.PublicKey)
	b.WriteString("\nAllowedIPs = 10.0.0.0/8, 172.20.0.0/14, 172.31.0.0/16, fd00::/8, fe00::/8\n")
	if request.WireGuard.Endpoint != "" {
		b.WriteString("Endpoint = ")
		b.WriteString(request.WireGuard.Endpoint)
		b.WriteString("\n")
	}
	_ = interfaceName
	return b.String(), nil
}

func ensureInterface(name, keyPath string, port, mtu int) error {
	if _, err := run("ip", "link", "show", "dev", name); err != nil {
		if _, err := run("ip", "link", "add", "dev", name, "type", "wireguard"); err != nil {
			return err
		}
	}
	if _, err := run("wg", "set", name, "private-key", keyPath, "listen-port", strconv.Itoa(port)); err != nil {
		return err
	}
	_, err := run("ip", "link", "set", "dev", name, "mtu", strconv.Itoa(mtu))
	return err
}

func applyAddresses(interfaceName string, request PeerRequest, config Config) error {
	if request.BGP.IPv4 != nil {
		if _, err := run("ip", "-4", "addr", "replace", config.OwnV4+"/32", "peer", request.BGP.IPv4.Neighbor+"/32", "dev", interfaceName); err != nil {
			return err
		}
	}
	if request.BGP.IPv6 != nil {
		if request.BGP.IPv6.LLA {
			if _, err := run("ip", "-6", "addr", "replace", "fe80::2024/64", "dev", interfaceName); err != nil {
				return err
			}
		} else if _, err := run("ip", "-6", "addr", "replace", config.OwnV6+"/128", "peer", request.BGP.IPv6.Neighbor+"/128", "dev", interfaceName); err != nil {
			return err
		}
	}
	return nil
}
