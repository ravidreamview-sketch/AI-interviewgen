"""Create the additive subscription database foundation."""

from sqlalchemy import inspect


VERSION = "0001"
NAME = "subscription_foundation"


def expected_tables():
    """Return the complete schema contract after this migration version."""
    from app.db_models import PaymentVerification, Subscription, SubscriptionPlan

    return (
        SubscriptionPlan.__table__,
        Subscription.__table__,
        PaymentVerification.__table__,
    )


def upgrade(connection):
    """Create subscription tables without reading or changing existing rows."""
    existing = set(inspect(connection).get_table_names())
    if "user_accounts" not in existing:
        raise RuntimeError("Required legacy table user_accounts is missing")

    from app.db_models import PaymentVerification, Subscription, SubscriptionPlan
    from app.database import Base

    Base.metadata.create_all(
        bind=connection,
        tables=[
            SubscriptionPlan.__table__,
            Subscription.__table__,
            PaymentVerification.__table__,
        ],
        checkfirst=True,
    )


def downgrade(connection):
    """Drop only empty Stage 1 tables; preserve all subscription/payment history."""
    from sqlalchemy import func, select
    from app.db_models import PaymentVerification, Subscription, SubscriptionPlan

    for model in (PaymentVerification, Subscription, SubscriptionPlan):
        table = model.__table__
        if table.name in inspect(connection).get_table_names():
            count = connection.execute(select(func.count()).select_from(table)).scalar_one()
            if count:
                raise RuntimeError(
                    f"Refusing downgrade: {table.name} contains {count} row(s)"
                )

    for model in (PaymentVerification, Subscription, SubscriptionPlan):
        model.__table__.drop(connection, checkfirst=True)
