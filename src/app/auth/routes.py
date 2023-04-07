import contextlib
from typing import Annotated

import grpc
from fastapi import APIRouter, Depends, status
from google.protobuf.json_format import MessageToDict
from starlette.background import BackgroundTasks

from app.auth import schemas
from app.auth.dependencies import CurrentActiveUser, Oauth2Form, Token, current_user
from app.auth.exceptions import BadRequest, IncorrectLoginCredentials
from app.auth.schemas import UserRead
from app.grpc import grpc_clients
from app.notifications.email import generate_email
from protos import auth_pb2

auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/users", tags=["users"])

CurrentUser = Annotated[UserRead, Depends(current_user)]


@auth_router.post("/token/login")
async def login(data: Oauth2Form) -> schemas.BearerResponse:
    async with grpc_clients["auth"] as client:
        try:
            request = auth_pb2.BearerTokenRequest(
                email=data.username,
                password=data.password,
            )
            response = await client("BearerToken", request)
            return MessageToDict(response, preserving_proto_field_name=True)
        except grpc.aio.AioRpcError as e:
            raise IncorrectLoginCredentials() from e


@auth_router.post("/token/logout")
async def logout(_: CurrentUser, token: Token) -> None:
    async with grpc_clients["auth"] as client:
        with contextlib.suppress(grpc.aio.AioRpcError):
            request = auth_pb2.Token(token=token)
            await client("RevokeBearerToken", request)


@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: schemas.UserCreate) -> schemas.UserRead:
    async with grpc_clients["auth"] as client:
        try:
            request = auth_pb2.RegisterRequest(**data.dict())
            response = await client("Register", request)
            return MessageToDict(
                response,
                preserving_proto_field_name=True,
                including_default_value_fields=True,
            )
        except grpc.aio.AioRpcError as e:
            raise BadRequest(e.details()) from e


@auth_router.post("/verify-request", status_code=status.HTTP_202_ACCEPTED)
async def verify_request(
    data: schemas.VerifyRequest,
    background_tasks: BackgroundTasks,
) -> None:
    async with grpc_clients["auth"] as client:
        with contextlib.suppress(grpc.aio.AioRpcError):
            request = auth_pb2.VerifyUserTokenRequest(email=data.email)
            response = await client("VerifyUserToken", request)

            print("Success: VerifyUserToken")
            print("-" * 60)
            print(response)

            async def send_mail(email, token):
                await generate_email(
                    to_address=email,
                    subject="Complete your registration",
                    template_context={
                        "token": token,
                        "host": "http://localhost",
                        "site_name": "Example Inc.",
                    },
                    template_name_text="verify_request.txt",
                    template_name_html="verify_request.html",
                )

            background_tasks.add_task(send_mail, response.email, response.token)


@auth_router.post("/verify")
async def verify(data: schemas.VerifyToken) -> schemas.UserRead:
    async with grpc_clients["auth"] as client:
        try:
            request = auth_pb2.Token(token=data.token)
            response = await client("VerifyUser", request)
            return MessageToDict(
                response,
                preserving_proto_field_name=True,
                including_default_value_fields=True,
            )
        except grpc.aio.AioRpcError as e:
            raise BadRequest(e.details()) from e


@auth_router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    data: schemas.ForgotPassword,
    background_tasks: BackgroundTasks,
) -> None:
    async with grpc_clients["auth"] as client:
        with contextlib.suppress(grpc.aio.AioRpcError):
            request = auth_pb2.ResetPasswordTokenRequest(email=data.email)
            response = await client("ResetPasswordToken", request)

            print("Success: ResetPasswordToken")
            print("-" * 60)
            print(response)

            async def send_mail(email, token):
                await generate_email(
                    to_address=email,
                    subject="Reset your password",
                    template_context={
                        "token": token,
                        "host": "http://localhost",
                        "site_name": "Example Inc.",
                    },
                    template_name_text="forgot_password.txt",
                    template_name_html="forgot_password.html",
                )

            background_tasks.add_task(send_mail, response.email, response.token)


@auth_router.post("/reset-password")
async def reset_password(data: schemas.ResetPassword) -> None:
    async with grpc_clients["auth"] as client:
        try:
            request = auth_pb2.ResetPasswordRequest(
                token=data.token,
                password=data.password,
            )
            await client("ResetPassword", request)
        except grpc.aio.AioRpcError as e:
            raise BadRequest(e.details()) from e


@user_router.get("/me")
async def get_current_user(user: CurrentActiveUser) -> schemas.UserRead:
    return user


@user_router.patch("/me")
async def update_current_user(
    data: schemas.UserUpdate,
    token: Token,
    _: CurrentActiveUser,
) -> schemas.UserRead:
    async with grpc_clients["auth"] as client:
        try:
            request = auth_pb2.UpdateUserRequest(
                token=token, **data.dict(exclude_unset=True)
            )
            response = await client("UpdateUser", request)
            return MessageToDict(
                response,
                preserving_proto_field_name=True,
                including_default_value_fields=True,
            )
        except grpc.aio.AioRpcError as e:
            raise BadRequest(e.details()) from e
