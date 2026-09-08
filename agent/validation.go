package main

import (
	"encoding/base64"
	"errors"
	"fmt"
	"net"
	"strconv"
)

func parseASN(value string) (int, bool) {
	if !asnPattern.MatchString(value) {
		return 0, false
	}
	asn, err := strconv.Atoi(value)
	return asn, err == nil && asn >= asnMin && asn <= asnMax
}

func validatePeerRequest(asn int, request PeerRequest, config Config) error {
	if asn < asnMin || asn > asnMax {
		return errors.New("ASN outside the allowed DN42 autopeer range")
	}
	if !validWireGuardKey(request.WireGuard.PublicKey) || request.WireGuard.ListenPort < 1 || request.WireGuard.ListenPort > 65535 || request.WireGuard.MTU < 576 || request.WireGuard.MTU > 9000 {
		return errors.New("invalid WireGuard parameters")
	}
	if !validEndpoint(request.WireGuard.Endpoint) {
		return errors.New("invalid WireGuard endpoint")
	}
	if !validWireGuardKey(config.WireGuardPrivateKey) {
		return errors.New("invalid local WireGuard private key")
	}
	if request.BGP.IPv4 == nil && request.BGP.IPv6 == nil {
		return errors.New("at least one BGP address family is required")
	}
	if request.BGP.MPBGP && request.BGP.IPv6 == nil {
		return errors.New("MP-BGP requires IPv6")
	}
	if request.BGP.IPv4 != nil {
		if net.ParseIP(config.OwnV4).To4() == nil || net.ParseIP(request.BGP.IPv4.Neighbor).To4() == nil {
			return errors.New("invalid IPv4 local or neighbor address")
		}
	}
	if request.BGP.IPv6 != nil {
		neighbor := net.ParseIP(request.BGP.IPv6.Neighbor)
		if net.ParseIP(config.OwnV6) == nil || neighbor == nil || neighbor.To4() != nil {
			return errors.New("invalid IPv6 local or neighbor address")
		}
		if request.BGP.IPv6.LLA != neighbor.IsLinkLocalUnicast() {
			return errors.New("IPv6 neighbor does not match lla flag")
		}
	}
	for _, value := range wireGuardAllowedIPs {
		if _, _, err := net.ParseCIDR(value); err != nil {
			return fmt.Errorf("invalid fixed AllowedIPs policy: %w", err)
		}
	}
	return nil
}

func validWireGuardKey(value string) bool {
	decoded, err := base64.StdEncoding.DecodeString(value)
	return err == nil && len(decoded) == 32
}

func validEndpoint(value string) bool {
	host, port, err := net.SplitHostPort(value)
	if err != nil || host == "" || port == "" {
		return false
	}
	portNumber, err := strconv.Atoi(port)
	if err != nil || portNumber < 1 || portNumber > 65535 {
		return false
	}
	if host[0] == '[' && host[len(host)-1] == ']' {
		host = host[1 : len(host)-1]
	}
	if net.ParseIP(host) != nil {
		return true
	}
	return hostPattern.MatchString(host)
}
