"""
admin_users.py -- Admin dashboard (Milestone 2, Step 6)

Two layers in one file:
  1. LOGIC  (no Streamlit): add_user, change_role, set_lock, delete_user, users_table, kpis, latest_log.
            Every rule lives here and raises AdminError with a message that is safe to show.
  2. PAGE   render_admin_page(...): the Streamlit page. It only calls the logic layer, so the rules can
            be tested without a browser (see test_part_b.py).

It works on the users / activity_log / lockouts tables created by app.py:
    users(id, username, email, password_hash, security_question, security_answer_hash, pwd_fp,
          role, locked, created_at, last_login, customer_id)
    activity_log(id, ts, actor, action, target, detail)
    lockouts(key, attempts, locked_until, last_try)

Rules enforced here (not just hidden in the UI):
  * only the Admin role may call anything (need(role, "users") at the top of the page)
  * an admin cannot delete, lock or change the role of their own account
  * the last remaining ACTIVE Admin can never be deleted, locked or demoted
  * deleting needs an explicit confirm
  * every admin action is written to activity_log (who, what, target, when); the page shows the latest 50
  * a password hash or recovery answer is never selected, returned or displayed
  * accounts created here get a random, unguessable recovery answer (the user can set a real one in Profile)
"""
import re
import time
import secrets
import datetime

from rbac import ROLES, ADMIN, need, AccessDenied, role_matrix, MATRIX_COLUMNS

