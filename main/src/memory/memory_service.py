import sqlite3
from pathlib import Path
from contextlib import contextmanager

from main.src.utils.constants import JENNA_MEMORY

DB_PATH = Path(JENNA_MEMORY)
if not DB_PATH.is_absolute():
    DB_PATH = (Path(__file__).resolve().parent / "../.." / DB_PATH).resolve()
DB_PATH = DB_PATH / "assistant_memory.sqlite3"

@contextmanager
def database():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DB_PATH, timeout=10)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS chat_messages_chat_id
            ON chat_messages(chat_id, id)
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS personal_notes (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        columns = {row[1] for row in connection.execute('PRAGMA table_info(personal_notes)')}
        if 'provenance' not in columns:
            try:
                connection.execute("ALTER TABLE personal_notes ADD COLUMN provenance TEXT NOT NULL DEFAULT '{}'")
            except sqlite3.OperationalError as error:
                if 'duplicate column' not in str(error): raise
        connection.execute("""
            CREATE TABLE IF NOT EXISTS conversation_state (
                session_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS uploaded_documents (
                filename TEXT PRIMARY KEY,
                content_hash TEXT NOT NULL,
                pdf_bytes BLOB NOT NULL,
                chunk_count INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%d %H:%M:%f', 'now')
                ),
                updated_at TEXT NOT NULL DEFAULT (
                    strftime('%Y-%m-%d %H:%M:%f', 'now')
                )
            )
        """)

        # Preserve conversations saved before multiple chats existed.
        connection.execute("""
            INSERT OR IGNORE INTO chats(
                id, title, created_at, updated_at
            )
            SELECT
                chat_id,
                'Saved conversation',
                MIN(created_at),
                MAX(created_at)
            FROM chat_messages
            GROUP BY chat_id
        """)

        connection.commit()

        with connection:
            yield connection

    finally:
        connection.close()

def fetch_records(
    table_name,
    columns="*",
    where=None,
    order_by=None,
    limit=None,
    offset=None,
):
    """Generic database fetch query builder.

    :param table_name: Target table name.
    :param columns: List of column names or '*' for all columns.
    :param where: Dict of column-value pairs for filtering (e.g. {'filename': 'doc.pdf'}).
    :param order_by: Column name or string to order by (e.g. 'filename ASC').
    :param limit: Max number of records to return.
    :param offset: Number of records to skip.
    """
    # 1. Format column selection
    if isinstance(columns, (list, tuple, set)):
        select_clause = ", ".join(columns)
    else:
        select_clause = str(columns)

    # 2. Build WHERE clause dynamically with bound parameters
    params = []
    where_clause = ""
    if where:
        conditions = [f"{col} = ?" for col in where.keys()]
        where_clause = "WHERE " + " AND ".join(conditions)
        params.extend(where.values())

    # 3. Build ORDER BY clause
    order_clause = f"ORDER BY {order_by}" if order_by else ""

    # 4. Build LIMIT / OFFSET clauses
    limit_clause = f"LIMIT {limit}" if limit is not None else ""
    offset_clause = f"OFFSET {offset}" if offset is not None else ""

    # Assemble query string
    query = f"""
        SELECT {select_clause}
        FROM {table_name}
        {where_clause}
        {order_clause}
        {limit_clause}
        {offset_clause}
    """

    with database() as connection:
        return connection.execute(query, params).fetchall()

def fetch_record(
    table_name,
    columns="*",
    where=None,
    order_by=None,
):
    """Generic database fetch query builder.

    :param table_name: Target table name.
    :param columns: List of column names or '*' for all columns.
    :param where: Dict of column-value pairs for filtering (e.g. {'filename': 'doc.pdf'}).
    :param order_by: Column name or string to order by (e.g. 'filename ASC').
    """
    # 1. Format column selection
    if isinstance(columns, (list, tuple, set)):
        select_clause = ", ".join(columns)
    else:
        select_clause = str(columns)

    # 2. Build WHERE clause dynamically with bound parameters
    params = []
    where_clause = ""
    if where:
        conditions = [f"{col} = ?" for col in where.keys()]
        where_clause = "WHERE " + " AND ".join(conditions)
        params.extend(where.values())

    # 3. Build ORDER BY clause
    order_clause = f"ORDER BY {order_by}" if order_by else ""

    # Assemble query string
    query = f"""
        SELECT {select_clause}
        FROM {table_name}
        {where_clause}
        {order_clause}
    """

    with database() as connection:
        return connection.execute(query, params).fetchone()

def insert(table_name, record_dict):
    """Generic SQLite INSERT statement.

    :param table_name: Name of the target table.
    :param record_dict: Key-value pairs of column names and values to insert.
    :return: The rowid / auto-increment primary key of the inserted row.
    """
    if not record_dict:
        raise ValueError("record_dict cannot be empty.")

    columns = list(record_dict.keys())
    values = list(record_dict.values())

    placeholders = ", ".join(["?"] * len(columns))
    formatted_columns = ", ".join(columns)

    query = f"""
        INSERT INTO {table_name} ({formatted_columns})
        VALUES ({placeholders})
    """

    with database() as connection:
        cursor = connection.execute(query, values)
        return cursor.lastrowid

def update(table_name, record_dict, where):
    """Generic SQLite UPDATE statement.

    :param table_name: Name of the target table.
    :param record_dict: Dict of column-value pairs to set/update.
    :param where: Dict of column-value pairs for the WHERE clause filtering.
    """
    if not record_dict:
        raise ValueError("record_dict cannot be empty.")
    if not where:
        raise ValueError(
            "where parameter cannot be empty to avoid updating all rows unintentionally."
        )

    # 1. Build SET assignments: "col1 = ?, col2 = ?"
    set_columns = list(record_dict.keys())
    set_clause = ", ".join(f"{col} = ?" for col in set_columns)
    values = list(record_dict.values())

    # 2. Build WHERE conditions: "filter_col1 = ? AND filter_col2 = ?"
    where_columns = list(where.keys())
    where_clause = " AND ".join(f"{col} = ?" for col in where_columns)
    values.extend(where.values())

    # Assemble query string
    query = f"""
        UPDATE {table_name}
        SET {set_clause}
        WHERE {where_clause}
    """

    with database() as connection:
        cursor = connection.execute(query, values)
        return cursor.lastrowid


def upsert(table_name, record_dict, conflict_target="filename"):
    """Generic SQLite UPSERT.

    Inserts a record, or updates the existing record when the
    conflict_target already exists.

    Example:
        upsert(
            "uploaded_documents",
            {
                "filename": filename,
                "content_hash": content_hash,
                "pdf_bytes": pdf_bytes,
                "chunk_count": chunk_count,
            },
            conflict_target="filename",
        )
    """
    if not record_dict:
        raise ValueError("record_dict cannot be empty.")

    if not conflict_target:
        raise ValueError("conflict_target cannot be empty.")

    # Support either a single conflict column or multiple columns.
    if isinstance(conflict_target, str):
        conflict_columns = [conflict_target]
    else:
        conflict_columns = list(conflict_target)

    columns = list(record_dict.keys())
    values = [record_dict[column] for column in columns]

    # Make sure every conflict column exists in the record.
    missing = [col for col in conflict_columns if col not in record_dict]
    if missing:
        raise ValueError(
            f"Conflict column(s) missing from record_dict: {missing}"
        )

    placeholders = ", ".join("?" for _ in columns)
    column_list = ", ".join(columns)
    conflict_clause = ", ".join(conflict_columns)

    # Update every column except the conflict column(s).
    update_columns = [
        column
        for column in columns
        if column not in conflict_columns
    ]

    update_assignments = [
        f"{column} = excluded.{column}"
        for column in update_columns
    ]

    # Always update the modification timestamp.
    update_assignments.append(
        "updated_at = CURRENT_TIMESTAMP"
    )

    update_clause = ", ".join(update_assignments)

    query = f"""
        INSERT INTO {table_name} ({column_list})
        VALUES ({placeholders})
        ON CONFLICT({conflict_clause}) DO UPDATE SET
            {update_clause}
    """

    with database() as connection:
        cursor = connection.execute(query, values)
        return cursor.lastrowid

def delete(table_name, where):
    """Generic SQLite DELETE statement.

    :param table_name: Name of the target table.
    :param where: Dict of column-value pairs for the WHERE clause filtering.
    """
    if not where:
        raise ValueError(
            "where parameter cannot be empty to avoid deleting all rows unintentionally."
        )

    # Build WHERE conditions: "filter_col1 = ? AND filter_col2 = ?"
    where_columns = list(where.keys())
    where_clause = " AND ".join(f"{col} = ?" for col in where_columns)
    values = list(where.values())

    # Assemble query string
    query = f"""
        DELETE FROM {table_name}
        WHERE {where_clause}
    """

    with database() as connection:
        cursor = connection.execute(query, values)
        return cursor.rowcount  # Returns the number of rows deleted

