package main

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
)

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
	_, configErr := os.Stat(a.peerConfigPath(asn))
	if r.Method == http.MethodPost && configErr == nil {
		http.Error(w, "peer already exists", http.StatusConflict)
		return
	}
	if r.Method == http.MethodPut && configErr != nil && !os.IsNotExist(configErr) {
		http.Error(w, "cannot read peer configuration", http.StatusInternalServerError)
		return
	}
	if r.Method == http.MethodPut && os.IsNotExist(configErr) {
		http.Error(w, "peer does not exist", http.StatusNotFound)
		return
	}
	if r.Method == http.MethodDelete {
		err = a.removePeer(asn)
	} else {
		var request PeerRequest
		decoder := json.NewDecoder(strings.NewReader(string(body)))
		decoder.DisallowUnknownFields()
		err = decoder.Decode(&request)
		if err == nil {
			var extra any
			err = decoder.Decode(&extra)
			if err != io.EOF {
				err = errors.New("request body must contain exactly one JSON object")
			}
		}
		if err == nil {
			err = validatePeerRequest(asn, request, a.config)
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

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
