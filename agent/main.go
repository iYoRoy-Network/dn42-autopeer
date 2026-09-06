package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
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

type Config struct {
	ListenAddr       string
	CAFile           string
	CertificateFile  string
	PrivateKeyFile   string
	SigningPublicKey string
	StateDir         string
	WireGuardKeyFile string
	BirdPeerDir      string
}

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
	OwnV4 string       `json:"own_v4,omitempty"`
	OwnV6 string       `json:"own_v6,omitempty"`
	MPBGP bool         `json:"mp_bgp"`
	IPv4  *IPv4Request `json:"ipv4,omitempty"`
	IPv6  *IPv6Request `json:"ipv6,omitempty"`
}

type PeerRequest struct {
	WireGuard WireGuardRequest `json:"wireguard"`
	BGP       BGPRequest       `json:"bgp"`
}

type StoredPeer struct {
	PublicKey string `json:"public_key"`
}

var execCommand = func(name string, args ...string) *exec.Cmd {
	return exec.Command(name, args...)
}

func main() {
	config, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}
	key, err := loadEd25519PublicKey(config.SigningPublicKey)
	if err != nil {
		log.Fatal(err)
	}
	agent := &Agent{config: config, key: key, nonces: &NonceStore{entries: make(map[string]time.Time)}}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", agent.healthz)
	mux.HandleFunc("/api/v1/", agent.peer)
	tlsConfig, err := loadTLSConfig(config)
	if err != nil {
		log.Fatal(err)
	}
	server := &http.Server{
		Addr:              config.ListenAddr,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       30 * time.Second,
		TLSConfig:         tlsConfig,
	}
	log.Printf("autopeer agent listening on %s", config.ListenAddr)
	log.Fatal(server.ListenAndServeTLS("", ""))
}