# Milestone 1 validation rules
EMAIL_RE = re.compile(r"[A-Za-z]{2,}[A-Za-z0-9._%+-]*@[A-Za-z]{2,}[A-Za-z0-9-]*(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
USERNAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{2,29}")
# recovery answers older versions of the app stored for admin-made accounts: public in the notebook, so replaced
DEFAULT_RECOVERY_ANSWERS = ("admin-created", "admin-recovery-disabled")
DELETE_CONFIRM_SECONDS = 30


class AdminError(ValueError):
    """A rule was broken. The message is shown to the admin."""


def password_problems(p):
    out = []
    if len(p) < 8: out.append("at least 8 characters")
    if len(p) > 64: out.append("at most 64 characters")
    if not any(c.isupper() for c in p): out.append("an uppercase letter")
    if not any(c.islower() for c in p): out.append("a lowercase letter")
    if not any(c.isdigit() for c in p): out.append("a number")
    if not any(not c.isalnum() for c in p): out.append("a special symbol")
    return out


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ----------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------
def log_action(conn, actor_email, action, target="", detail=""):
    conn.execute("INSERT INTO activity_log(ts, actor, action, target, detail) VALUES (?,?,?,?,?)",
                 (_now(), actor_email, action, str(target), str(detail)[:500]))


def _target(conn, user_id):
    row = conn.execute("SELECT id, username, email, role, locked FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise AdminError("That user no longer exists.")
    return {"id": row[0], "username": row[1], "email": row[2], "role": row[3], "locked": int(row[4] or 0)}


def _no_self(actor, target, what):
    if target["id"] == actor["id"]:
        raise AdminError(f"You cannot {what} your own account.")


def _keep_an_admin(conn, target, what):
    """The last remaining ACTIVE Admin can never be deleted, locked or demoted."""
    if target["role"] == ADMIN:
        others = conn.execute("SELECT COUNT(*) FROM users WHERE role=? AND COALESCE(locked,0)=0 AND id<>?",
                              (ADMIN, target["id"])).fetchone()[0]
        if others == 0:
            raise AdminError(f"The last remaining active Admin cannot be {what}.")


def random_recovery_answer_hash(hash_fn):
    """A recovery answer nobody knows. Used for accounts the admin creates."""
    return hash_fn(secrets.token_urlsafe(32))


def clear_lockouts(conn, email):
    conn.execute("DELETE FROM lockouts WHERE key IN (?,?,?,?)",
                 tuple(f"{p}:{email}" for p in ("login", "otp", "sq", "admin")))


def fix_default_recovery_answers(conn, check_fn, hash_fn):
    """
    One-time clean-up for databases created by older versions: any account whose recovery answer is one of the
    constants that were written into the notebook gets a random answer and a blank question (security-question
    recovery is then switched off for it; the e-mail OTP route still works). Returns how many were fixed.
    """
    fixed = 0
    for uid, h in conn.execute("SELECT id, security_answer_hash FROM users").fetchall():
        if h and any(check_fn(c, h) for c in DEFAULT_RECOVERY_ANSWERS):
            conn.execute("UPDATE users SET security_question='', security_answer_hash=? WHERE id=?",
                         (random_recovery_answer_hash(hash_fn), uid))
            fixed += 1
    return fixed


# ----------------------------------------------------------------------------------------------
# read side
# ----------------------------------------------------------------------------------------------
def users_table(conn):
    """Rows for the users table. Never selects a password hash or a recovery answer."""
    rows = conn.execute("SELECT id, email, username, role, COALESCE(locked,0), created_at, last_login, customer_id "
                        "FROM users ORDER BY id").fetchall()
    return [{"id": r[0], "email": r[1], "username": r[2], "role": r[3], "status": "Locked" if r[4] else "Active",
             "created_at": r[5] or "", "last_login": r[6] or "", "customer_id": r[7]} for r in rows]


def kpis(conn):
    per_role = {r: 0 for r in ROLES}
    for role, n in conn.execute("SELECT role, COUNT(*) FROM users GROUP BY role"):
        per_role[role] = n
    return {"total": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
            "locked": conn.execute("SELECT COUNT(*) FROM users WHERE COALESCE(locked,0)=1").fetchone()[0],
            "per_role": per_role}


def latest_log(conn, limit=50):
    rows = conn.execute("SELECT ts, actor, action, target, detail FROM activity_log ORDER BY id DESC LIMIT ?",
                        (min(int(limit), 50),)).fetchall()
    return [dict(zip(("ts", "actor", "action", "target", "detail"), r)) for r in rows]


# ----------------------------------------------------------------------------------------------
# write side -- one function per admin action; `actor` = {"id": ..., "email": ...}
# ----------------------------------------------------------------------------------------------
def add_user(conn, actor, username, email, password, role, hash_fn, fingerprint_fn=None):
    username, email, role = (username or "").strip(), (email or "").strip().lower(), (role or "").strip()
    if not (username and email and password and role):
        raise AdminError("Username, email, temporary password and role are all required.")
    if not USERNAME_RE.fullmatch(username):
        raise AdminError("Username must be 3-30 characters (letters, numbers, space, . _ -).")
    if not EMAIL_RE.fullmatch(email):
        raise AdminError("Enter a valid email address (e.g. ab@cd.ef).")
    problems = password_problems(password)
    if problems:
        raise AdminError("Password needs " + ", ".join(problems) + ".")
    if role not in ROLES:
        raise AdminError("Unknown role.")
    if conn.execute("SELECT 1 FROM users WHERE lower(username)=lower(?)", (username,)).fetchone():
        raise AdminError("That username is already taken.")
    if conn.execute("SELECT 1 FROM users WHERE lower(email)=lower(?)", (email,)).fetchone():
        raise AdminError("That email is already registered.")
    fp = fingerprint_fn(password) if fingerprint_fn else None
    if fp and conn.execute("SELECT 1 FROM users WHERE pwd_fp=?", (fp,)).fetchone():
        raise AdminError("This password is already used by another account. Choose a different one.")
    # recovery question left blank + random answer: nobody can reset this account through the security question
    conn.execute("INSERT INTO users(username,email,password_hash,security_question,security_answer_hash,pwd_fp,role,locked,created_at) "
                 "VALUES (?,?,?,?,?,?,?,0,?)",
                 (username, email, hash_fn(password), "", random_recovery_answer_hash(hash_fn), fp, role, _now()))
    log_action(conn, actor["email"], "add_user", email, f"Created {role} account")
    return f"User {email} created as {role}."


def change_role(conn, actor, target_id, new_role):
    if new_role not in ROLES:
        raise AdminError("Unknown role.")
    t = _target(conn, target_id)
    _no_self(actor, t, "change the role of")
    if t["role"] == new_role:
        raise AdminError(f"{t['email']} already has the {new_role} role.")
    if new_role != ADMIN:
        _keep_an_admin(conn, t, "demoted")
    conn.execute("UPDATE users SET role=? WHERE id=?", (new_role, target_id))
    action = "promote_user" if ROLES.index(new_role) < ROLES.index(t["role"] if t["role"] in ROLES else ROLES[-1]) else "demote_user"
    log_action(conn, actor["email"], action, t["email"], f"{t['role']} -> {new_role}")
    return f"{t['email']} is now {new_role}."


def set_lock(conn, actor, target_id, locked):
    t = _target(conn, target_id)
    if locked:
        _no_self(actor, t, "lock")
        _keep_an_admin(conn, t, "locked")
    conn.execute("UPDATE users SET locked=? WHERE id=?", (1 if locked else 0, target_id))
    if not locked:
        clear_lockouts(conn, t["email"])           # also drop the temporary 30-second lock / attempt counters
    log_action(conn, actor["email"], "lock_user" if locked else "unlock_user", t["email"],
               "Account locked" if locked else "Account unlocked")
    return f"{t['email']} {'locked - their session stops working immediately' if locked else 'unlocked'}."


def delete_user(conn, actor, target_id, confirm=False):
    if not confirm:
        raise AdminError("Deleting a user needs confirmation.")
    t = _target(conn, target_id)
    _no_self(actor, t, "delete")
    _keep_an_admin(conn, t, "deleted")
    conn.execute("DELETE FROM users WHERE id=?", (target_id,))
    clear_lockouts(conn, t["email"])
    log_action(conn, actor["email"], "delete_user", t["email"], f"Deleted {t['role']} account")
    return f"{t['email']} was deleted."


# ----------------------------------------------------------------------------------------------
# the Streamlit page
# ----------------------------------------------------------------------------------------------
def render_admin_page(db, actor, hash_fn, fingerprint_fn=None):
    """
    db      : the app's context manager  `with db() as conn:`  (commits on exit)
    actor   : {"id": user id, "email": ..., "role": ...}   (read from the DATABASE, not the browser)
    hash_fn : app.hash_txt          fingerprint_fn : app.pwd_fp (keeps the "everyone has a different password" rule)
    """
    import streamlit as st
    import pandas as pd

    try:
        need(actor["role"], "users")                 # every route behind this page needs the "users" capability
    except AccessDenied as e:
        st.error(str(e))
        st.stop()

    st.subheader("Administrator dashboard")
    flash = st.session_state.pop("admin_flash", None)
    if flash:
        st.success(flash)

    with db() as c:
        users, stats, log = users_table(c), kpis(c), latest_log(c, 50)

    # ---- KPI cards
    cols = st.columns(2 + len(ROLES))
    cols[0].metric("Total users", stats["total"])
    cols[1].metric("Locked users", stats["locked"])
    for col, role in zip(cols[2:], ROLES):
        col.metric(role + "s", stats["per_role"][role])

    # ---- users table (no password data)
    st.markdown("#### Users")
    df = pd.DataFrame(users, columns=["email", "username", "role", "status", "created_at", "last_login"])
    st.dataframe(df, hide_index=True, width="stretch", height=min(420, 60 + 36 * max(len(df), 1)))

    def run(action, *args, **kw):
        """Run one admin action; show a broken rule as an error, a success as a message, then refresh."""
        try:
            with db() as c:
                msg = action(c, actor, *args, **kw)
        except AdminError as e:
            st.error(str(e))
            return False
        st.session_state["admin_flash"] = msg
        st.rerun()

    # ---- add user
    st.markdown("#### Add user")
    with st.form("admin_add_user"):
        a, b = st.columns(2)
        new_name = a.text_input("Username")
        new_mail = b.text_input("Email")
        new_pw = st.text_input("Temporary password", type="password")
        new_role = st.selectbox("Role", list(ROLES[1:]) + [ADMIN])
        st.caption("Same rules as sign-up: valid email, 8+ characters with upper case, lower case, number and special symbol.")
        add = st.form_submit_button("Create user", type="primary")
    if add:
        run(add_user, new_name, new_mail, new_pw, new_role, hash_fn, fingerprint_fn)

    # ---- manage one account
    st.markdown("#### Change role · lock · unlock · delete")
    others = [u for u in users if u["id"] != actor["id"]]
    if not others:
        st.info("There are no other accounts to manage.")
    else:
        labels = {f"{u['username'] or '-'} · {u['email']} ({u['role']}{', locked' if u['status'] == 'Locked' else ''})": u for u in others}
        target = labels[st.selectbox("Select account", list(labels))]
        st.caption("Your own account is not listed: you cannot change, lock or delete yourself.")

        r1, r2 = st.columns([3, 1])
        role_choice = r1.selectbox("New role", list(ROLES), index=ROLES.index(target["role"]) if target["role"] in ROLES else 0)
        r2.markdown("<div style='height:1.9rem'></div>", unsafe_allow_html=True)
        if r2.button("Save role", key="admin_save_role"):
            run(change_role, target["id"], role_choice)

        l1, l2 = st.columns(2)
        if l1.button("Lock selected user", key="admin_lock"):
            run(set_lock, target["id"], True)
        if l2.button("Unlock selected user", key="admin_unlock"):
            run(set_lock, target["id"], False)

        # two-step delete: first click arms it, second click (within 30 s, same user) deletes
        pending = st.session_state.get("admin_delete_pending")
        if pending and (pending[0] != target["id"] or time.time() - pending[1] > DELETE_CONFIRM_SECONDS):
            st.session_state.pop("admin_delete_pending", None)
            pending = None
        if st.button("Delete selected user", key="admin_delete"):
            st.session_state["admin_delete_pending"] = (target["id"], time.time())
            pending = st.session_state["admin_delete_pending"]
        if pending:
            st.warning(f"Permanently delete {target['email']}? This cannot be undone.")
            y, n = st.columns(2)
            if y.button("Yes, delete permanently", type="primary", key="admin_delete_yes"):
                st.session_state.pop("admin_delete_pending", None)
                run(delete_user, target["id"], confirm=True)
            if n.button("Cancel", key="admin_delete_no"):
                st.session_state.pop("admin_delete_pending", None)
                st.rerun()

    # ---- activity log
    st.markdown("#### Activity log · latest 50 actions")
    if log:
        st.dataframe(pd.DataFrame(log), hide_index=True, width="stretch", height=300)
    else:
        st.info("No admin actions recorded yet.")

    # ---- permission table
    st.markdown("#### Role permission matrix")
    st.table(pd.DataFrame(role_matrix(), columns=MATRIX_COLUMNS))
