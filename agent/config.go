package main

import (
	"crypto/ed25519"
	"crypto/tls"
	"crypto/x509"
	"encoding/pem"
	"errors"
	"fmt"
	"os"
)

func loadConfig() (Config, error) {
	config := Config{
		ListenAddr:          envOr("AUTOPEER_AGENT_LISTEN_ADDR", ":8443"),
		CAFile:              os.Getenv("AUTOPEER_AGENT_CA_FILE"),
		CertificateFile:     os.Getenv("AUTOPEER_AGENT_CERT_FILE"),
		PrivateKeyFile:      os.Getenv("AUTOPEER_AGENT_KEY_FILE"),
		SigningPublicKey:    os.Getenv("AUTOPEER_AGENT_SIGNING_PUBLIC_KEY_FILE"),
		StateDir:            envOr("AUTOPEER_AGENT_STATE_DIR", "/var/lib/autopeer-agent"),
		WireGuardPrivateKey: os.Getenv("AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY"),
		OwnV4:               os.Getenv("AUTOPEER_AGENT_OWN_V4"),
		OwnV6:               os.Getenv("AUTOPEER_AGENT_OWN_V6"),
		BirdPeerDir:         envOr("AUTOPEER_AGENT_BIRD_PEER_DIR", "/etc/bird/dn42/peers"),
	}
	for name, value := range map[string]string{
		"AUTOPEER_AGENT_CA_FILE":                 config.CAFile,
		"AUTOPEER_AGENT_CERT_FILE":               config.CertificateFile,
		"AUTOPEER_AGENT_KEY_FILE":                config.PrivateKeyFile,
		"AUTOPEER_AGENT_SIGNING_PUBLIC_KEY_FILE": config.SigningPublicKey,
		"AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY":   config.WireGuardPrivateKey,
		"AUTOPEER_AGENT_OWN_V4":                  config.OwnV4,
		"AUTOPEER_AGENT_OWN_V6":                  config.OwnV6,
	} {
		if value == "" && name != "AUTOPEER_AGENT_OWN_V4" && name != "AUTOPEER_AGENT_OWN_V6" {
			return Config{}, fmt.Errorf("%s is required", name)
		}
	}
	if err := os.MkdirAll(config.StateDir, 0700); err != nil {
		return Config{}, fmt.Errorf("create state directory: %w", err)
	}
	return config, nil
}

func loadTLSConfig(config Config) (*tls.Config, error) {
	cert, err := tls.LoadX509KeyPair(config.CertificateFile, config.PrivateKeyFile)
	if err != nil {
		return nil, fmt.Errorf("load agent TLS certificate: %w", err)
	}
	caPEM, err := os.ReadFile(config.CAFile)
	if err != nil {
		return nil, fmt.Errorf("read agent CA: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		return nil, errors.New("agent CA contains no certificates")
	}
	return &tls.Config{
		MinVersion:   tls.VersionTLS13,
		Certificates: []tls.Certificate{cert},
		ClientAuth:   tls.RequireAndVerifyClientCert,
		ClientCAs:    pool,
	}, nil
}

func loadEd25519PublicKey(path string) (ed25519.PublicKey, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read signing public key: %w", err)
	}
	if len(data) == ed25519.PublicKeySize {
		return ed25519.PublicKey(data), nil
	}
	block, _ := pem.Decode(data)
	if block == nil {
		return nil, errors.New("signing public key is neither raw Ed25519 nor PEM")
	}
	key, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse signing public key: %w", err)
	}
	publicKey, ok := key.(ed25519.PublicKey)
	if !ok {
		return nil, errors.New("signing public key is not Ed25519")
	}
	return publicKey, nil
}

func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
