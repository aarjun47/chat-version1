import os
import unittest
from unittest.mock import AsyncMock, patch


os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("MASTER_USERNAME", "master")
os.environ.setdefault("MASTER_PASSWORD", "password")

from fastapi import HTTPException

from app import crud
from app.routes import client as client_routes


class TenantIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_conversations_by_lead_scopes_by_client_id(self):
        fake_cursor = AsyncMock()
        fake_cursor.sort.return_value = fake_cursor
        fake_cursor.to_list = AsyncMock(return_value=[])

        with patch.object(crud.conversations_col, "find", return_value=fake_cursor) as find_mock:
            await crud.get_conversations_by_lead("client-123", "lead-456")

        find_mock.assert_called_once_with({
            "client_id": "client-123",
            "lead_id": "lead-456",
        })

    async def test_get_recent_messages_scopes_by_client_and_lead(self):
        fake_cursor = AsyncMock()
        fake_cursor.sort.return_value = fake_cursor
        fake_cursor.limit.return_value = fake_cursor
        fake_cursor.to_list = AsyncMock(return_value=[])

        with patch.object(crud.conversations_col, "find", return_value=fake_cursor) as find_mock:
            await crud.get_recent_messages("client-123", "lead-456", limit=6)

        find_mock.assert_called_once_with({
            "client_id": "client-123",
            "lead_id": "lead-456",
        })

    async def test_service_interest_normalization_is_consistent(self):
        self.assertEqual(crud.normalize_service_interest(" acca "), "ACCA")
        self.assertEqual(crud.normalize_service_interest(""), None)
        self.assertEqual(crud.normalize_service_interest(None), None)

    async def test_get_lead_detail_rejects_invalid_object_id(self):
        with self.assertRaises(HTTPException) as ctx:
            await client_routes.get_lead_detail("bad-id", {"client_id": "client-123"})

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.detail, "Invalid lead ID format")

    async def test_get_lead_detail_returns_404_for_other_tenant_lead(self):
        with patch.object(client_routes, "get_lead_by_id_for_client", AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as ctx:
                await client_routes.get_lead_detail("507f1f77bcf86cd799439011", {"client_id": "client-123"})

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertEqual(ctx.exception.detail, "Lead not found")

    async def test_get_appointments_uses_client_scoped_lead_map(self):
        appts = [{
            "id": "appt-1",
            "lead_id": "507f1f77bcf86cd799439011",
            "requested_time": "Monday 10am",
            "status": "pending",
            "created_at": None,
        }]
        leads_by_id = {
            "507f1f77bcf86cd799439011": {
                "id": "507f1f77bcf86cd799439011",
                "name": "Raj",
                "phone_number": "+91999",
            }
        }

        with patch.object(client_routes, "get_appointments_by_client", AsyncMock(return_value=appts)) as appts_mock:
            with patch.object(client_routes, "get_leads_by_ids_for_client", AsyncMock(return_value=leads_by_id)) as leads_mock:
                result = await client_routes.get_appointments({"client_id": "client-123"})

        appts_mock.assert_awaited_once_with("client-123")
        leads_mock.assert_awaited_once_with("client-123", ["507f1f77bcf86cd799439011"])
        self.assertEqual(result[0]["lead_name"], "Raj")
        self.assertEqual(result[0]["phone_number"], "+91999")


if __name__ == "__main__":
    unittest.main()
