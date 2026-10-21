from botocore.exceptions import ClientError

from devopsagent.runners.strands import _is_transient


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "ConverseStream")


def test_bedrock_server_errors_are_transient():
    assert _is_transient(_client_error("internalServerException"))
    assert _is_transient(_client_error("ServiceUnavailableException"))
    assert _is_transient(_client_error("modelStreamErrorException"))


def test_client_errors_are_not_transient():
    assert not _is_transient(_client_error("ValidationException"))
    assert not _is_transient(_client_error("AccessDeniedException"))
    assert not _is_transient(ValueError("not a client error"))
