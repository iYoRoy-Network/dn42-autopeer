package main

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"time"
)

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
