import streamlit as st
import pandas as pd
from sqlalchemy import text
from DB import engine, inspector
from DB_utils import get_columns, create_ticket_relations
from utils.security import generate_salt, hash_password
from datetime import datetime

# Datenbankverwaltung anzeigen
def show_database_management():
    st.title("🛠️ Datenbankverwaltung")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Anzeigen", "✏️ Bearbeiten", "➕ Einfügen", "❌ Löschen"])

    # -----------------------------
    # 📋 Tab 1: Anzeigen
    # -----------------------------
    with tab1:
        st.subheader("Tabelle anzeigen")

        try:
            tabellen = inspector.get_table_names()
            table_choice = st.selectbox("Wähle eine Tabelle", tabellen, key="view_table")

            # Suchfunktion für die ausgewählte Tabelle
            st.subheader("🔍 Tabellensuche")

            # Durchsuchbare Spalten ermitteln
            searchable_columns = get_searchable_columns(table_choice)

            # Suchoptionen
            col1, col2, col3 = st.columns([3, 2, 1])

            with col1:
                search_term = st.text_input("Suchbegriff eingeben", placeholder="Suchbegriff...", key=f"search_term_{table_choice}")

            with col2:
                # Mehrfachauswahl für Spalten
                selected_columns = st.multiselect(
                    "Zu durchsuchende Spalten (leer = alle)",
                    options=searchable_columns,
                    key=f"search_columns_{table_choice}"
                )

            with col3:
                # Erweiterte Suchoptionen
                exact_match = st.checkbox("Exakte Übereinstimmung", key=f"exact_match_{table_choice}")
                case_sensitive = st.checkbox("Groß-/Kleinschreibung beachten", key=f"case_sensitive_{table_choice}")

            # Suchbutton
            search_clicked = st.button("Suchen", key=f"search_button_{table_choice}")

            # Daten laden - entweder Suchergebnisse oder alle Daten
            if search_clicked and search_term:
                # Suche durchführen
                results = search_table(
                    table_name=table_choice,
                    search_term=search_term,
                    search_columns=selected_columns if selected_columns else None,
                    exact_match=exact_match,
                    case_sensitive=case_sensitive
                )

                # Ergebnisse anzeigen
                if results.empty:
                    st.warning(f"Keine Ergebnisse für '{search_term}' gefunden.")
                    # Alle Daten anzeigen als Fallback
                    df = pd.read_sql(f"SELECT * FROM {table_choice}", con=engine)
                    st.write("Stattdessen werden alle Daten angezeigt:")
                else:
                    st.success(f"{len(results)} Ergebnisse gefunden.")
                    df = results
            else:
                # Alle Daten anzeigen
                df = pd.read_sql(f"SELECT * FROM {table_choice}", con=engine)

            # Daten anzeigen
            st.dataframe(df, use_container_width=True)

            # Button zum Zurücksetzen der Suche
            if search_clicked and search_term:
                if st.button("Suche zurücksetzen", key=f"reset_search_{table_choice}"):
                    st.rerun()

            # Optional: In Session speichern für andere Tabs
            st.session_state["last_viewed_table"] = table_choice
            st.session_state["last_viewed_df"] = df.copy()

        except Exception as e:
            st.error("❌ Fehler beim Laden:")
            st.exception(e)

    # -----------------------------
    # ✏️ Tab 2: Bearbeiten
    # -----------------------------
    with tab2:
        st.subheader("Datensätze bearbeiten (interaktiv)")

        try:
            tabellen = inspector.get_table_names()
            table_choice_edit = st.selectbox("Tabelle wählen (Bearbeiten)", tabellen, key="edit_table_editor")
            spalten = get_columns(table_choice_edit)
            id_spalte = st.selectbox("Primärschlüsselspalte", spalten, key="primary_column_editor")

            if "original_df" not in st.session_state:
                st.session_state.original_df = pd.DataFrame()
            if "edited_df" not in st.session_state:
                st.session_state.edited_df = pd.DataFrame()

            if st.button("🔄 Daten laden (Editiermodus)"):
                df = pd.read_sql(f"SELECT * FROM {table_choice_edit}", con=engine)
                st.session_state.original_df = df.copy()
                st.session_state.edited_df = df.copy()

            if not st.session_state.original_df.empty:
                st.markdown("✏️ **Daten bearbeiten – Änderungen werden erst nach dem Speichern übernommen.**")
                st.session_state.edited_df = st.data_editor(
                    st.session_state.edited_df,
                    use_container_width=True,
                    num_rows="fixed",
                    key="editable_df"
                )

                if st.button("💾 Änderungen speichern"):
                    df = st.session_state.original_df
                    edited_df = st.session_state.edited_df
                    delta = df.compare(edited_df, keep_shape=True, keep_equal=True)
                    rows_to_update = delta.dropna(how="all").index.tolist()

                    if not rows_to_update:
                        st.info("Keine Änderungen erkannt.")
                    else:
                        try:
                            with engine.begin() as conn:
                                for idx in rows_to_update:
                                    row = edited_df.loc[idx]
                                    original_row = df.loc[idx]

                                    update_fields = {}
                                    for col in spalten:
                                        if row[col] != original_row[col]:
                                            update_fields[col] = row[col]

                                    if update_fields:
                                        set_clause = ", ".join([f"{col} = :{col}" for col in update_fields])
                                        query = text(
                                            f"UPDATE {table_choice_edit} SET {set_clause} WHERE {id_spalte} = :id_value"
                                        )
                                        update_fields["id_value"] = row[id_spalte]
                                        conn.execute(query, update_fields)

                            st.success("✅ Änderungen erfolgreich gespeichert.")
                            # Daten neu laden
                            df = pd.read_sql(f"SELECT * FROM {table_choice_edit}", con=engine)
                            st.session_state.original_df = df.copy()
                            st.session_state.edited_df = df.copy()
                            st.rerun()

                        except Exception as e:
                            st.error("❌ Fehler beim Speichern:")
                            st.exception(e)

        except Exception as e:
            st.error("❌ Fehler beim Bearbeiten der Daten:")
            st.exception(e)

    # -----------------------------
    # ➕ Tab 3: Einfügen
    # -----------------------------
    with tab3:
        st.subheader("Datensatz einfügen")

        # Tabs für einzelne und mehrfache Einfügung
        insert_tab1, insert_tab2 = st.tabs(["Einzelner Datensatz", "Mehrere Datensätze"])

        try:
            tabellen = inspector.get_table_names()
            table_choice = st.selectbox("Tabelle wählen (Einfügen)", tabellen, key="insert_table")
            spalten = get_columns(table_choice)
            spalten_typen = get_column_types(table_choice)

            # Tab für einzelnen Datensatz
            with insert_tab1:
                with st.form(key="insert_form_single"):
                    st.subheader(f"Neuen Datensatz in '{table_choice}' einfügen")

                    inputs = {}
                    for spalte in spalten:
                        # Spezielle Behandlung für Datum/Zeit-Spalten
                        if 'date' in spalte.lower() or 'time' in spalte.lower() or 'erstellt' in spalte.lower():
                            # Aktuelles Datum als Standardwert für Datum/Zeit-Spalten
                            default_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            inputs[spalte] = st.text_input(f"{spalte}", value=default_value, key=f"insert_{spalte}")
                        # Spezielle Behandlung für Passwort-Spalten
                        elif 'password' in spalte.lower() and table_choice.lower() == 'mitarbeiter':
                            password = st.text_input(f"{spalte}", type="password", key=f"insert_{spalte}")
                            # Salt wird automatisch generiert und das Passwort gehasht
                            inputs[spalte] = password  # Wird später verarbeitet
                        else:
                            inputs[spalte] = st.text_input(f"{spalte}", key=f"insert_{spalte}")

                    submit_insert = st.form_submit_button("💾 Einfügen")

                if submit_insert:
                    try:
                        # Spezielle Behandlung für Mitarbeiter-Tabelle mit Passwort-Hashing
                        if table_choice.lower() == 'mitarbeiter' and 'Password_hash' in spalten:
                            # Salt generieren und Passwort hashen
                            salt = generate_salt()
                            password = inputs.get('Password_hash', '')
                            password_hash = hash_password(password, salt)

                            # Werte aktualisieren
                            inputs['Password_hash'] = password_hash
                            inputs['salt'] = salt

                        with engine.begin() as conn:
                            # Nur Spalten einfügen, für die Werte vorhanden sind
                            valid_spalten = [col for col in spalten if inputs.get(col)]
                            placeholders = ", ".join([f":{col}" for col in valid_spalten])
                            query = text(f"INSERT INTO {table_choice} ({', '.join(valid_spalten)}) VALUES ({placeholders})")
                            result = conn.execute(query, {col: inputs[col] for col in valid_spalten})

                            # Wenn es sich um ein Ticket handelt, automatische Beziehungen erstellen
                            if table_choice == "ticket":
                                ticket_id = result.lastrowid
                                ID_Mitarbeiter = inputs.get("ID_Mitarbeiter")

                                # Standard-Kategorie (ID 1) verwenden
                                create_ticket_relations(ticket_id, ID_Mitarbeiter, 1)

                        st.success(f"✅ Datensatz in '{table_choice}' eingefügt!")
                    except Exception as e:
                        st.error("❌ Fehler beim Einfügen:")
                        st.exception(e)

            # Tab für mehrere Datensätze
            with insert_tab2:
                st.subheader(f"Mehrere Datensätze in '{table_choice}' einfügen")

                # Initialisiere leeren DataFrame für die Eingabe, wenn noch nicht vorhanden
                if "multi_insert_df" not in st.session_state or st.session_state.get("last_multi_insert_table") != table_choice:
                    # Erstelle leeren DataFrame mit den Spalten der Tabelle
                    empty_df = pd.DataFrame(columns=spalten)

                    # Füge eine leere Zeile hinzu
                    empty_row = {col: "" for col in spalten}
                    # Spezielle Behandlung für Datum/Zeit-Spalten
                    for col in spalten:
                        if 'date' in col.lower() or 'time' in col.lower() or 'erstellt' in col.lower():
                            empty_row[col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                    empty_df = pd.concat([empty_df, pd.DataFrame([empty_row])], ignore_index=True)

                    st.session_state["multi_insert_df"] = empty_df
                    st.session_state["last_multi_insert_table"] = table_choice

                # Zeige Hinweis
                st.info("Fügen Sie Zeilen hinzu und bearbeiten Sie die Daten. Klicken Sie dann auf 'Speichern'.")

                # Daten-Editor für mehrere Zeilen
                edited_df = st.data_editor(
                    st.session_state["multi_insert_df"],
                    use_container_width=True,
                    num_rows="dynamic",
                    key="multi_insert_editor"
                )

                # Speichern-Button
                if st.button("💾 Alle Datensätze einfügen"):
                    if edited_df.empty or edited_df.iloc[0].isnull().all():
                        st.warning("Keine Daten zum Einfügen vorhanden.")
                    else:
                        try:
                            success_count = 0
                            error_count = 0

                            with engine.begin() as conn:
                                for _, row in edited_df.iterrows():
                                    # Leere Zeilen überspringen
                                    if row.isnull().all():
                                        continue

                                    # Nur Spalten einfügen, für die Werte vorhanden sind
                                    valid_spalten = [col for col in spalten if pd.notna(row[col]) and row[col] != ""]
                                    if not valid_spalten:
                                        continue

                                    try:
                                        # Spezielle Behandlung für Mitarbeiter-Tabelle mit Passwort-Hashing
                                        values = {}
                                        for col in valid_spalten:
                                            values[col] = row[col]

                                        if table_choice.lower() == 'mitarbeiter' and 'Password_hash' in valid_spalten:
                                            # Salt generieren und Passwort hashen
                                            salt = generate_salt()
                                            password = values.get('Password_hash', '')
                                            password_hash = hash_password(password, salt)

                                            # Werte aktualisieren
                                            values['Password_hash'] = password_hash
                                            values['salt'] = salt
                                            if 'salt' not in valid_spalten:
                                                valid_spalten.append('salt')

                                        placeholders = ", ".join([f":{col}" for col in valid_spalten])
                                        query = text(f"INSERT INTO {table_choice} ({', '.join(valid_spalten)}) VALUES ({placeholders})")
                                        result = conn.execute(query, values)

                                        # Wenn es sich um ein Ticket handelt, automatische Beziehungen erstellen
                                        if table_choice == "ticket":
                                            ticket_id = result.lastrowid
                                            ID_Mitarbeiter = values.get("ID_Mitarbeiter")

                                            # Standard-Kategorie (ID 1) verwenden
                                            create_ticket_relations(ticket_id, ID_Mitarbeiter, 1)

                                        success_count += 1
                                    except Exception as e:
                                        error_count += 1
                                        st.error(f"Fehler beim Einfügen von Zeile {_+1}: {str(e)}")

                            if success_count > 0:
                                st.success(f"✅ {success_count} Datensätze erfolgreich eingefügt!")
                                # Leeren DataFrame für neue Eingaben erstellen
                                empty_df = pd.DataFrame(columns=spalten)
                                empty_row = {col: "" for col in spalten}
                                # Spezielle Behandlung für Datum/Zeit-Spalten
                                for col in spalten:
                                    if 'date' in col.lower() or 'time' in col.lower() or 'erstellt' in col.lower():
                                        empty_row[col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                empty_df = pd.concat([empty_df, pd.DataFrame([empty_row])], ignore_index=True)
                                st.session_state["multi_insert_df"] = empty_df
                                st.rerun()

                            if error_count > 0:
                                st.warning(f"⚠️ {error_count} Datensätze konnten nicht eingefügt werden.")

                        except Exception as e:
                            st.error(f"❌ Fehler beim Einfügen der Datensätze: {str(e)}")

        except Exception as e:
            st.error("❌ Fehler beim Einfügen:")
            st.exception(e)

    # -----------------------------
    # ❌ Tab 4: Löschen
    # -----------------------------
    with tab4:
        st.subheader("Datensatz löschen")

        try:
            tabellen = inspector.get_table_names()
            table_choice_delete = st.selectbox("Tabelle wählen (Löschen)", tabellen, key="delete_table")
            spalten_delete = get_columns(table_choice_delete)
            id_spalte_delete = st.selectbox("Primärschlüsselspalte", spalten_delete, key="primary_column_delete")

            if st.button("🔄 Daten zum Löschen laden"):
                df_delete = pd.read_sql(f"SELECT * FROM {table_choice_delete}", con=engine)
                st.dataframe(df_delete, use_container_width=True)

                if not df_delete.empty:
                    selected_id_to_delete = st.selectbox(
                        f"Datensatz zum Löschen auswählen ({id_spalte_delete})",
                        df_delete[id_spalte_delete].tolist()
                    )

                    if st.button("🗑️ Datensatz löschen"):
                        try:
                            with engine.begin() as conn:
                                query = text(f"DELETE FROM {table_choice_delete} WHERE {id_spalte_delete} = :value")
                                result = conn.execute(query, {"value": selected_id_to_delete})

                                if result.rowcount > 0:
                                    st.success(f"✅ Datensatz mit {id_spalte_delete} = {selected_id_to_delete} gelöscht.")
                                else:
                                    st.warning(f"⚠️ Kein Datensatz gelöscht. Möglicherweise wurde er bereits entfernt.")

                            # Daten neu laden
                            df_delete = pd.read_sql(f"SELECT * FROM {table_choice_delete}", con=engine)
                            st.write("Aktualisierte Tabellendaten:")
                            st.dataframe(df_delete)

                        except Exception as e:
                            st.error("❌ Fehler beim Löschen:")
                            st.exception(e)
                else:
                    st.info(f"Keine Daten in der Tabelle {table_choice_delete}.")

        except Exception as e:
            st.error("❌ Fehler beim Laden der Daten zum Löschen:")
            st.exception(e)

# Hilfsfunktion: Primärschlüssel einer Tabelle ermitteln
def get_primary_key(table):
    try:
        pk = inspector.get_pk_constraint(table)
        if pk and 'constrained_columns' in pk and pk['constrained_columns']:
            return pk['constrained_columns'][0]
        # Fallback: Suche nach Spalten mit 'id' im Namen
        columns = get_columns(table)
        for col in columns:
            if col.lower() == 'id':
                return col
        # Zweiter Fallback: Erste Spalte
        if columns:
            return columns[0]
        return None
    except:
        return None

# Hilfsfunktion: Spaltentypen einer Tabelle
def get_column_types(table):
    try:
        return {col["name"]: str(col["type"]) for col in inspector.get_columns(table)}
    except:
        return {}

# Hilfsfunktion: Durchsuchbare Spalten einer Tabelle ermitteln
def get_searchable_columns(table):
    try:
        column_types = get_column_types(table)
        searchable_columns = []

        for col, type_str in column_types.items():
            # Spaltentypen, die für die Suche geeignet sind
            if any(text_type in type_str.lower() for text_type in ['char', 'text', 'varchar', 'enum']):
                searchable_columns.append(col)
            # Numerische Typen sind auch durchsuchbar
            elif any(num_type in type_str.lower() for num_type in ['int', 'decimal', 'float', 'double']):
                searchable_columns.append(col)
            # Datum/Zeit-Typen sind auch durchsuchbar
            elif any(date_type in type_str.lower() for date_type in ['date', 'time', 'datetime', 'timestamp']):
                searchable_columns.append(col)

        return searchable_columns
    except Exception as e:
        st.error(f"Fehler beim Ermitteln der durchsuchbaren Spalten: {str(e)}")
        return []

# Hilfsfunktion: Tabelle durchsuchen
def search_table(table_name, search_term, search_columns=None, exact_match=False, case_sensitive=False):
    try:
        if not search_term:
            return pd.DataFrame()

        # Durchsuchbare Spalten ermitteln
        if search_columns is None:
            search_columns = get_searchable_columns(table_name)

        if not search_columns:
            st.warning(f"Keine durchsuchbaren Spalten in der Tabelle '{table_name}' gefunden.")
            return pd.DataFrame()

        # SQL-Abfrage erstellen
        conditions = []
        params = {}

        for i, col in enumerate(search_columns):
            param_name = f"search_term_{i}"

            if exact_match:
                # Exakte Übereinstimmung
                if case_sensitive:
                    conditions.append(f"{col} = :{param_name}")
                else:
                    conditions.append(f"LOWER({col}) = :{param_name}")
                    search_term = search_term.lower()

                params[param_name] = search_term
            else:
                # Teilweise Übereinstimmung
                if case_sensitive:
                    conditions.append(f"{col} LIKE :{param_name}")
                else:
                    conditions.append(f"LOWER({col}) LIKE :{param_name}")
                    search_term = search_term.lower()

                params[param_name] = f"%{search_term}%"

        # WHERE-Klausel erstellen
        where_clause = " OR ".join(conditions)

        # SQL-Abfrage ausführen
        query = text(f"SELECT * FROM {table_name} WHERE {where_clause}")

        with engine.connect() as conn:
            result = conn.execute(query, params)
            columns = result.keys()
            data = result.fetchall()

        # DataFrame erstellen
        df = pd.DataFrame(data, columns=columns)
        return df

    except Exception as e:
        st.error(f"Fehler bei der Suche: {str(e)}")
        return pd.DataFrame()


