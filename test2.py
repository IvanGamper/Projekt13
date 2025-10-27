import streamlit as st
import sqlite3
from datetime import datetime

# --- 1. Datenbank-Teil ---

DATABASE_NAME = "ticketsystem_lernversion.db"

def get_db_connection():
    """Stellt eine Verbindung zur SQLite-Datenbank her."""
    conn = sqlite3.connect(DATABASE_NAME)
    # Erlaubt den Zugriff auf Spalten per Namen (z.B. row["username"])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Erstellt die Datenbanktabellen, falls sie noch nicht existieren."""
    conn = get_db_connection()
    c = conn.cursor()

    # Tabelle für Benutzer
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL, -- WICHTIG: Kein Hashing, nur für Lernzwecke!
            role TEXT NOT NULL DEFAULT 'user' -- 'user' oder 'admin'
        )
    """)

    # Tabelle für Tickets
    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Neu',
            priority TEXT NOT NULL DEFAULT 'Mittel',
            creator_id INTEGER NOT NULL,
            assignee_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (creator_id) REFERENCES users(id),
            FOREIGN KEY (assignee_id) REFERENCES users(id)
        )
    """)

    # Beispiel-Benutzer hinzufügen (falls die Tabelle leer ist)
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", ('admin', 'admin', 'admin'))
    c.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", ('user', 'user', 'user'))

    conn.commit()
    conn.close()

def get_user_by_credentials(username, password):
    """Sucht einen Benutzer anhand von Benutzername und Passwort."""
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
    conn.close()
    return user

def get_all_users():
    """Gibt eine Liste aller Benutzer zurück."""
    conn = get_db_connection()
    users = conn.execute("SELECT id, username FROM users ORDER BY username").fetchall()
    conn.close()
    return users

def create_ticket(title, description, category, priority, creator_id):
    """Fügt ein neues Ticket in die Datenbank ein."""
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        INSERT INTO tickets (title, description, category, priority, creator_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (title, description, category, priority, creator_id, now, now))
    conn.commit()
    conn.close()

def get_my_tickets(user_id):
    """Holt alle Tickets, die von einem bestimmten Benutzer erstellt wurden."""
    conn = get_db_connection()
    tickets = conn.execute("""
        SELECT t.*, u_creator.username AS creator_name, u_assignee.username AS assignee_name
        FROM tickets t
        JOIN users u_creator ON t.creator_id = u_creator.id
        LEFT JOIN users u_assignee ON t.assignee_id = u_assignee.id
        WHERE t.creator_id = ?
        ORDER BY t.updated_at DESC
    """, (user_id,)).fetchall()
    conn.close()
    return tickets

def get_all_tickets():
    """Holt alle Tickets aus der Datenbank."""
    conn = get_db_connection()
    tickets = conn.execute("""
        SELECT t.*, u_creator.username AS creator_name, u_assignee.username AS assignee_name
        FROM tickets t
        JOIN users u_creator ON t.creator_id = u_creator.id
        LEFT JOIN users u_assignee ON t.assignee_id = u_assignee.id
        ORDER BY t.updated_at DESC
    """).fetchall()
    conn.close()
    return tickets

def update_ticket(ticket_id, status, priority, assignee_id):
    """Aktualisiert ein bestehendes Ticket."""
    conn = get_db_connection()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("""
        UPDATE tickets
        SET status = ?, priority = ?, assignee_id = ?, updated_at = ?
        WHERE id = ?
    """, (status, priority, assignee_id, now, ticket_id))
    conn.commit()
    conn.close()

# --- 2. Streamlit App-Teil ---

# --- Initialisierung ---
# Stellt sicher, dass die DB und Tabellen existieren, bevor die App startet
init_db()

# --- Konstanten für die UI ---
STATI = ["Neu", "In Bearbeitung", "Gelöst"]
PRIORITIES = ["Niedrig", "Mittel", "Hoch"]
CATEGORIES = ["Hardware", "Software", "Netzwerk"]

# --- UI-Funktionen für Login & Navigation ---
def show_login():
    """Zeigt das Login-Formular in der Sidebar an."""
    st.sidebar.subheader("Login")
    username = st.sidebar.text_input("Benutzername")
    password = st.sidebar.text_input("Passwort", type="password")
    if st.sidebar.button("Anmelden"):
        # Datenbankfunktion aufrufen, um Benutzer zu prüfen
        user = get_user_by_credentials(username, password)
        if user:
            # Benutzerinformationen im Session State speichern
            st.session_state["user_id"] = user["id"]
            st.session_state["username"] = user["username"]
            st.session_state["role"] = user["role"]
            st.rerun() # Seite neu laden, um App-Ansicht zu zeigen
        else:
            st.sidebar.error("Falsche Anmeldedaten")

