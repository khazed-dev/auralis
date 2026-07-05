from app.providers.database import MockDatabaseProvider
from app.routes.checkout import generate_checkout_password
from app.services.auth import AuthService, UserCreate


async def test_generated_checkout_password_can_authenticate():
    database = MockDatabaseProvider()
    password = generate_checkout_password()
    auth = AuthService(database)

    await auth.create_user(UserCreate(
        email="checkout@example.com",
        password=password,
        name="Checkout Company",
    ))

    assert await auth.authenticate_user("checkout@example.com", password)
    assert await auth.authenticate_user("checkout@example.com", password + "x") is None

