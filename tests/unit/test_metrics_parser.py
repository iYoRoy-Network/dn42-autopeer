from prometheus_client.parser import text_string_to_metric_families


def test_prometheus_client_parser_available():
    text = 'wireguard_peer_receive_bytes_total{interface="dn42_4242423128"} 42\n'
    families = list(text_string_to_metric_families(text))
    assert families[0].samples[0].value == 42
