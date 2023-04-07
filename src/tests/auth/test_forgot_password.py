import pytest
from grpc import StatusCode
from grpc.aio import AioRpcError, Metadata
from starlette.testclient import TestClient

from app.main import app
from protos import auth_pb2
from tests.mocks import MockAuthClient


async def _run_forgot_password_test(mocker, response_callback):
    mocked_client = MockAuthClient()
    mocker.patch("app.auth.routes.grpc_clients", {"auth": mocked_client})

    mocked_client.stub.ResetPasswordToken = mocker.AsyncMock(
        side_effect=response_callback
    )

    request_data = {"email": "test@example.com"}
    with TestClient(app=app) as client:
        response = client.post("/auth/forgot-password", json=request_data)

    expected_request = auth_pb2.ResetPasswordTokenRequest(**request_data)
    mocked_client.stub.ResetPasswordToken.assert_called_once_with(expected_request)

    return response


@pytest.mark.asyncio
async def test_forgot_password_mocked_success(mocker):
    mocked_mail = mocker.patch("app.auth.routes.generate_email")

    grpc_response = auth_pb2.TokenWithEmail(
        token="reset-token",
        email="test@example.com",
        first_name="Some",
        last_name="One",
    )

    response = await _run_forgot_password_test(mocker, lambda *_: grpc_response)

    assert response.status_code == 202
    assert response.json() is None

    mocked_mail.assert_called_once_with(
        to_address="test@example.com",
        subject="Reset your password",
        template_context={
            "host": "http://localhost",
            "site_name": "Example Inc.",
            "token": "reset-token",
        },
        template_name_html="forgot_password.html",
        template_name_text="forgot_password.txt",
    )


@pytest.mark.asyncio
async def test_forgot_password_mocked_error(mocker):
    mocked_mail = mocker.patch("app.auth.routes.generate_email")

    async def create_rpc_error(*args, **kwargs):
        raise AioRpcError(
            code=StatusCode.NOT_FOUND,
            initial_metadata=Metadata(),
            trailing_metadata=Metadata(),
            details="user not found",
        )

    response = await _run_forgot_password_test(mocker, create_rpc_error)

    assert response.status_code == 202
    assert response.json() is None

    mocked_mail.assert_not_called()
