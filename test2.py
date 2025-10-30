import pymysql
from datetime import datetime, timezone
import bcrypt
import streamlit as st
import pandas as pd
from contextlib import contextmanager
import os

# --------------------
# Konfiguration
# --------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "Xyz1343!!!"),  # Besser: aus .env Datei laden
    "database": os.getenv("DB_NAME", "ticketsystemabkoo1"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

STATI = ["Neu", "In Bearbeitung", "Warten auf Benutzer", "Gelöst", "Geschlossen"]
PRIO = ["Niedrig", "Normal", "Hoch", "Kritisch"]
CATS = ["Hardware", "Software", "Netzwerk", "Sonstiges"]

# Farben für Status und Priorität
STATUS_COLORS = {
    "Neu": "🔵",
    "In Bearbeitung": "🟡",
    "Warten auf Benutzer": "🟠",
    "Gelöst": "🟢",
    "Geschlossen": "⚫"
}

PRIO_COLORS = {
    "Niedrig": "🟢",
    "Normal": "🟡",
    "Hoch": "🟠",
    "Kritisch": "🔴"
}

# --------------------
# Datenbank Context Manager
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
# Hilfsfunktionen
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
    """Gibt den nächsten Status in der Reihenfolge zurück."""
    order = STATI
    try:
        i = order.index(s)
        return order[min(i + 1, len(order) - 1)]
    except ValueError:
        return s

def prev_status(s: str) -> str:
    """Gibt den vorherigen Status in der Reihenfolge zurück."""
    order = STATI
    try:
        i = order.index(s)
        return order[max(i - 1, 0)]
    except ValueError:
        return s

def format_datetime(dt_str):
    """Formatiert Datum/Zeit für bessere Lesbarkeit."""
    if not dt_str:
        return "—"
    try:
        dt = datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return str(dt_str)

# --------------------
# DB-Wrapper Funktionen
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
# User Management
# --------------------
def get_user_by_username(username: str):
    """Holt Benutzer aus DB anhand Username."""
    rows = query_fetchall(
        "SELECT id, username, role, password_hash, active FROM users WHERE username=%s",
        (username.strip(),)
    )
    if not rows or rows[0]["active"] != 1:
        return None
    return rows[0]

def login_user(username: str, password: str):
    """Authentifiziert Benutzer und gibt User-Dict zurück."""
    u = get_user_by_username(username.strip())
    if not u:
        return None
    if verify_pw_bcrypt(password, u["password_hash"]):
        return {"id": u["id"], "username": u["username"], "role": u["role"]}
    return None

def create_user(username: str, password: str, role: str = "user"):
    """Erstellt neuen Benutzer."""
    pw_hash = hash_pw_bcrypt(password)
    query_execute("INSERT INTO users (username, password_hash, role) VALUES (%s,%s,%s)",
                  (username, pw_hash, role))

def list_users():
    """Liste aller aktiven Benutzer."""
    return query_fetchall("SELECT id, username, role FROM users WHERE active=1 ORDER BY username")

def deactivate_user(user_id: int):
    """Deaktiviert einen Benutzer."""
    query_execute("UPDATE users SET active=0, deleted_at=NOW() WHERE id=%s", (user_id,))

# --------------------
# Ticket Management
# --------------------
def create_ticket(title, description, category, priority, creator_id):
    """Erstellt ein neues Ticket."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    query_execute(
        """INSERT INTO tickets
           (title, description, category, status, priority, creator_id, created_at, updated_at, archived)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0)""",
        (title, description, category, "Neu", priority, creator_id, now, now)
    )

def fetch_tickets(creator_id=None, archived=False, search_term=None, category=None, priority=None):
    """Holt Tickets mit optionalen Filtern."""
    params = []
    where = []

    if not archived:
        where.append("t.archived = 0")
    if creator_id is not None:
        where.append("t.creator_id = %s")
        params.append(creator_id)
    if search_term:
        where.append("(t.title LIKE %s OR t.description LIKE %s)")
        params.extend([f"%{search_term}%", f"%{search_term}%"])
    if category and category != "Alle":
        where.append("t.category = %s")
        params.append(category)
    if priority and priority != "Alle":
        where.append("t.priority = %s")
        params.append(priority)

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
    """Aktualisiert Ticket-Felder."""
    if not fields:
        return
    fields["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    set_clause = ", ".join(f"{k}=%s" for k in fields.keys())
    params = list(fields.values()) + [tid]
    query_execute(f"UPDATE tickets SET {set_clause} WHERE id=%s", tuple(params))

def get_ticket_stats():
    """Holt Statistiken über Tickets."""
    stats = query_fetchall("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Neu' THEN 1 ELSE 0 END) as neue,
            SUM(CASE WHEN status = 'In Bearbeitung' THEN 1 ELSE 0 END) as in_bearbeitung,
            SUM(CASE WHEN status = 'Gelöst' THEN 1 ELSE 0 END) as geloest,
            SUM(CASE WHEN archived = 1 THEN 1 ELSE 0 END) as archiviert
        FROM tickets
    """)
    return stats[0] if stats else {}

