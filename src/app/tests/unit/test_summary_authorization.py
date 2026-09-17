"""Unit coverage for authorize_summary_scope: delegated (caregiver/parent) access restored,
and every path bound to the specific appointment being requested."""
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException

from src.app.services.summary_authorization import authorize_summary_scope

PATIENT_ID = "patient-id"
REQUESTER_ID = "requester-id"
APPOINTMENT_ID = "appointment-id"


def row(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


def make_request(*, authenticated=True, clerk_id="clerk-x", is_internal_service=False, summary_ready=True):
    return SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(summary_ready=summary_ready)),
        state=SimpleNamespace(user={
            "is_authenticated": authenticated,
            "clerk_id": clerk_id,
            "is_internal_service": is_internal_service,
        }),
    )


def session_with(*rows):
    """A session whose execute() answers each sequential call with the next row in order -
    never a single shared return_value, which would let one query's mock silently satisfy
    another (e.g. the appointment-ownership check being answered by the identity mapping mock)."""
    return SimpleNamespace(execute=AsyncMock(side_effect=list(rows)))


class AuthorizeSummaryScopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_self_access_with_matching_appointment_is_allowed(self):
        request = make_request(clerk_id="clerk-patient")
        session = session_with(row(PATIENT_ID), row(APPOINTMENT_ID))
        await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(session.execute.await_count, 2)

    async def test_caregiver_with_accepted_non_revoked_grant_is_allowed(self):
        # Regression test for the live production break this PR exists to fix: a
        # caregiver-initiated summary request (a flow nodeapi already authorizes) must not
        # be rejected just because the requester isn't the patient themself.
        request = make_request(clerk_id="clerk-caregiver")
        session = session_with(
            row(REQUESTER_ID),  # identity mapping: caregiver's own users.id
            row(None),          # not a parent of the patient's child profile
            row(True),          # accepted, non-revoked shared_access row exists
            row(APPOINTMENT_ID),  # appointment belongs to the patient
        )
        await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(session.execute.await_count, 4)

    async def test_caregiver_with_pending_grant_is_rejected(self):
        request = make_request(clerk_id="clerk-caregiver")
        session = session_with(
            row(REQUESTER_ID),
            row(None),  # not a parent
            row(None),  # shared_access query filters out pending/non-accepted rows -> no match
        )
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 403)

    async def test_caregiver_with_accepted_but_revoked_grant_is_rejected(self):
        request = make_request(clerk_id="clerk-caregiver")
        session = session_with(
            row(REQUESTER_ID),
            row(None),  # not a parent
            row(None),  # shared_access query filters out access_revoked_at IS NOT NULL rows
        )
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 403)

    async def test_parent_of_child_profile_is_allowed(self):
        request = make_request(clerk_id="clerk-parent")
        session = session_with(
            row(REQUESTER_ID),
            row(True),  # patient is a child profile whose parent_user_id is the requester
            row(APPOINTMENT_ID),
        )
        await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(session.execute.await_count, 3)

    async def test_unrelated_user_is_rejected(self):
        request = make_request(clerk_id="clerk-stranger")
        session = session_with(
            row(REQUESTER_ID),
            row(None),
            row(None),
        )
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 403)

    async def test_unauthenticated_request_is_rejected(self):
        request = make_request(authenticated=False)
        session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("session must not be touched")))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 401)
        session.execute.assert_not_awaited()

    async def test_summary_unavailable_short_circuits_without_touching_session(self):
        request = make_request(summary_ready=False)
        session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("session must not be touched")))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 503)
        session.execute.assert_not_awaited()

    async def test_internal_service_without_patient_scope_allowed_only_when_appointment_matches(self):
        request = make_request(clerk_id=None, is_internal_service=True)
        session = session_with(row(APPOINTMENT_ID))
        await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(session.execute.await_count, 1)

    async def test_internal_service_appointment_belonging_to_different_patient_is_rejected(self):
        # The actual new safety property item 4 adds: a trusted-service credential alone no
        # longer authorizes an appointment that isn't the claimed patient's own.
        request = make_request(clerk_id=None, is_internal_service=True)
        session = session_with(row(None))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 403)

    async def test_matching_identity_with_mismatched_appointment_is_rejected(self):
        # Same property as above, on the non-internal-service path - proves the appointment
        # binding is unconditional rather than internal-service-only.
        request = make_request(clerk_id="clerk-patient")
        session = session_with(row(PATIENT_ID), row(None))
        with self.assertRaises(HTTPException) as error:
            await authorize_summary_scope(request, PATIENT_ID, session, APPOINTMENT_ID)
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
