from pathlib import Path
from unittest import mock

import pytest

from autopeer.core.kioubit import KioubitAuthVerifier, effective_name


TEST_PARAMS = "eyJhc24iOiI0MjQyNDIzMDM1IiwidGltZSI6MTY2ODI2NjkyNiwiYWxsb3dlZDQiOiIxNzIuMjIuMTI1LjEyOFwvMjYsMTcyLjIwLjAuODFcLzMyIiwiYWxsb3dlZDYiOiJmZDYzOjVkNDA6NDdlNTo6XC80OCxmZDQyOmQ0MjpkNDI6ODE6OlwvNjQiLCJtbnQiOiJMQVJFLU1OVCIsImF1dGh0eXBlIjoibG9naW5jb2RlIiwiZG9tYWluIjoic3ZjLmJ1cmJsZS5kbjQyIn0="
TEST_SIGNATURE = "MIGIAkIBAmwz3sQ1vOkH8+8e0NJ8GsUqKSaazIWmYDp60sshlTo7gCAopZOZ6/+tD6s+oEGM1i5mKGbHgK9ROATQLHxUZecCQgCa2N828uNn76z1Yg63/c7veMVIiK4l1X9TCUepJnJ3mCto+7ogCP+2vQm6GHipSNRF4wnt6tZbir0HZvrqEnRAmA=="
PUBLIC_KEY = Path(__file__).parents[2] / "config" / "kioubit-public-key.pem"


def test_verifies_signed_kioubit_response_and_returns_identity():
    verifier = KioubitAuthVerifier("svc.burble.dn42", PUBLIC_KEY)

    with mock.patch("time.time", return_value=1668266926):
        identity = verifier.verify(TEST_PARAMS, TEST_SIGNATURE)

    assert identity.asn == 4242423035
    assert identity.display_name is None


def test_accepts_https_prefix_in_configured_domain():
    verifier = KioubitAuthVerifier("https://svc.burble.dn42/", PUBLIC_KEY)

    with mock.patch("time.time", return_value=1668266910):
        assert verifier.verify(TEST_PARAMS, TEST_SIGNATURE).asn == 4242423035


def test_accepts_effective_name_as_display_name():
    assert effective_name("  Kioubit  ") == "Kioubit"
    assert effective_name("\ninvalid") is None
    assert effective_name("x" * 161) is None


def test_rejects_expired_kioubit_response():
    verifier = KioubitAuthVerifier("svc.burble.dn42", PUBLIC_KEY)

    with mock.patch("time.time", return_value=1668266000):
        with pytest.raises(ValueError, match="expired"):
            verifier.verify(TEST_PARAMS, TEST_SIGNATURE)


def test_rejects_wrong_domain():
    verifier = KioubitAuthVerifier("autopeer.example", PUBLIC_KEY)

    with mock.patch("time.time", return_value=1668266926):
        with pytest.raises(ValueError, match="domain"):
            verifier.verify(TEST_PARAMS, TEST_SIGNATURE)
