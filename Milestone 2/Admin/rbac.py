"""
rbac.py -- Role-Based Access Control  (Milestone 2, Step 5)

Single source of truth for "who may open which page" and "who may do which action".

    ROLE_MENU : {role: set(page ids)}          pages a role may open
    ROLE_CAPS : {role: set(capability names)}  actions a role may perform

Functions used by app.py
    menu_for(role)                 -> list of pages for the sidebar (only what the role may open)
    can_page(role, page)           -> True / False
    can_do(role, capability)       -> True / False
    need(role, capability)         -> raises AccessDenied ("403") when the role lacks the capability
    require_page(role, page)       -> raises AccessDenied ("403") when a page is opened that the role may not see
    owner_filter(role, customer_id, column)
                                   -> (sql_fragment, params) that limits a Customer to their own rows

Enforcement happens on the server side of Streamlit: app.py reads the role from the DATABASE on every
rerun (never from the browser) and calls these functions before it builds a page or runs an action.
"""
import re

# ----------------------------------------------------------------------------------------------
# Roles (users.role stores exactly these strings)
# ----------------------------------------------------------------------------------------------
ADMIN, OPS, BROKER, AUDITOR, CUSTOMER = "Admin", "Operations Manager", "Freight Broker", "Auditor", "Customer"
ROLES = (ADMIN, OPS, BROKER, AUDITOR, CUSTOMER)

# every page of the app, in sidebar order
ALL_PAGES = ["Dashboard", "Copilot", "Route", "Quotes", "Carriers", "Weather", "Margin", "Customs", "Admin", "Profile"]

# ----------------------------------------------------------------------------------------------
# ROLE_MENU -- page access matrix of the Milestone 2 document. Profile is open to every signed-in user
# (see can_page), so everybody can change their own username and password.
# ----------------------------------------------------------------------------------------------
ROLE_MENU = {
    ADMIN:    {"Dashboard", "Copilot", "Route", "Quotes", "Carriers", "Weather", "Margin", "Customs", "Admin"},
    OPS:      {"Dashboard", "Copilot", "Route", "Carriers", "Weather", "Customs"},
    BROKER:   {"Dashboard", "Copilot", "Quotes", "Carriers", "Margin"},
    AUDITOR:  {"Dashboard", "Copilot", "Route", "Quotes", "Carriers", "Weather", "Margin", "Customs"},
    CUSTOMER: {"Dashboard", "Copilot", "Quotes"},
}

# ----------------------------------------------------------------------------------------------
# ROLE_CAPS -- capabilities (actions). Admin may do everything (see can_do).
#   users          open the Admin dashboard and manage users and roles
#   quotes_create  create a quote for any customer       quotes_create_own  create a quote for your own account
#   agents_run     run the agents / agent cycle          reroute            re-route a vessel
#   storms_inject  inject a test storm                   customs_edit       attach / edit customs documents
# ----------------------------------------------------------------------------------------------
ROLE_CAPS = {
    ADMIN:    {"users", "quotes_create", "agents_run", "storms_inject", "reroute", "customs_edit"},
    OPS:      {"agents_run", "reroute"},          # runs logistics; no users, no storms
    BROKER:   {"quotes_create"},                  # sells and prices; no storms, no customs edits
    AUDITOR:  set(),                              # read-only everywhere
    CUSTOMER: {"quotes_create_own"},              # own account only
}

# permission table for the README and the Admin dashboard
MATRIX_COLUMNS = ["Role", "Copilot", "Route", "Quotes", "Carriers", "Weather", "Margin", "Customs", "Run agents", "Users"]


def role_matrix():
    """Built from ROLE_MENU / ROLE_CAPS, so the table can never disagree with what is enforced."""
    pages = ["Copilot", "Route", "Quotes", "Carriers", "Weather", "Margin", "Customs"]
    mark = lambda ok: "✓" if ok else "✗"
    return [(r, *[mark(can_page(r, p)) for p in pages], mark(can_do(r, "agents_run")),
             mark(can_do(r, "users") and can_page(r, "Admin"))) for r in ROLES]


def matrix_markdown():
    rows = ["| " + " | ".join(MATRIX_COLUMNS) + " |", "|" + "---|" * len(MATRIX_COLUMNS)]
    rows += ["| " + " | ".join(r) + " |" for r in role_matrix()]
    return "\n".join(rows)


# ----------------------------------------------------------------------------------------------
# permission checks
# ----------------------------------------------------------------------------------------------
class AccessDenied(PermissionError):
    """Raised for every 403. The message is safe to show to the user."""


def can_page(role, page):
    """May this role open this page?  Unknown / missing role -> no access (fail closed)."""
    return page == "Profile" and role in ROLES or page in ROLE_MENU.get(role, set())


def can_do(role, capability):
    """May this role perform this action?  Admin may do everything; unknown role -> nothing."""
    return role == ADMIN or capability in ROLE_CAPS.get(role, set())


def menu_for(role):
    """Pages for the sidebar: only what this role may open, in sidebar order."""
    return [p for p in ALL_PAGES if can_page(role, p)]


def need(role, capability):
    """Raise AccessDenied (403) when the role lacks the capability. Returns True otherwise."""
    if not can_do(role, capability):
        raise AccessDenied(f"403 - the {role or 'unknown'} role is not allowed to do '{capability}'.")
    return True


def require_page(role, page):
    """Raise AccessDenied (403) when the role may not open the page (e.g. a hand-typed or stale page name)."""
    if not can_page(role, page):
        raise AccessDenied(f"403 - the {role or 'unknown'} role cannot open the '{page}' page.")
    return True


# ----------------------------------------------------------------------------------------------
# Customer scoping -- a Customer sees only their own quotes / shipments
# ----------------------------------------------------------------------------------------------
_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def is_scoped(role):
    return role == CUSTOMER


def owner_filter(role, customer_id, column="customer_id"):
    """
    Returns (sql_fragment, params) to append to a WHERE clause.
        staff roles                      -> ("", ())
        Customer                         -> (" AND customer_id = ?", (their customer_id,))
        Customer without a customer_id   -> (" AND 1 = 0", ())      (fail closed: they see nothing)

        frag, args = owner_filter(role, customer_id, "q.customer_id")
        sql = "SELECT ... FROM freight_quotes q WHERE q.status = ?" + frag
        rows = query(sql, ("Approved", *args))
    """
    if not _COLUMN.match(column):
        raise ValueError("invalid column name")
    if not is_scoped(role):
        return "", ()
    if not customer_id:
        return " AND 1 = 0", ()
    return f" AND {column} = ?", (customer_id,)


def shipment_filter(role, customer_id):
    """Shipments belong to a customer through their quotes (freight_quotes.shipment_id)."""
    if not is_scoped(role):
        return "", ()
    if not customer_id:
        return " AND 1 = 0", ()
    return " AND shipment_id IN (SELECT shipment_id FROM freight_quotes WHERE customer_id = ?)", (customer_id,)
