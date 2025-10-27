import pymysql
from datetime import datetime, timezone
import bcrypt
import streamlit as st
import pandas as pd
from contextlib import contextmanager

# Konfiguration
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Xyz1343!!!",
    "database": "ticketsystemabkoo1",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

STATI = ["Neu", "In Bearbeitung", "Warten", "Gelöst", "Geschlossen"]
PRIO = ["Niedrig", "Normal", "Hoch", "Kritisch"]
CATS = ["Hardware", "Software", "Netzwerk", "Sonstiges"]

# Icons für bessere Übersicht
ICONS = {
    "Neu": "🔵", "In Bearbeitung": "🟡", "Warten": "🟠", "Gelöst": "🟢", "Geschlossen": "⚫",
    "Niedrig": "🟢", "Normal": "🟡", "Hoch": "🟠", "Kritisch": "🔴"
}

# ==================== Datenbank ====================
@contextmanager
def get_conn():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()

def query(sql, params=()):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall() if cur.description else cur.lastrowid

# ==================== User ====================
def login_user(username, password):
    users = query("SELECT * FROM users WHERE username=%s AND active=1", (username,))
    if users and bcrypt.checkpw(password.encode(), users[0]["password_hash"].encode()):
        return users[0]
    return None

def create_user(username, password, role="user"):
    hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    query("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)", (username, hash, role))

def list_users():
    return query("SELECT * FROM users WHERE active=1 ORDER BY username")

# ==================== Tickets ====================
def create_ticket(title, desc, cat, prio, user_id):
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    query("INSERT INTO tickets (title, description, category, status, priority, creator_id, created_at, updated_at) VALUES (%s,%s,%s,'Neu',%s,%s,%s,%s)",
          (title, desc, cat, prio, user_id, now, now))

def get_tickets(archived=False, search=""):
    sql = """
        SELECT t.*, u.username AS creator, a.username AS assignee
        FROM tickets t
        JOIN users u ON u.id = t.creator_id
        LEFT JOIN users a ON a.id = t.assignee_id
        WHERE t.archived = %s AND (t.title LIKE %s OR t.description LIKE %s)
        ORDER BY t.updated_at DESC
    """
    return query(sql, (archived, f"%{search}%", f"%{search}%"))

def update_ticket(tid, **fields):
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    sql = "UPDATE tickets SET " + ", ".join(f"{k}=%s" for k in fields) + " WHERE id=%s"
    query(sql, tuple(fields.values()) + (tid,))

# ==================== UI Komponenten ====================
def ticket_card(t):
    """Kompakte Ticket-Darstellung"""
    st.markdown(f"{ICONS.get(t['status'],'⚪')} {ICONS.get(t['priority'],'⚪')} **#{t['id']} {t['title']}**")
    st.caption(f"{t['category']} • {t.get('assignee') or 'Niemand'}")
    st.write((t['description'][:100] + "…") if len(t['description']) > 100 else t['description'])

def move_status(current, direction):
    """Status vor/zurück bewegen"""
    try:
        idx = STATI.index(current)
        return STATI[max(0, min(len(STATI)-1, idx + direction))]
    except:
        return current

# ==================== Seiten ====================
def page_login():
    st.title("🎫 Ticketsystem Login")
    with st.form("login"):
        user = st.text_input("Benutzername")
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Login"):
            u = login_user(user, pw)
            if u:
                st.session_state.update({"user_id": u["id"], "role": u["role"], "username": u["username"]})
                st.rerun()
            else:
                st.error("Falsche Zugangsdaten")

def page_kanban():
    st.header("🎫 Kanban Board")

    # Filter
    col1, col2 = st.columns([3, 1])
    search = col1.text_input("🔍 Suche", placeholder="Tickets durchsuchen...")
    show_arch = col2.checkbox("📦 Archiv")

    tickets = get_tickets(archived=show_arch, search=search)
    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_opts = [None] + [u["id"] for u in users]

    # Kanban Spalten
    cols = st.columns(len(STATI))
    for idx, status in enumerate(STATI):
        with cols[idx]:
            st.subheader(f"{ICONS[status]} {status}")
            status_tickets = [t for t in tickets if t["status"] == status]

            for t in status_tickets:
                with st.container(border=True):
                    ticket_card(t)

                    c1, c2, c3 = st.columns([1,1,2])

                    # Status Navigation
                    if c1.button("⬅️", key=f"l{t['id']}", help="Zurück"):
                        update_ticket(t["id"], status=move_status(status, -1))
                        st.rerun()
                    if c2.button("➡️", key=f"r{t['id']}", help="Vor"):
                        update_ticket(t["id"], status=move_status(status, 1))
                        st.rerun()

                    # Bearbeiter
                    curr = t.get("assignee_id") or None
                    idx = user_opts.index(curr) if curr in user_opts else 0
                    assignee = c3.selectbox(
                        "Bearbeiter", user_opts, idx,
                        format_func=lambda x: "—" if x is None else user_map.get(x, "?"),
                        key=f"a{t['id']}", label_visibility="collapsed"
                    )

                    # Speichern
                    if st.button("💾", key=f"s{t['id']}", use_container_width=True):
                        update_ticket(t["id"], assignee_id=assignee)
                        st.success("✅")
                        st.rerun()

