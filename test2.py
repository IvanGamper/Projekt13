import pymysql
from datetime import datetime, timezone
import bcrypt
import streamlit as st
import pandas as pd
from contextlib import contextmanager


# --------------------uu
# Konfiguration: hier die DB-Zugangsdaten anpassen
# --------------------
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Xyz1343!!!",
    "database": "ticketsystemabkoo1",
    "charset": "utf8mb4",
    # Cursor als Dict liefert Zeilen als Dictionaries statt Tuples -> einfacher im Code
    "cursorclass": pymysql.cursors.DictCursor,
    # autocommit False ist sicherer, wir committen explizit
    "autocommit": False,
}

STATI = ["Neu", "In Bearbeitung", "Warten auf Benutzer", "Gelöst", "Geschlossen"]
PRIO = ["Niedrig", "Normal", "Hoch", "Kritisch"]
CATS = ["Hardware", "Software", "Netzwerk", "Sonstiges"]

# --------------------
# Einfacher DB-Context-Manager
# --------------------
@contextmanager
def get_conn():
    """Verwende get_conn() als Kontextmanager, um Commit/Rollback automatisch zu handhaben."""
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# --------------------
# Hilfsfunktionen: Hashen, sichere Indizes etc.
# --------------------
def hash_pw_bcrypt(password: str) -> str:
    """Erzeugt bcrypt-Hash (als String)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_pw_bcrypt(password: str, stored_hash: str) -> bool:
    """Überprüft Passwort gegen gespeicherten bcrypt-Hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except Exception:
        return False


def safe_index(options, value, default=0):
    """Hilfsfunktion für Selectbox-Index: verhindert Absturz, wenn Wert fehlt."""
    try:
        return options.index(value)
    except Exception:
        return default

def next_status(s: str) -> str:
    order = STATI
    try:
        i = order.index(s)
        return order[min(i + 1, len(order) - 1)]
    except ValueError:
        return s


def prev_status(s: str) -> str:
    order = STATI
    try:
        i = order.index(s)
        return order[max(i - 1, 0)]
    except ValueError:
        return s




# --------------------
# DB-Wrapper: Query und einfache Abfragen
# --------------------
def query_fetchall(sql: str, params: tuple = ()):
    """Führt SELECT-Query aus und liefert Liste von Dicts zurück."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def query_execute(sql: str, params: tuple = ()):
    """Führt INSERT/UPDATE/DELETE aus. Gibt lastrowid zurück (oder 0)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return getattr(cur, "lastrowid", 0) or 0

# --------------------
# Auth / Users
# --------------------
def get_user_by_username(username: str):
    rows = query_fetchall(
        "SELECT id, username, role, password_hash, active FROM users WHERE username=%s",
        (username.strip(),)
    )
    if not rows:
        return None
    user = rows[0]
    if user["active"] != 1:
        return None
    return user

def login_user(username: str, password: str):
    u = get_user_by_username(username.strip())
    if not u:
        return None
    # Wir erwarten bcrypt-Hashes in der DB.
    if verify_pw_bcrypt(password, u["password_hash"]):
        return {"id": u["id"], "username": u["username"], "role": u["role"]}
    # Falls ein alter SHA256-Hash vorhanden wäre, könnte man hier migrieren.
    return None


def create_user(username: str, password: str, role: str = "user"):
    pw_hash = hash_pw_bcrypt(password)
    query_execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", (username, pw_hash, role))


def list_users():
    return query_fetchall("SELECT id, username, role FROM users WHERE active=1 ORDER BY username")

def deactivate_user(user_id:int):
    query_execute("UPDATE users SET active=0, deleted_at=NOW() WHERE id=%s", (user_id,))




