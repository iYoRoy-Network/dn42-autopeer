package main

import (
	"log"
	"net/http"
	"time"
)

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
