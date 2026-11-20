from __future__ import annotations

import os
from pathlib import Path

import pytest

from otpauthentication.service import AppError, OTPService


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("OTPAUTHENTICATION_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OTPAUTHENTICATION_SKIP_DSM_AUTH", "1")
    return tmp_path


def _svc(user: str) -> OTPService:
    os.environ["OTPAUTHENTICATION_SKIP_DSM_AUTH"] = "1"
    svc = OTPService({}, dev_user=user)
    svc.set_enabled(True)
    return svc


def test_owner_share_and_grantee_restrictions(env):
    alice = _svc("alice")
    alice.setup_pin("123456", "123456")
    unlock = alice.unlock("123456")
    created = alice.create_entry(
        unlock["unlock_token"],
        {"issuer": "Example", "account": "alice@example.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="r1",
    )
    entry_id = created["id"]

    bob = _svc("bob")
    bob.setup_pin("654321", "654321")
    bob_unlock = bob.unlock("654321")

    # Bob not ready? he is ready. Alice shares.
    alice.share_add(unlock["unlock_token"], entry_id, "bob")
    shared = bob.list_entries(bob_unlock["unlock_token"], scope="shared")
    assert len(shared["items"]) == 1
    codes = bob.codes(bob_unlock["unlock_token"], [entry_id])
    assert codes["items"][0]["code"]

    with pytest.raises(AppError):
        bob.delete_entry(bob_unlock["unlock_token"], entry_id)
    with pytest.raises(AppError):
        bob.reveal_secret(bob_unlock["unlock_token"], entry_id, "654321")
    with pytest.raises(AppError):
        bob.export_plain(bob_unlock["unlock_token"], "any-dsm-pass", [entry_id])

    alice.share_remove(unlock["unlock_token"], entry_id, alice.share_list(unlock["unlock_token"], entry_id)["items"][0]["id"])
    shared2 = bob.list_entries(bob_unlock["unlock_token"], scope="shared")
    assert shared2["items"] == []


def test_share_to_user_without_app_setup_or_pin(env):
    """S1: share works when recipient never opened the app / has no PIN."""
    owner = _svc("nas")
    owner.setup_pin("", "")
    unlock = owner.open_nopin()
    entry_id = owner.create_entry(
        unlock["unlock_token"],
        {"issuer": "ShareMe", "account": "a@x.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="share-nopin-1",
    )["id"]

    info = owner.resolve_recipient(unlock["unlock_token"], "khoa")
    assert info["ready"] is True

    owner.share_add(unlock["unlock_token"], entry_id, "khoa")
    shares = owner.share_list(unlock["unlock_token"], entry_id)
    assert any(s["username"].lower() == "khoa" for s in shares["items"])

    # Recipient opens with no PIN (pin_disabled set by share_add).
    khoa = _svc("khoa")
    st = khoa.pin_status()
    assert st["pin_set"] is False
    assert st["pin_disabled"] is True
    khoa_u = khoa.open_nopin()
    shared = khoa.list_entries(khoa_u["unlock_token"], scope="shared")
    assert any(i["id"] == entry_id for i in shared["items"])
    codes = khoa.codes(khoa_u["unlock_token"], [entry_id])
    assert codes["items"][0]["code"]


def test_batch_delete_entries(env):
    alice = _svc("alice")
    alice.setup_pin("123456", "123456")
    unlock = alice.unlock("123456")
    ids = []
    for i in range(3):
        created = alice.create_entry(
            unlock["unlock_token"],
            {
                "issuer": f"Batch{i}",
                "account": f"a{i}@example.com",
                "secret": "JBSWY3DPEHPK3PXP",
            },
            request_id=f"bd{i}",
        )
        ids.append(created["id"])

    bob = _svc("bob")
    bob.setup_pin("654321", "654321")
    bob_unlock = bob.unlock("654321")
    bob_entry = bob.create_entry(
        bob_unlock["unlock_token"],
        {"issuer": "BobOnly", "account": "bob@example.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="bob1",
    )["id"]

    result = alice.delete_entries(unlock["unlock_token"], [ids[0], ids[0], ids[1], bob_entry, 999999])
    assert result["deleted_count"] == 2
    assert result["failed_count"] == 2
    assert result["shares_removed"] == 0
    ok_ids = {r["id"] for r in result["results"] if r["ok"]}
    assert ok_ids == {ids[0], ids[1]}
    fail_ids = {r["id"] for r in result["results"] if not r["ok"]}
    assert fail_ids == {bob_entry, 999999}

    listed = alice.list_entries(unlock["unlock_token"])
    assert [it["id"] for it in listed["items"]] == [ids[2]]

    single = alice.delete_entry(unlock["unlock_token"], ids[2])
    assert single["deleted"] is True
    listed2 = alice.list_entries(unlock["unlock_token"])
    assert listed2["items"] == []

    with pytest.raises(AppError) as empty:
        alice.delete_entries(unlock["unlock_token"], [])
    assert empty.value.code == "invalid"


def test_pin_lockout_and_export_import(env):
    svc = _svc("carol")
    svc.setup_pin("111111", "111111")
    for _ in range(5):
        with pytest.raises(AppError):
            svc.unlock("000000")
    with pytest.raises(AppError) as ei:
        svc.unlock("111111")
    assert ei.value.code == "cooldown"

    # Bypass cooldown for remaining test by resetting attempts through new service after clearing cooldown in DB
    with svc.db.txn() as conn:
        conn.execute("UPDATE pin_attempts SET failures=0, cooldown_until=0")
    unlock = svc.unlock("111111")
    svc.create_entry(
        unlock["unlock_token"],
        {"uri": "otpauth://totp/Demo:user?secret=JBSWY3DPEHPK3PXP&issuer=Demo"},
        request_id="c1",
    )
    with pytest.raises(AppError) as empty_pw:
        svc.export_encrypted(unlock["unlock_token"], "any-dsm-pass", "")
    assert empty_pw.value.code == "password_required"

    # No minimum length / complexity on export encryption password
    short_enc = svc.export_encrypted(unlock["unlock_token"], "any-dsm-pass", "123456")
    assert short_enc["format"] == "otp-backup-v1"

    enc = svc.export_encrypted(unlock["unlock_token"], "any-dsm-pass", "backup-pass")
    assert enc["format"] == "otp-backup-v1"
    page = svc.list_entries(unlock["unlock_token"], scope="all", offset=0, limit=1)
    assert "total" in page
    assert page["total"] >= 1
    assert len(page["items"]) == 1
    preview = svc.import_preview(unlock["unlock_token"], __import__("json").dumps(enc), "backup-pass")
    result = svc.import_confirm(unlock["unlock_token"], preview["preview_token"], request_id="imp1")
    assert result["skipped"] >= 1

    # issuer+account duplicate → override replaces secret/params
    preview2 = svc.import_preview(
        unlock["unlock_token"],
        "otpauth://totp/Demo:user?secret=GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ&issuer=Demo",
    )
    assert preview2["items"][0]["status"] == "duplicate"
    overridden = svc.import_confirm(
        unlock["unlock_token"],
        preview2["preview_token"],
        request_id="imp2",
        decisions=["override"],
    )
    assert overridden["overridden"] == 1
    assert overridden["added"] == 0

    with pytest.raises(AppError) as bad_json:
        svc.import_preview(unlock["unlock_token"], "{not-json", "")
    assert bad_json.value.code == "invalid_backup"

    with pytest.raises(AppError) as bad_pw:
        svc.import_preview(unlock["unlock_token"], __import__("json").dumps(enc), "wrong-pass")
    assert bad_pw.value.code == "invalid_backup"

    with pytest.raises(AppError) as bad_uri:
        svc.import_preview(unlock["unlock_token"], "otpauth://hotp/Bad:user?secret=AAAA", "")
    assert bad_uri.value.code == "invalid_otpauth"

def test_status_reports_stopped(env, monkeypatch):
    monkeypatch.delenv("OTPAUTHENTICATION_SKIP_DSM_AUTH", raising=False)
    svc = OTPService({}, dev_user="dave")
    svc.set_enabled(False)
    st = svc.pin_status()
    assert st["package_stopped"] is True
    assert st["enabled"] is False
    svc.set_enabled(True)
    # without skip auth, identity still works via environ HTTP header set by dev_user
    monkeypatch.setenv("OTPAUTHENTICATION_SKIP_DSM_AUTH", "1")
    svc2 = OTPService({}, dev_user="dave")
    svc2.set_enabled(True)
    st2 = svc2.pin_status()
    assert st2["enabled"] is True


def test_empty_new_pin_disables_and_list_all(env):
    frank = _svc("frank")
    frank.setup_pin("123456", "123456")
    unlock = frank.unlock("123456")
    created = frank.create_entry(
        unlock["unlock_token"],
        {"issuer": "Keep", "account": "frank@example.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="f1",
    )
    entry_id = created["id"]

    with pytest.raises(AppError) as bad:
        frank.change_pin(unlock["unlock_token"], "123456", "12", "12")
    assert bad.value.code == "invalid_pin_format"

    disabled = frank.change_pin(unlock["unlock_token"], "123456", "", "")
    assert disabled["unlock_token"]
    st = frank.pin_status()
    assert st["pin_set"] is False
    assert st["pin_disabled"] is True
    listed = frank.list_entries(disabled["unlock_token"], scope="all")
    assert len(listed["items"]) == 1
    assert listed["items"][0]["id"] == entry_id

    gina = _svc("gina")
    opened = gina.setup_pin("", "")
    assert opened["unlock_token"]
    st2 = gina.pin_status()
    assert st2["pin_set"] is False
    assert st2["pin_disabled"] is True

    gina.setup_pin("654321", "654321")
    bob_u = gina.unlock("654321")
    frank_u = frank.open_nopin()
    frank.share_add(frank_u["unlock_token"], entry_id, "gina")
    combined = gina.list_entries(bob_u["unlock_token"], scope="all")
    assert any(i["id"] == entry_id and i["is_shared"] for i in combined["items"])
    shared_only = gina.list_entries(bob_u["unlock_token"], scope="shared")
    assert any(i["id"] == entry_id for i in shared_only["items"])


def test_recover_keep_entries_remove_and_reset(env, monkeypatch):
    monkeypatch.setenv("OTPAUTHENTICATION_DEV_PASSWORD", "dsm-pass")
    svc = _svc("erin")
    svc.setup_pin("123456", "123456")
    unlock = svc.unlock("123456")
    created = svc.create_entry(
        unlock["unlock_token"],
        {"issuer": "KeepMe", "account": "erin@example.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="w1",
    )
    assert created["id"]
    entry_id = created["id"]

    with pytest.raises(AppError) as bad:
        svc.recover_verify("wrong")
    assert bad.value.code == "invalid_password"

    verified = svc.recover_verify("dsm-pass")
    assert verified["recovery_token"]
    removed = svc.recover_pin(verified["recovery_token"], "remove")
    assert removed["unlock_token"]
    st = svc.pin_status()
    assert st["pin_set"] is False
    assert st["pin_disabled"] is True
    listed = svc.list_entries(removed["unlock_token"])
    assert len(listed["items"]) == 1
    assert listed["items"][0]["id"] == entry_id
    assert listed["items"][0]["issuer"] == "KeepMe"

    # Re-open without PIN after remove; entries still present
    again = svc.open_nopin()
    assert again["unlock_token"]
    listed2 = svc.list_entries(again["unlock_token"])
    assert len(listed2["items"]) == 1
    assert listed2["items"][0]["id"] == entry_id

    # Set a PIN again, then reset path — entries survive
    svc.setup_pin("654321", "654321")
    st2 = svc.pin_status()
    assert st2["pin_set"] is True
    assert st2["pin_disabled"] is False
    tok = svc.recover_verify("dsm-pass")["recovery_token"]
    reset = svc.recover_pin(tok, "reset")
    assert reset["need_setup"] is True
    st3 = svc.pin_status()
    assert st3["pin_set"] is False
    assert st3["pin_disabled"] is False
    with pytest.raises(AppError):
        svc.open_nopin()

    svc.setup_pin("111222", "111222")
    unlock3 = svc.unlock("111222")
    listed3 = svc.list_entries(unlock3["unlock_token"])
    assert len(listed3["items"]) == 1
    assert listed3["items"][0]["id"] == entry_id
    assert listed3["items"][0]["issuer"] == "KeepMe"


def test_delete_entries_batch(env):
    owner = _svc("dave")
    owner.setup_pin("123456", "123456")
    unlock = owner.unlock("123456")
    ids = []
    for i in range(5):
        created = owner.create_entry(
            unlock["unlock_token"],
            {
                "issuer": f"Batch{i}",
                "account": f"dave{i}@example.com",
                "secret": "JBSWY3DPEHPK3PXP",
            },
            request_id=f"batch-{i}",
        )
        ids.append(created["id"])

    other = _svc("erin")
    other.setup_pin("654321", "654321")
    other_unlock = other.unlock("654321")
    foreign = other.create_entry(
        other_unlock["unlock_token"],
        {"issuer": "Other", "account": "erin@example.com", "secret": "JBSWY3DPEHPK3PXP"},
        request_id="foreign-1",
    )["id"]

    # Soft-fail foreign + missing; delete owned in one txn
    result = owner.delete_entries(unlock["unlock_token"], ids[:3] + [foreign, 999999, ids[0]])
    assert result["deleted_count"] == 3
    assert result["failed_count"] == 2
    assert result["shares_removed"] == 0
    ok_ids = {r["id"] for r in result["results"] if r["ok"]}
    assert ok_ids == set(ids[:3])

    listed = owner.list_entries(unlock["unlock_token"])
    remaining = {item["id"] for item in listed["items"]}
    assert remaining == set(ids[3:])

    # Single-id path still raises for non-owner
    with pytest.raises(AppError):
        other.delete_entry(other_unlock["unlock_token"], ids[3])

    # Empty / oversize
    with pytest.raises(AppError) as empty:
        owner.delete_entries(unlock["unlock_token"], [])
    assert empty.value.code == "invalid"
    with pytest.raises(AppError) as too_many:
        owner.delete_entries(unlock["unlock_token"], list(range(1, 202)))
    assert too_many.value.code == "too_many"