# --------------------
# Tickets: Erstellen, Lesen, Aktualisieren
# --------------------
def create_ticket(title, description, category, priority, creator_id):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    query_execute(
        """INSERT INTO tickets
           (title, description, category, status, priority, creator_id, created_at, updated_at, archived)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
        (title, description, category, "Neu", priority, creator_id, now, now)
    )


def fetch_tickets(creator_id=None, archived=False):
    params = []
    where = []
    if not archived:
        where.append("t.archived = 0")
    if creator_id is not None:
        where.append("t.creator_id = %s")
        params.append(creator_id)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
       SELECT t.*, u.username AS creator_name, a.username AS assignee_name
       FROM tickets t
       JOIN users u ON u.id = t.creator_id
       LEFT JOIN users a ON a.id = t.assignee_id
       {where_sql}
       ORDER BY t.updated_at DESC
   """
    return query_fetchall(sql, tuple(params))


def update_ticket(tid, **fields):
    if not fields:
        return
    # updated_at setzen wir serverseitig auf UTC-String
    fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=%s" for k in fields.keys())
    params = list(fields.values()) + [tid]
    query_execute(f"UPDATE tickets SET {set_clause} WHERE id=%s", tuple(params))


# --------------------
# UI Hilfe: Anzeigen eines Tickets
# --------------------
def show_ticket(t):
    st.markdown(f"### #{t['id']} — {t['title']}")
    st.caption(f"{t.get('category','-')} | {t.get('priority','-')} | {t.get('status','-')}")
    st.write(t.get("description",""))
    st.caption(f"Von: {t.get('creator_name','?')}  •  Bearbeiter: {t.get('assignee_name','-') or '-'}")
    st.markdown("---")

def kanban_card(t):
    st.markdown(f"**#{t['id']} — {t['title']}**")
    st.caption(f"{t.get('category','-')} • {t.get('priority','-')}")
    st.write((t.get('description') or '')[:220] + ("…" if len(t.get('description') or '') > 220 else ""))
    st.caption(f"Von: {t.get('creator_name','?')} • Bearbeiter: {t.get('assignee_name','—')}")



# --------------------
# Seiten (Login, Erstellen, Meine Tickets, Admin, DB)
# --------------------
def page_login():
    st.sidebar.subheader("Anmelden")
    u = st.sidebar.text_input("Benutzername")
    p = st.sidebar.text_input("Passwort", type="password")
    if st.sidebar.button("Login"):
        user = login_user(u, p)
        if user:
            st.session_state.update({"user_id": user["id"], "role": user["role"], "username": user["username"]})
            st.rerun()
        else:
            st.sidebar.error("Ungültige Zugangsdaten")


def page_my_tickets():
    st.header("Tickets (Kanban)")
    ctop1, ctop2 = st.columns([1,1])
    show_arch = ctop1.checkbox("Archivierte anzeigen")
    is_admin = (st.session_state.get("role") == "admin")

    # alle (nicht)archivierten Tickets holen
    tickets = fetch_tickets(archived=show_arch)
    if not tickets:
        st.info("Keine Tickets gefunden.")
        return

    # Assignee-Auswahl (für Karte)
    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_ids = [None] + [u["id"] for u in users]

    # Tickets je Status gruppieren
    cols = st.columns(len(STATI))
    for idx, status_name in enumerate(STATI):
        with cols[idx]:
            st.subheader(status_name)
            col_tickets = [t for t in tickets if (t.get("status") == status_name)]
            if not col_tickets:
                st.caption("—")
            for t in col_tickets:
                with st.container(border=True):
                    # Karte
                    kanban_card(t)

                    # Navigations- & Edit-Controls
                    c1, c2, c3 = st.columns([1, 1, 2])

                    # ← / → Status wechseln
                    with c1:
                        if st.button("←", key=f"left_{t['id']}", help="Vorheriger Status"):
                            update_ticket(t["id"], status=prev_status(t["status"]))
                            st.rerun()
                    with c2:
                        if st.button("→", key=f"right_{t['id']}", help="Nächster Status"):
                            update_ticket(t["id"], status=next_status(t["status"]))
                            st.rerun()

                    # Bearbeiter setzen
                    cur = t.get("assignee_id")
                    a_index = 0 if cur in (None, 0) else (user_ids.index(cur) if cur in user_ids else 0)
                    assignee = c3.selectbox(
                        f"Bearbeiter #{t['id']}",
                        user_ids, index=a_index,
                        format_func=lambda v: "—" if v is None else user_map.get(v, "?"),
                        key=f"as_{t['id']}"
                    )

                    # Archiv nur für Admin
                    if is_admin:
                        arch = st.checkbox(
                            f"Archivieren #{t['id']}",
                            value=bool(t.get("archived", 0)),
                            key=f"arch_{t['id']}"
                        )
                    else:
                        st.checkbox(
                            f"Archiviert (nur Admin) #{t['id']}",
                            value=bool(t.get("archived", 0)),
                            key=f"arch_ro_{t['id']}",
                            disabled=True
                        )
                        arch = bool(t.get("archived", 0))

                    # Speichern-Button
                    if st.button(f"Speichern #{t['id']}", key=f"save_{t['id']}"):
                        fields = {"assignee_id": assignee}

                        if is_admin:
                            fields["archived"] = int(arch)
                        update_ticket(t["id"], **fields)
                        st.success("Gespeichert")
                        st.rerun()



def page_create_ticket():
    st.header("Ticket erstellen")
    title = st.text_input("Titel")
    desc = st.text_area("Beschreibung", height=150)
    cat = st.selectbox("Kategorie", CATS)
    prio = st.selectbox("Priorität", PRIO, index=1)
    if st.button("Anlegen"):
        if not title.strip() or not desc.strip():
            st.error("Titel und Beschreibung dürfen nicht leer sein.")
        else:
            create_ticket(title.strip(), desc.strip(), cat, prio, st.session_state.user_id)
            st.success("Ticket angelegt.")
            st.rerun()


def page_admin():
    st.header("Admin: Tickets verwalten")
    show_arch = st.checkbox("Archivierte anzeigen")
    tickets = fetch_tickets(archived=show_arch)
    if not tickets:
        st.info("Keine Tickets")
        return


    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_ids = [None] + [u["id"] for u in users]


    for t in tickets:
        show_ticket(t)
        c1, c2, c3, c4 = st.columns(4)
        status = c1.selectbox(f"Status #{t['id']}", STATI, index=safe_index(STATI, t.get("status")))
        prio = c2.selectbox(f"Priorität #{t['id']}", PRIO, index=safe_index(PRIO, t.get("priority"), 1))
        cat = c3.selectbox(f"Kategorie #{t['id']}", CATS, index=safe_index(CATS, t.get("category")))
        # Assignee: 0 => kein Bearbeiter
        current_assignee = t.get("assignee_id")
        assignee_index = 0 if current_assignee in (None, 0) else (user_ids.index(current_assignee) if current_assignee in user_ids else 0)
        assignee = c4.selectbox(f"Bearbeiter #{t['id']}", user_ids, index=assignee_index,
                                format_func=lambda v: "—" if v is None else user_map.get(v, "?"))
        arch = st.checkbox(f"Archivieren #{t['id']}", value=bool(t.get("archived", 0)))


        if st.button(f"Speichern #{t['id']}"):
            update_ticket(t["id"], status=status, priority=prio, category=cat,
                          assignee_id=assignee, archived=int(arch))
            st.success("Speichert...")
            st.rerun()


def page_database():
    st.header("Datenbank (Admin)")
    tab1, tab2 = st.tabs(["Users", "Tickets"])


    with tab1:
        users = list_users()
        st.dataframe(pd.DataFrame(users), use_container_width=True)


        with st.form("new_user"):
            st.subheader("Neuen Benutzer anlegen")
            u = st.text_input("Username")
            p = st.text_input("Passwort", type="password")
            r = st.selectbox("Rolle", ["user", "admin"])
            if st.form_submit_button("Anlegen"):
                if u and p:
                    create_user(u, p, r)
                    st.success("Benutzer angelegt.")
                    st.rerun()
                else:
                    st.error("Username und Passwort erforderlich.")
        st.subheader("Benutzer deaktivieren")
    if not users:
        st.info("Keine aktiven Benutzer vorhanden.")
    else:
        victim = st.selectbox("Benutzer auswählen", users, format_func=lambda x: x["username"])
        confirm = st.text_input("Zur Bestätigung Benutzernamen erneut eingeben")
        sure = st.checkbox("Ich bin sicher")

        # nicht sich selbst deaktivieren
        is_self = ("user_id" in st.session_state) and (victim["id"] == st.session_state["user_id"])
        if is_self:
            st.warning("Du kannst dich nicht selbst deaktivieren.")

        if st.button("🗑️ Benutzer deaktivieren", disabled=is_self or not sure or confirm != victim["username"]):
            deactivate_user(victim["id"])
            st.success(f"Benutzer '{victim['username']}' wurde deaktiviert.")
            st.rerun()



        with tab2:
                tickets = query_fetchall("SELECT * FROM tickets ORDER BY updated_at DESC")
                st.dataframe(pd.DataFrame(tickets), use_container_width=True)


def page_profile():
    st.header("Profil")
    st.write(f"**{st.session_state.username}** ({st.session_state.role})")
    if st.button("Logout"):
        for k in ["user_id", "role", "username"]:
            st.session_state.pop(k, None)
        st.rerun()


# --------------------
# Hauptprogramm / Navigation
# --------------------
def main():
    st.set_page_config(page_title="Ticketsystem (Lernversion)", layout="wide")
    st.sidebar.title("Ticketsystem")


    if "user_id" not in st.session_state:
        page_login()
        return


    pages = ["Meine Tickets", "Ticket erstellen"]
    if st.session_state.role == "admin":
        pages.extend(["Admin", "Datenbank"])
    pages.append("Profil / Logout")


    choice = st.sidebar.radio("Navigation", pages)
    if choice == "Meine Tickets":
        page_my_tickets()
    elif choice == "Ticket erstellen":
        page_create_ticket()
    elif choice == "Admin":
        if st.session_state.role == "admin":
            page_admin()
        else:
            st.error("Kein Zugriff")
    elif choice == "Datenbank":
        if st.session_state.role == "admin":
            page_database()
        else:
            st.error("Kein Zugriff")
    else:
        page_profile()


if __name__ == "__main__":
    main()