# --------------------
# UI Komponenten
# --------------------
def show_stats():
    """Zeigt Statistik-Dashboard."""
    stats = get_ticket_stats()
    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Gesamt", stats.get('total', 0))
    col2.metric("🔵 Neu", stats.get('neue', 0))
    col3.metric("🟡 In Bearbeitung", stats.get('in_bearbeitung', 0))
    col4.metric("🟢 Gelöst", stats.get('geloest', 0))
    col5.metric("📦 Archiviert", stats.get('archiviert', 0))
    st.divider()

def kanban_card(t):
    """Zeigt eine Ticket-Karte im Kanban-Stil."""
    status_icon = STATUS_COLORS.get(t.get('status', ''), '⚪')
    prio_icon = PRIO_COLORS.get(t.get('priority', ''), '⚪')

    st.markdown(f"{status_icon} {prio_icon} **#{t['id']} — {t['title']}**")
    st.caption(f"📁 {t.get('category','-')} • ⏰ {format_datetime(t.get('updated_at'))}")

    desc = t.get('description') or ''
    st.write(desc[:150] + ("…" if len(desc) > 150 else ""))

    st.caption(f"👤 {t.get('creator_name','?')} → 👨‍💼 {t.get('assignee_name','—') or 'Nicht zugewiesen'}")

# --------------------
# Seiten
# --------------------
def page_login():
    """Login-Seite."""
    st.title("🎫 Ticketsystem Login")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            st.subheader("Anmelden")
            u = st.text_input("Benutzername", placeholder="username")
            p = st.text_input("Passwort", type="password", placeholder="••••••••")

            if st.form_submit_button("🔐 Anmelden", use_container_width=True):
                user = login_user(u, p)
                if user:
                    st.session_state.update({
                        "user_id": user["id"],
                        "role": user["role"],
                        "username": user["username"]
                    })
                    st.success("✅ Erfolgreich angemeldet!")
                    st.rerun()
                else:
                    st.error("❌ Ungültige Zugangsdaten")

# ===== Kanban- und Admin-Helfer (drop-in) =====