def show_navbar():
    """Zeigt die Navigation in der Sidebar für eingeloggte Benutzer an."""
    st.sidebar.subheader(f'Angemeldet als {st.session_state["username"]}')

    # Seitenliste, Admin-Seite nur für Admins
    pages = ["Meine Tickets", "Ticket erstellen"]
    if st.session_state["role"] == "admin":
        pages.append("Admin")

    # Seitenauswahl
    page = st.sidebar.radio("Navigation", pages)

    # Logout-Button
    if st.sidebar.button("Logout"):
        # Session State leeren
        for key in ["user_id", "username", "role"]:
            st.session_state.pop(key, None)
        st.rerun() # Seite neu laden, um Login-Ansicht zu zeigen

    return page

# --- UI-Funktionen für die einzelnen Seiten ---
def page_my_tickets():
    """Zeigt die Tickets des angemeldeten Benutzers an."""
    st.header("Meine Tickets")
    my_tickets = get_my_tickets(st.session_state["user_id"])

    if not my_tickets:
        st.info("Du hast noch keine Tickets erstellt.")
        return

    # Jedes Ticket in einem eigenen Container anzeigen
    for ticket in my_tickets:
        with st.container(border=True):
            st.subheader(f'#{ticket["id"]}: {ticket["title"]}')
            st.write(ticket["description"])
            st.caption(f'Status: {ticket["status"]} | Priorität: {ticket["priority"]} | Kategorie: {ticket["category"]}')
            assignee = ticket["assignee_name"] or "Nicht zugewiesen"
            st.caption(f'Erstellt von: {ticket["creator_name"]} | Bearbeiter: {assignee}')

def page_create_ticket():
    """Zeigt ein Formular zum Erstellen eines neuen Tickets."""
    st.header("Neues Ticket erstellen")
    with st.form("create_form"):
        title = st.text_input("Titel")
        description = st.text_area("Beschreibung")
        category = st.selectbox("Kategorie", CATEGORIES)
        priority = st.selectbox("Priorität", PRIORITIES, index=1)

        submitted = st.form_submit_button("Ticket erstellen")
        if submitted:
            if title and description:
                create_ticket(title, description, category, priority, st.session_state["user_id"])
                st.success("Ticket erfolgreich erstellt!")
            else:
                st.error("Titel und Beschreibung sind erforderlich.")

def page_admin():
    """Zeigt das Admin-Dashboard zur Verwaltung aller Tickets."""
    st.header("Admin-Dashboard")
    all_tickets = get_all_tickets()

    if not all_tickets:
        st.info("Es sind keine Tickets vorhanden.")
        return

    # Benutzerliste für die Zuweisung von Tickets
    users = get_all_users()
    user_map = {user["id"]: user["username"] for user in users}
    user_ids = [None] + list(user_map.keys()) # [None] für "Keiner"

    # Jedes Ticket in einem Expander anzeigen, um die Seite übersichtlich zu halten
    for ticket in all_tickets:
        with st.expander(f'Ticket #{ticket["id"]}: {ticket["title"]}'):
            st.write(ticket["description"])
            st.caption(f'Erstellt von: {ticket["creator_name"]}')

            # Spalten für die Bearbeitungsfelder
            col1, col2, col3 = st.columns(3)
            new_status = col1.selectbox("Status", STATI, index=STATI.index(ticket["status"]), key=f'status_{ticket["id"]}')
            new_priority = col2.selectbox("Priorität", PRIORITIES, index=PRIORITIES.index(ticket["priority"]), key=f'prio_{ticket["id"]}')

            # Index des aktuellen Bearbeiters finden
            assignee_index = 0
            if ticket["assignee_id"] in user_ids:
                assignee_index = user_ids.index(ticket["assignee_id"])
            new_assignee_id = col3.selectbox("Bearbeiter", user_ids, index=assignee_index, format_func=lambda x: user_map.get(x, "Keiner"), key=f'assignee_{ticket["id"]}')

            # Speicher-Button
            if st.button("Speichern", key=f'save_{ticket["id"]}'):
                update_ticket(ticket["id"], new_status, new_priority, new_assignee_id)
                st.success(f'Ticket #{ticket["id"]} aktualisiert.')
                st.rerun()

# --- Hauptlogik der App ---
st.title("Einfaches Ticketsystem für Lernzwecke")

# Prüfen, ob der Benutzer eingeloggt ist
if "user_id" not in st.session_state:
    # Wenn nicht eingeloggt, zeige Login-Seite
    show_login()
else:
    # Wenn eingeloggt, zeige Navigation und die ausgewählte Seite
    page = show_navbar()
    if page == "Meine Tickets":
        page_my_tickets()
    elif page == "Ticket erstellen":
        page_create_ticket()
    elif page == "Admin":
        page_admin()