def page_create():
    st.header("➕ Ticket erstellen")
    with st.form("create"):
        title = st.text_input("Titel")
        desc = st.text_area("Beschreibung", height=150)
        col1, col2 = st.columns(2)
        cat = col1.selectbox("Kategorie", CATS)
        prio = col2.selectbox("Priorität", PRIO, index=1)

        if st.form_submit_button("Erstellen"):
            if title and desc:
                create_ticket(title, desc, cat, prio, st.session_state.user_id)
                st.success("✅ Ticket erstellt!")
                st.rerun()
            else:
                st.error("Titel und Beschreibung erforderlich")

def page_admin():
    st.header("🔧 Admin")

    tickets = get_tickets(archived=st.checkbox("Archivierte"))
    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_opts = [None] + [u["id"] for u in users]

    for t in tickets:
        with st.expander(f"#{t['id']} {t['title']}"):
            st.write(t["description"])
            st.caption(f"Von: {t['creator']} → {t.get('assignee') or '—'}")

            c1, c2, c3, c4 = st.columns(4)
            status = c1.selectbox("Status", STATI, STATI.index(t["status"]), key=f"st{t['id']}")
            prio = c2.selectbox("Priorität", PRIO, PRIO.index(t["priority"]), key=f"pr{t['id']}")
            cat = c3.selectbox("Kategorie", CATS, CATS.index(t["category"]), key=f"ct{t['id']}")

            curr = t.get("assignee_id") or None
            idx = user_opts.index(curr) if curr in user_opts else 0
            assignee = c4.selectbox("Bearbeiter", user_opts, idx,
                                    format_func=lambda x: "—" if x is None else user_map.get(x, "?"),
                                    key=f"as{t['id']}")

            arch = st.checkbox("Archivieren", bool(t.get("archived")), key=f"ar{t['id']}")

            if st.button("Speichern", key=f"sv{t['id']}"):
                update_ticket(t["id"], status=status, priority=prio, category=cat,
                              assignee_id=assignee, archived=int(arch))
                st.success("✅")
                st.rerun()

def page_database():
    st.header("🗄️ Datenbank")

    tab1, tab2 = st.tabs(["Benutzer", "Tickets"])

    with tab1:
        st.dataframe(pd.DataFrame(list_users()), use_container_width=True)

        with st.form("new_user"):
            st.subheader("Neuer Benutzer")
            col1, col2, col3 = st.columns(3)
            u = col1.text_input("Username")
            p = col2.text_input("Passwort", type="password")
            r = col3.selectbox("Rolle", ["user", "admin"])

            if st.form_submit_button("Erstellen"):
                if u and p:
                    create_user(u, p, r)
                    st.success("✅ Benutzer erstellt")
                    st.rerun()

    with tab2:
        tickets = query("SELECT * FROM tickets ORDER BY updated_at DESC")
        st.dataframe(pd.DataFrame(tickets), use_container_width=True)

def page_profile():
    st.header("👤 Profil")
    st.write(f"**{st.session_state.username}** ({st.session_state.role})")
    if st.button("Logout"):
        for k in ["user_id", "role", "username"]:
            st.session_state.pop(k, None)
        st.rerun()

# ==================== Main ====================
def main():
    st.set_page_config(page_title="Ticketsystem", layout="wide", page_icon="🎫")

    if "user_id" not in st.session_state:
        page_login()
        return

    st.sidebar.title("🎫 Ticketsystem")
    st.sidebar.caption(f"Angemeldet: {st.session_state.username}")

    pages = {
        "Kanban": page_kanban,
        "Erstellen": page_create,
        "Profil": page_profile
    }

    if st.session_state.role == "admin":
        pages.update({"Admin": page_admin, "Datenbank": page_database})

    choice = st.sidebar.radio("Navigation", list(pages.keys()))
    pages[choice]()

if __name__ == "__main__":
    main()