def now_utc_str():
    """Einheitlicher Zeitstempel (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def get_user_map_and_ids():
    """Liefert (user_map, user_ids) für Assignee-Selectboxen."""
    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_ids = [None] + [u["id"] for u in users]
    return user_map, user_ids

def render_ticket_controls(t, user_map, user_ids, is_admin: bool):
    """Buttons (←/→), Assignee-Auswahl, Archiv-Checkbox + Speichern."""
    c1, c2, c3 = st.columns([1, 1, 2])

    with c1:
        if st.button("⬅️", key=f"left_{t['id']}", help="Vorheriger Status"):
            update_ticket(t["id"], status=prev_status(t["status"]), updated_at=now_utc_str())
            st.rerun()
    with c2:
        if st.button("➡️", key=f"right_{t['id']}", help="Nächster Status"):
            update_ticket(t["id"], status=next_status(t["status"]), updated_at=now_utc_str())
            st.rerun()

    # Assignee
    cur = t.get("assignee_id")
    a_index = 0 if cur in (None, 0) else (user_ids.index(cur) if cur in user_ids else 0)
    assignee = c3.selectbox(
        "Bearbeiter",
        user_ids, index=a_index,
        format_func=lambda v: "—" if v is None else user_map.get(v, "?"),
        key=f"as_{t['id']}",
        label_visibility="collapsed"
    )

    # Archiv (nur Admin)
    arch_val = bool(t.get("archived", 0))
    arch = st.checkbox("📦 Archivieren", value=arch_val, key=f"arch_{t['id']}") if is_admin else arch_val

    # Speichern
    if st.button("💾 Speichern", key=f"save_{t['id']}", use_container_width=True):
        fields = {"assignee_id": assignee, "updated_at": now_utc_str()}
        if is_admin:
            fields["archived"] = int(arch)
        update_ticket(t["id"], **fields)
        st.success("✅ Gespeichert")
        st.rerun()

def render_ticket_column(status_name: str, tickets: list[dict], user_map, user_ids, is_admin: bool):
    """Eine komplette Kanban-Spalte mit Überschrift und Karten."""
    status_icon = STATUS_COLORS.get(status_name, '⚪')
    col_tickets = [t for t in tickets if t.get("status") == status_name]
    st.subheader(f"{status_icon} {status_name} ({len(col_tickets)})")
    if not col_tickets:
        st.caption("—")
        return

    for t in col_tickets:
        with st.container(border=True):
            kanban_card(t)
            render_ticket_controls(t, user_map, user_ids, is_admin)

def page_kanban():
    """Kanban-Board für Tickets (aufgeräumt)."""
    st.header("🎫 Ticket Kanban-Board")

    show_stats()  # unverändert, zeigt die Metrics oben

    # Filter
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
    search = col1.text_input("🔍 Suche", placeholder="Ticket durchsuchen...")
    filter_cat = col2.selectbox("📁 Kategorie", ["Alle"] + CATS)
    filter_prio = col3.selectbox("⚠️ Priorität", ["Alle"] + PRIO)
    show_arch = col4.checkbox("📦 Archiv")

    is_admin = (st.session_state.get("role") == "admin")

    # Tickets mit Filtern holen
    tickets = fetch_tickets(
        archived=show_arch,
        search_term=search or None,
        category=(None if filter_cat == "Alle" else filter_cat),
        priority=(None if filter_prio == "Alle" else filter_prio),
    )
    if not tickets:
        st.info("ℹ️ Keine Tickets gefunden.")
        return

    # User-Mapping für Assignees
    user_map, user_ids = get_user_map_and_ids()

    # Spalten-Layout
    cols = st.columns(len(STATI))
    for idx, status_name in enumerate(STATI):
        with cols[idx]:
            render_ticket_column(status_name, tickets, user_map, user_ids, is_admin)


def page_create_ticket():
    """Ticket erstellen."""
    st.header("➕ Neues Ticket erstellen")

    with st.form("create_ticket_form"):
        title = st.text_input("📝 Titel", placeholder="Kurze Beschreibung des Problems")
        desc = st.text_area("📄 Beschreibung", height=200,
                            placeholder="Detaillierte Beschreibung des Problems...")

        col1, col2 = st.columns(2)
        cat = col1.selectbox("📁 Kategorie", CATS)
        prio = col2.selectbox("⚠️ Priorität", PRIO, index=1)

        if st.form_submit_button("✅ Ticket anlegen", use_container_width=True):
            if not title.strip() or not desc.strip():
                st.error("❌ Titel und Beschreibung dürfen nicht leer sein.")
            else:
                create_ticket(title.strip(), desc.strip(), cat, prio, st.session_state.user_id)
                st.success("✅ Ticket erfolgreich angelegt!")
                st.balloons()
                st.rerun()

def page_admin():
    """Admin-Bereich für Ticket-Verwaltung."""
    st.header("🔧 Admin: Tickets verwalten")

    show_arch = st.checkbox("📦 Archivierte anzeigen")
    tickets = fetch_tickets(archived=show_arch)

    if not tickets:
        st.info("ℹ️ Keine Tickets vorhanden")
        return

    users = list_users()
    user_map = {u["id"]: u["username"] for u in users}
    user_ids = [None] + [u["id"] for u in users]

    for t in tickets:
        with st.expander(f"#{t['id']} — {t['title']}", expanded=False):
            status_icon = STATUS_COLORS.get(t.get('status', ''), '⚪')
            prio_icon = PRIO_COLORS.get(t.get('priority', ''), '⚪')

            st.markdown(f"{status_icon} {prio_icon} **Ticket #{t['id']}**")
            st.caption(f"Erstellt: {format_datetime(t.get('created_at'))} | "
                       f"Aktualisiert: {format_datetime(t.get('updated_at'))}")
            st.write(t.get("description", ""))
            st.caption(f"Von: {t.get('creator_name','?')} → Bearbeiter: {t.get('assignee_name','-') or '-'}")

            st.divider()

            c1, c2, c3, c4 = st.columns(4)
            status = c1.selectbox("Status", STATI, index=safe_index(STATI, t.get("status")), key=f"st_{t['id']}")
            prio = c2.selectbox("Priorität", PRIO, index=safe_index(PRIO, t.get("priority"), 1), key=f"pr_{t['id']}")
            cat = c3.selectbox("Kategorie", CATS, index=safe_index(CATS, t.get("category")), key=f"ct_{t['id']}")

            current_assignee = t.get("assignee_id")
            assignee_index = 0 if current_assignee in (None, 0) else (user_ids.index(current_assignee) if current_assignee in user_ids else 0)
            assignee = c4.selectbox("Bearbeiter", user_ids, index=assignee_index,
                                    format_func=lambda v: "—" if v is None else user_map.get(v, "?"),
                                    key=f"as_adm_{t['id']}")

            arch = st.checkbox(f"📦 Archivieren", value=bool(t.get("archived", 0)), key=f"arch_adm_{t['id']}")

            if st.button(f"💾 Speichern", key=f"save_adm_{t['id']}", use_container_width=True):
                update_ticket(t["id"], status=status, priority=prio, category=cat,
                              assignee_id=assignee, archived=int(arch))
                st.success("✅ Gespeichert")
                st.rerun()

def page_database():
    """Datenbank-Verwaltung (Admin)."""
    st.header("🗄️ Datenbank (Admin)")
    tab1, tab2 = st.tabs(["👥 Benutzer", "🎫 Tickets"])

    with tab1:
        st.subheader("Aktive Benutzer")
        users = list_users()
        if users:
            df = pd.DataFrame(users)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Keine Benutzer vorhanden")

        st.divider()

        # Neuer Benutzer
        with st.form("new_user"):
            st.subheader("➕ Neuen Benutzer anlegen")
            col1, col2, col3 = st.columns(3)
            u = col1.text_input("Username")
            p = col2.text_input("Passwort", type="password")
            r = col3.selectbox("Rolle", ["user", "admin"])

            if st.form_submit_button("✅ Anlegen", use_container_width=True):
                if u and p:
                    create_user(u, p, r)
                    st.success("✅ Benutzer angelegt.")
                    st.rerun()
                else:
                    st.error("❌ Username und Passwort erforderlich.")

        st.divider()

        # Benutzer deaktivieren
        st.subheader("🗑️ Benutzer deaktivieren")
        if not users:
            st.info("Keine aktiven Benutzer vorhanden.")
        else:
            victim = st.selectbox("Benutzer auswählen", users, format_func=lambda x: x["username"])
            confirm = st.text_input("Zur Bestätigung Benutzernamen erneut eingeben")
            sure = st.checkbox("Ich bin sicher")

            is_self = ("user_id" in st.session_state) and (victim["id"] == st.session_state["user_id"])
            if is_self:
                st.warning("⚠️ Du kannst dich nicht selbst deaktivieren.")

            if st.button("🗑️ Benutzer deaktivieren",
                         disabled=is_self or not sure or confirm != victim["username"],
                         type="primary"):
                deactivate_user(victim["id"])
                st.success(f"✅ Benutzer '{victim['username']}' wurde deaktiviert.")
                st.rerun()

    with tab2:
        st.subheader("Alle Tickets")
        tickets = query_fetchall("SELECT * FROM tickets ORDER BY updated_at DESC")
        if tickets:
            df = pd.DataFrame(tickets)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("Keine Tickets vorhanden")

def page_profile():
    """Profil und Logout."""
    st.header("👤 Profil")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"""
        ### Angemeldet als
        
        **Benutzername:** {st.session_state.username}  
        **Rolle:** {st.session_state.role}
        
        """)

        if st.button("🚪 Logout", use_container_width=True, type="primary"):
            for k in ["user_id", "role", "username"]:
                st.session_state.pop(k, None)
            st.success("✅ Erfolgreich abgemeldet!")
            st.rerun()

# --------------------
# Hauptprogramm
# --------------------
# -------------------- #
# 🎯 App-Startpunkt
# -------------------- #
def app_start():
    """Initialisiert die Streamlit-App und verwaltet Navigation & Login."""
    setup_page()
    if not is_logged_in():
        show_login()
        return

    show_sidebar()
    route_to_selected_page()


# -------------------- #
# ⚙️ Setup & Utilities
# -------------------- #
def setup_page():
    """Seitenlayout & Stil."""
    # Hinweis: set_page_config darf nur einmal pro App-Lauf aufgerufen werden.
    st.set_page_config(page_title="Ticketsystem", layout="wide", page_icon="🎫")
    st.markdown(
        """
        <style>
        .stButton button { border-radius: 5px; }
        div[data-testid="stExpander"] { border: 1px solid #ddd; border-radius: 5px; }
        </style>
        """,
        unsafe_allow_html=True
    )


def is_logged_in() -> bool:
    """Prüft Loginstatus."""
    return "user_id" in st.session_state


def show_login():
    """Zeigt die Login-Seite."""
    page_login()


# -------------------- #
# 📚 Sidebar & Routing
# -------------------- #
def show_sidebar():
    """Zeigt Sidebar mit Navigation."""
    user = st.session_state.get("username", "Unbekannt")
    role = st.session_state.get("role", "user")

    st.sidebar.title("🎫 Ticketsystem")
    st.sidebar.markdown(f"**Angemeldet als:** {user} ({role})")
    st.sidebar.divider()


def route_to_selected_page():
    """Wählt passende Seite basierend auf Rolle und ruft sie auf."""
    role = st.session_state.get("role", "user")
    pages = get_pages(role)

    choice = st.sidebar.radio(
        "Navigation",
        list(pages.keys()),
        label_visibility="collapsed"
    )
    pages[choice]()  # Seite rendern


def get_pages(role: str) -> dict:
    """Erstellt das Navigationsmenü dynamisch."""
    pages = {
        "🎫 Kanban-Board": page_kanban,
        "➕ Ticket erstellen": page_create_ticket,
        "👤 Profil": page_profile,
    }
    if role == "admin":
        pages["🔧 Admin"] = page_admin
        pages["🗄️ Datenbank"] = page_database
    return pages


# -------------------- #
# 🚀 Main
# -------------------- #
if __name__ == "__main__":
    app_start()