func loadConfig() (Config, error) {
	config := Config{
		ListenAddr:       envOr("AUTOPEER_AGENT_LISTEN_ADDR", ":8443"),
		CAFile:           os.Getenv("AUTOPEER_AGENT_CA_FILE"),
		CertificateFile:  os.Getenv("AUTOPEER_AGENT_CERT_FILE"),
		PrivateKeyFile:   os.Getenv("AUTOPEER_AGENT_KEY_FILE"),
		SigningPublicKey: os.Getenv("AUTOPEER_AGENT_SIGNING_PUBLIC_KEY_FILE"),
		StateDir:         envOr("AUTOPEER_AGENT_STATE_DIR", "/var/lib/autopeer-agent"),
		WireGuardKeyFile: envOr("AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY_FILE", "/etc/wireguard/autopeer.key"),
		BirdPeerDir:      envOr("AUTOPEER_AGENT_BIRD_PEER_DIR", "/etc/bird/dn42/peers"),
	}
	for name, value := range map[string]string{
		"AUTOPEER_AGENT_CA_FILE":                    config.CAFile,
		"AUTOPEER_AGENT_CERT_FILE":                  config.CertificateFile,
		"AUTOPEER_AGENT_KEY_FILE":                   config.PrivateKeyFile,
		"AUTOPEER_AGENT_SIGNING_PUBLIC_KEY_FILE":    config.SigningPublicKey,
		"AUTOPEER_AGENT_WIREGUARD_PRIVATE_KEY_FILE": config.WireGuardKeyFile,
	} {
		if value == "" {
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

func (a *Agent) healthz(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *Agent) peer(w http.ResponseWriter, r *http.Request) {
	asn, ok := parseASN(strings.TrimPrefix(r.URL.Path, "/api/v1/"))
	if !ok {
		http.Error(w, "not found", http.StatusNotFound)
		return
	}
	if r.Method != http.MethodPost && r.Method != http.MethodPut && r.Method != http.MethodDelete {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	body, err := io.ReadAll(io.LimitReader(r.Body, maxBodyBytes+1))
	if err != nil || len(body) > maxBodyBytes {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if err := a.verifyRequest(r, body); err != nil {
		http.Error(w, err.Error(), http.StatusUnauthorized)
		return
	}
	state, stateErr := a.loadPeer(asn)
	if r.Method == http.MethodPost && stateErr == nil {
		http.Error(w, "peer already exists", http.StatusConflict)
		return
	}
	if r.Method == http.MethodPut && stateErr != nil && !os.IsNotExist(stateErr) {
		http.Error(w, "cannot read peer state", http.StatusInternalServerError)
		return
	}
	if r.Method == http.MethodPut && os.IsNotExist(stateErr) {
		http.Error(w, "peer does not exist", http.StatusNotFound)
		return
	}
	if r.Method == http.MethodDelete {
		err = a.removePeer(asn, state)
	} else {
		var request PeerRequest
		decoder := json.NewDecoder(strings.NewReader(string(body)))
		decoder.DisallowUnknownFields()
		err = decoder.Decode(&request)
		if err == nil {
			err = validatePeerRequest(request)
		}
		if err == nil {
			err = a.applyPeer(asn, request)
		}
	}
	if err != nil {
		log.Printf("peer AS%d %s failed: %v", asn, r.Method, err)
		http.Error(w, "deployment failed", http.StatusUnprocessableEntity)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (a *Agent) verifyRequest(r *http.Request, body []byte) error {
	timestamp, err := strconv.ParseInt(r.Header.Get("X-Autopeer-Timestamp"), 10, 64)
	if err != nil {
		return errors.New("invalid request timestamp")
	}
	requestTime := time.Unix(timestamp, 0)
	if time.Since(requestTime) > timestampSkew || time.Until(requestTime) > timestampSkew {
		return errors.New("request timestamp outside allowed window")
	}
	nonce := r.Header.Get("X-Autopeer-Nonce")
	if nonce == "" || len(nonce) > 128 || strings.ContainsAny(nonce, "\r\n") {
		return errors.New("invalid request nonce")
	}
	hashHeader := strings.ToLower(r.Header.Get("X-Autopeer-Body-SHA256"))
	digest := sha256.Sum256(body)
	if hashHeader != hex.EncodeToString(digest[:]) {
		return errors.New("request body hash mismatch")
	}
	signature, err := base64.RawURLEncoding.DecodeString(r.Header.Get("X-Autopeer-Signature"))
	if err != nil || len(signature) != ed25519.SignatureSize {
		return errors.New("invalid request signature")
	}
	message := strings.Join([]string{r.Method, r.URL.EscapedPath(), strconv.FormatInt(timestamp, 10), nonce, hashHeader}, "\n")
	if !ed25519.Verify(a.key, []byte(message), signature) {
		return errors.New("invalid request signature")
	}
	return a.nonces.Use(nonce, requestTime)
}

func (s *NonceStore) Use(nonce string, timestamp time.Time) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	for key, value := range s.entries {
		if time.Since(value) > timestampSkew {
			delete(s.entries, key)
		}
	}
	if _, exists := s.entries[nonce]; exists {
		return errors.New("request nonce already used")
	}
	s.entries[nonce] = timestamp
	return nil
}

func parseASN(value string) (int, bool) {
	if !asnPattern.MatchString(value) {
		return 0, false
	}
	asn, err := strconv.Atoi(value)
	return asn, err == nil && asn >= asnMin && asn <= asnMax
}

func validatePeerRequest(request PeerRequest) error {
	if !validWireGuardKey(request.WireGuard.PublicKey) || request.WireGuard.ListenPort < 1 || request.WireGuard.ListenPort > 65535 || request.WireGuard.MTU < 576 || request.WireGuard.MTU > 9000 {
		return errors.New("invalid WireGuard parameters")
	}
	if !validEndpoint(request.WireGuard.Endpoint) {
		return errors.New("invalid WireGuard endpoint")
	}
	if request.BGP.IPv4 == nil && request.BGP.IPv6 == nil {
		return errors.New("at least one BGP address family is required")
	}
	if request.BGP.MPBGP && request.BGP.IPv6 == nil {
		return errors.New("MP-BGP requires IPv6")
	}
	if request.BGP.IPv4 != nil {
		if net.ParseIP(request.BGP.OwnV4) == nil || net.ParseIP(request.BGP.IPv4.Neighbor).To4() == nil {
			return errors.New("invalid IPv4 local or neighbor address")
		}
	}
	if request.BGP.IPv6 != nil {
		neighbor := net.ParseIP(request.BGP.IPv6.Neighbor)
		if net.ParseIP(request.BGP.OwnV6) == nil || neighbor == nil || neighbor.To4() != nil {
			return errors.New("invalid IPv6 local or neighbor address")
		}
		if request.BGP.IPv6.LLA != neighbor.IsLinkLocalUnicast() {
			return errors.New("IPv6 neighbor does not match lla flag")
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

func (a *Agent) applyPeer(asn int, request PeerRequest) error {
	interfaceName := fmt.Sprintf("dn42_%d", asn)
	keyPath := a.config.WireGuardKeyFile
	if _, err := os.Stat(keyPath); err != nil {
		return fmt.Errorf("WireGuard private key unavailable: %w", err)
	}
	if err := ensureInterface(interfaceName, keyPath, request.WireGuard.ListenPort, request.WireGuard.MTU); err != nil {
		return err
	}
	args := []string{"set", interfaceName, "peer", request.WireGuard.PublicKey, "allowed-ips", "10.0.0.0/8,172.20.0.0/14,172.31.0.0/16,fd00::/8,fe00::/8", "endpoint", request.WireGuard.Endpoint}
	if _, err := run("wg", args...); err != nil {
		return err
	}
	if _, err := run("ip", "link", "set", "dev", interfaceName, "up"); err != nil {
		return err
	}
	if err := applyAddresses(interfaceName, request); err != nil {
		return err
	}
	if err := writeBirdConfigs(a.config.BirdPeerDir, asn, request); err != nil {
		return err
	}
	if _, err := run("birdc", "configure"); err != nil {
		return err
	}
	return a.savePeer(asn, StoredPeer{PublicKey: request.WireGuard.PublicKey})
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

func applyAddresses(interfaceName string, request PeerRequest) error {
	if request.BGP.IPv4 != nil {
		if _, err := run("ip", "-4", "addr", "replace", request.BGP.OwnV4+"/32", "peer", request.BGP.IPv4.Neighbor+"/32", "dev", interfaceName); err != nil {
			return err
		}
	}
	if request.BGP.IPv6 != nil {
		if request.BGP.IPv6.LLA {
			if _, err := run("ip", "-6", "addr", "replace", "fe80::2024/64", "dev", interfaceName); err != nil {
				return err
			}
		} else if _, err := run("ip", "-6", "addr", "replace", request.BGP.OwnV6+"/128", "peer", request.BGP.IPv6.Neighbor+"/128", "dev", interfaceName); err != nil {
			return err
		}
	}
	return nil
}

func (a *Agent) removePeer(asn int, state StoredPeer) error {
	interfaceName := fmt.Sprintf("dn42_%d", asn)
	if state.PublicKey != "" {
		if _, err := run("wg", "set", interfaceName, "peer", state.PublicKey, "remove"); err != nil {
			log.Printf("remove WireGuard peer AS%d: %v", asn, err)
		}
	}
	if _, err := run("ip", "link", "delete", "dev", interfaceName); err != nil {
		log.Printf("remove WireGuard interface AS%d: %v", asn, err)
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
	path := filepath.Join(a.config.StateDir, fmt.Sprintf("peer_%d.json", asn))
	if err := os.Remove(path); err != nil && !os.IsNotExist(err) {
		return err
	}
	return nil
}

func writeBirdConfigs(directory string, asn int, request PeerRequest) error {
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
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d.conf", asn)), content)
	}
	if request.BGP.IPv4 != nil {
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d_v4' from dnpeers {\n    neighbor %s as %d;\n    ipv4 {};\n};\n", asn, request.BGP.IPv4.Neighbor, asn)
		if err := writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v4.conf", asn)), content); err != nil {
			return err
		}
	}
	if request.BGP.IPv6 != nil {
		neighbor := request.BGP.IPv6.Neighbor
		if request.BGP.IPv6.LLA {
			neighbor += fmt.Sprintf(" %% 'dn42_%d'", asn)
		}
		content := fmt.Sprintf("protocol bgp 'dn42_peer_%d_v6' from dnpeers {\n    neighbor %s as %d;\n    ipv6 {};\n};\n", asn, neighbor, asn)
		return writeRootFile(filepath.Join(directory, fmt.Sprintf("dn42_peer_%d_v6.conf", asn)), content)
	}
	return nil
}

func writeRootFile(path, content string) error {
	temporary, err := os.CreateTemp(filepath.Dir(path), ".autopeer-*")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if err := temporary.Chmod(0644); err != nil {
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

func (a *Agent) savePeer(asn int, state StoredPeer) error {
	data, err := json.Marshal(state)
	if err != nil {
		return err
	}
	path := filepath.Join(a.config.StateDir, fmt.Sprintf("peer_%d.json", asn))
	return os.WriteFile(path, data, 0600)
}

func (a *Agent) loadPeer(asn int) (StoredPeer, error) {
	data, err := os.ReadFile(filepath.Join(a.config.StateDir, fmt.Sprintf("peer_%d.json", asn)))
	if err != nil {
		return StoredPeer{}, err
	}
	var state StoredPeer
	return state, json.Unmarshal(data, &state)
}

func run(name string, args ...string) ([]byte, error) {
	command := execCommand(name, args...)
	output, err := command.CombinedOutput()
	if err != nil {
		return output, fmt.Errorf("%s failed: %w", name, err)
	}
	return output, nil
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
