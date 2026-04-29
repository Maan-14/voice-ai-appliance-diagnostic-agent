from __future__ import annotations

from sqlalchemy import select

from app.models.customer import Customer
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    model = Customer

    async def get_by_phone(self, phone: str) -> Customer | None:
        stmt = select(Customer).where(Customer.phone == phone)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def upsert(
        self,
        *,
        phone: str,
        name: str | None = None,
        email: str | None = None,
        default_address: str | None = None,
        default_zip: str | None = None,
    ) -> Customer:
        """Find a customer by phone, or create one if none exists.

        Existing customers get their non-null fields *upgraded* with whatever
        new information was passed in (existing values win when the new value
        is None).
        """
        existing = await self.get_by_phone(phone)
        if existing is None:
            customer = Customer(
                phone=phone,
                name=name,
                email=email,
                default_address=default_address,
                default_zip=default_zip,
            )
            return await self.add(customer)

        if name and not existing.name:
            existing.name = name
        if email and not existing.email:
            existing.email = email
        if default_address and not existing.default_address:
            existing.default_address = default_address
        if default_zip and not existing.default_zip:
            existing.default_zip = default_zip
        await self.session.flush()
        return existing
