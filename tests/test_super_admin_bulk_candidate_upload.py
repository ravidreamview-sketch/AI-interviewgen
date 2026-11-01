import io
import unittest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import openpyxl

from api.index import app
from app.database import SessionLocal, init_db
from app.db_models import UserAccount, UserInvitation, AuditLog
from app.security import hash_password, create_access_token


class TestSuperAdminBulkCandidateUpload(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)

        with SessionLocal() as db:
            # Ensure super admin exists
            admin = db.query(UserAccount).filter(UserAccount.email == "test_bulk_admin@example.com").first()
            if not admin:
                admin = UserAccount(
                    email="test_bulk_admin@example.com",
                    password_hash=hash_password("SuperAdminPass123!"),
                    role="super_admin",
                    plan_tier="enterprise",
                    is_active=True
                )
                db.add(admin)
                db.commit()
                db.refresh(admin)
            cls.admin_id = admin.id

            # Ensure an existing registered user exists for duplicate testing
            reg_user = db.query(UserAccount).filter(UserAccount.email == "existing_reg_user@example.com").first()
            if not reg_user:
                reg_user = UserAccount(
                    email="existing_reg_user@example.com",
                    password_hash=hash_password("UserPass123!"),
                    role="candidate",
                    plan_tier="free",
                    is_active=True
                )
                db.add(reg_user)
                db.commit()

            # Ensure an existing pending invitation exists
            prior_inv = db.query(UserInvitation).filter(UserInvitation.email == "prior_active_invite@example.com").first()
            if not prior_inv:
                prior_inv = UserInvitation(
                    email="prior_active_invite@example.com",
                    role="candidate",
                    plan_tier="free",
                    token_hash="sample_hash_prior_invite_12345",
                    invited_by_user_id=admin.id,
                    invited_by_email=admin.email,
                    created_at=datetime.now(timezone.utc),
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                    is_revoked=False
                )
                db.add(prior_inv)
                db.commit()

        cls.admin_token = create_access_token({
            "sub": cls.admin_id,
            "email": "test_bulk_admin@example.com",
            "role": "super_admin"
        })
        cls.auth_headers = {
            "Authorization": f"Bearer {cls.admin_token}",
            "X-Requested-With": "XMLHttpRequest"
        }

    def setUp(self):
        """Ensure clean state for test-specific emails before each test."""
        with SessionLocal() as db:
            test_emails = [
                "bulk_alpha_cand@example.com",
                "bulk_beta_cand@example.com",
                "bulk_gamma_excel@example.com",
                "bulk_delta_excel@example.com",
                "repeat_cand@example.com",
                "fresh_unique_cand@example.com",
                "single_compat_candidate@example.com"
            ]
            db.query(UserInvitation).filter(UserInvitation.email.in_(test_emails)).delete(synchronize_session=False)
            db.commit()

    def test_01_bulk_upload_csv_success(self):
        """Test bulk uploading a CSV file with valid candidates."""
        csv_content = (
            "Name,Email Address,Plan\n"
            "Candidate Alpha,bulk_alpha_cand@example.com,pro\n"
            "Candidate Beta,bulk_beta_cand@example.com,free\n"
        )
        files = {
            "file": ("candidates.csv", csv_content.encode("utf-8"), "text/csv")
        }
        data = {
            "role": "candidate",
            "plan_tier": "free"
        }

        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files, data=data)
        self.assertEqual(res.status_code, 200, res.text)
        res_data = res.json()

        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["total_records"], 2)
        self.assertEqual(res_data["processed_count"], 2)
        self.assertEqual(res_data["skipped_count"], 0)

        # Verify database records
        with SessionLocal() as db:
            inv_alpha = db.query(UserInvitation).filter(UserInvitation.email == "bulk_alpha_cand@example.com").first()
            self.assertIsNotNone(inv_alpha)
            self.assertEqual(inv_alpha.role, "candidate")
            self.assertEqual(inv_alpha.plan_tier, "pro")
            self.assertFalse(inv_alpha.is_revoked)

            inv_beta = db.query(UserInvitation).filter(UserInvitation.email == "bulk_beta_cand@example.com").first()
            self.assertIsNotNone(inv_beta)
            self.assertEqual(inv_beta.plan_tier, "free")

    def test_02_bulk_upload_xlsx_success(self):
        """Test bulk uploading an Excel (.xlsx) file with valid candidates."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Batch Candidates"
        ws.append(["Candidate Name", "Email", "Role", "Plan"])
        ws.append(["Excel Gamma", "bulk_gamma_excel@example.com", "candidate", "enterprise"])
        ws.append(["Excel Delta", "bulk_delta_excel@example.com", "candidate", "pro"])

        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        files = {
            "file": ("candidates.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        }
        data = {
            "role": "candidate",
            "plan_tier": "free"
        }

        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files, data=data)
        self.assertEqual(res.status_code, 200, res.text)
        res_data = res.json()

        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["processed_count"], 2)

        with SessionLocal() as db:
            inv_gamma = db.query(UserInvitation).filter(UserInvitation.email == "bulk_gamma_excel@example.com").first()
            self.assertIsNotNone(inv_gamma)
            self.assertEqual(inv_gamma.plan_tier, "enterprise")

    def test_03_bulk_upload_prevents_duplicate_within_file(self):
        """Test deduplication when the same email is repeated within the file."""
        csv_content = (
            "Name,Email\n"
            "First Entry,repeat_cand@example.com\n"
            "Duplicate Entry,repeat_cand@example.com\n"
        )
        files = {
            "file": ("duplicate_in_file.csv", csv_content.encode("utf-8"), "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()

        self.assertEqual(res_data["processed_count"], 1)
        self.assertEqual(res_data["skipped_count"], 1)
        self.assertIn("Duplicate entry within uploaded file", res_data["details"]["skipped"][0]["reason"])

    def test_04_bulk_upload_prevents_duplicate_registered_user(self):
        """Test skipping emails that belong to existing registered users."""
        csv_content = (
            "Name,Email\n"
            "Existing User,existing_reg_user@example.com\n"
            "Fresh User,fresh_unique_cand@example.com\n"
        )
        files = {
            "file": ("existing_user.csv", csv_content.encode("utf-8"), "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()

        self.assertEqual(res_data["processed_count"], 1)
        self.assertEqual(res_data["skipped_count"], 1)
        self.assertIn("Already registered", res_data["details"]["skipped"][0]["reason"])

    def test_05_bulk_upload_prevents_duplicate_active_invitation(self):
        """Test skipping emails that already have an active unexpired invitation."""
        csv_content = (
            "Name,Email\n"
            "Prior Invite User,prior_active_invite@example.com\n"
        )
        files = {
            "file": ("prior_invite.csv", csv_content.encode("utf-8"), "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()

        self.assertEqual(res_data["processed_count"], 0)
        self.assertEqual(res_data["skipped_count"], 1)
        self.assertIn("Active unexpired pending invitation", res_data["details"]["skipped"][0]["reason"])

    def test_06_bulk_upload_invalid_email_format(self):
        """Test skipping rows with invalid email formats."""
        csv_content = (
            "Name,Email\n"
            "Bad Email User,not-an-email-at-all\n"
        )
        files = {
            "file": ("bad_email.csv", csv_content.encode("utf-8"), "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()

        self.assertEqual(res_data["processed_count"], 0)
        self.assertEqual(res_data["skipped_count"], 1)
        self.assertIn("Invalid email address format", res_data["details"]["skipped"][0]["reason"])

    def test_07_bulk_upload_unsupported_file_type(self):
        """Test rejecting unsupported file extensions like .pdf or .txt."""
        files = {
            "file": ("candidates.pdf", b"%PDF-1.4...", "application/pdf")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported file format", res.json()["detail"])

    def test_08_bulk_upload_empty_file(self):
        """Test rejecting empty uploaded files."""
        files = {
            "file": ("empty.csv", b"", "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", headers=self.auth_headers, files=files)
        self.assertEqual(res.status_code, 400)
        self.assertIn("empty", res.json()["detail"].lower())

    def test_09_single_user_invitation_remains_functional(self):
        """Verify backward compatibility: single invitation endpoint POST /api/admin/invitations works unchanged."""
        payload = {
            "email": "single_compat_candidate@example.com",
            "role": "candidate",
            "plan_tier": "free"
        }
        res = self.client.post("/api/admin/invitations", headers=self.auth_headers, json=payload)
        self.assertEqual(res.status_code, 201, res.text)
        data = res.json()
        self.assertTrue(data["success"])
        self.assertIn("single_compat_candidate@example.com", data["message"])

    def test_10_unauthorized_access_rejected(self):
        """Verify that requests without valid admin credentials are rejected with 401."""
        csv_content = "Name,Email\nTest,unauth@example.com\n"
        files = {
            "file": ("test.csv", csv_content.encode("utf-8"), "text/csv")
        }
        res = self.client.post("/api/admin/invitations/bulk", files=files)
        self.assertIn(res.status_code, [401, 403])


if __name__ == "__main__":
    unittest.main()
