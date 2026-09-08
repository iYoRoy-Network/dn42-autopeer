package main

import (
	"fmt"
	"os/exec"
)

var execCommand = func(name string, args ...string) *exec.Cmd { return exec.Command(name, args...) }

func run(name string, args ...string) ([]byte, error) {
	command := execCommand(name, args...)
	output, err := command.CombinedOutput()
	if err != nil {
		return output, fmt.Errorf("%s failed: %w", name, err)
	}
	return output, nil
}
