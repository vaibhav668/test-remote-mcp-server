from fastmcp import FastMCP
import os
import sqlite3
from pathlib import Path
from datetime import datetime


mcp = FastMCP("ExpenseTracker")


# --------------------------------------------------
# DATABASE CONFIGURATION
# --------------------------------------------------

# Use EXPENSES_DB_PATH if provided.
# Otherwise store the DB in /tmp, which is normally writable
# in container/server environments.
DB_PATH = os.environ.get(
    "EXPENSES_DB_PATH",
    "/tmp/expenses.db"
)

DB_PATH = os.path.abspath(DB_PATH)

# Make sure the parent directory exists
db_dir = os.path.dirname(DB_PATH)

if db_dir:
    os.makedirs(db_dir, exist_ok=True)


# --------------------------------------------------
# DATABASE CONNECTION
# --------------------------------------------------

def get_connection():
    """
    Create a SQLite connection with read/write access.
    """
    conn = sqlite3.connect(DB_PATH)

    # Foreign keys
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# --------------------------------------------------
# INITIALIZE DATABASE
# --------------------------------------------------

def init_db():
    """
    Create the expenses table if it doesn't already exist.
    """

    with get_connection() as conn:

        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)

        conn.commit()


init_db()


# --------------------------------------------------
# ADD EXPENSE
# --------------------------------------------------

@mcp.tool()
def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
):
    """
    Add a new expense to the database.
    """

    with get_connection() as conn:

        cursor = conn.execute(
            """
            INSERT INTO expenses
            (date, amount, category, subcategory, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                date,
                amount,
                category,
                subcategory,
                note
            )
        )

        conn.commit()

        return {
            "status": "ok",
            "message": "Expense added successfully",
            "id": cursor.lastrowid,
            "date": date,
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
            "note": note
        }


# --------------------------------------------------
# LIST EXPENSES
# --------------------------------------------------

@mcp.tool()
def list_expenses(
    start_date: str,
    end_date: str
):
    """
    List all expenses between start_date and end_date.
    """

    with get_connection() as conn:

        cursor = conn.execute(
            """
            SELECT
                id,
                date,
                amount,
                category,
                subcategory,
                note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date ASC, id ASC
            """,
            (start_date, end_date)
        )

        columns = [description[0] for description in cursor.description]

        rows = cursor.fetchall()

        return [
            dict(zip(columns, row))
            for row in rows
        ]


# --------------------------------------------------
# GET ALL EXPENSES
# --------------------------------------------------

@mcp.tool()
def get_all_expenses():
    """
    Get every expense stored in the database.
    """

    with get_connection() as conn:

        cursor = conn.execute("""
            SELECT
                id,
                date,
                amount,
                category,
                subcategory,
                note
            FROM expenses
            ORDER BY date ASC, id ASC
        """)

        columns = [description[0] for description in cursor.description]

        return [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]


# --------------------------------------------------
# DELETE EXPENSE
# --------------------------------------------------

@mcp.tool()
def delete_expense(expense_id: int):
    """
    Delete an expense using its ID.
    """

    with get_connection() as conn:

        cursor = conn.execute(
            """
            DELETE FROM expenses
            WHERE id = ?
            """,
            (expense_id,)
        )

        conn.commit()

        if cursor.rowcount == 0:
            return {
                "status": "error",
                "message": f"No expense found with id {expense_id}"
            }

        return {
            "status": "ok",
            "message": "Expense deleted successfully",
            "id": expense_id
        }


# --------------------------------------------------
# UPDATE EXPENSE
# --------------------------------------------------

@mcp.tool()
def update_expense(
    expense_id: int,
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
):
    """
    Update an existing expense.
    """

    with get_connection() as conn:

        cursor = conn.execute(
            """
            UPDATE expenses
            SET
                date = ?,
                amount = ?,
                category = ?,
                subcategory = ?,
                note = ?
            WHERE id = ?
            """,
            (
                date,
                amount,
                category,
                subcategory,
                note,
                expense_id
            )
        )

        conn.commit()

        if cursor.rowcount == 0:
            return {
                "status": "error",
                "message": f"No expense found with id {expense_id}"
            }

        return {
            "status": "ok",
            "message": "Expense updated successfully",
            "id": expense_id
        }


# --------------------------------------------------
# DATABASE INFO / HEALTH CHECK
# --------------------------------------------------

@mcp.tool()
def database_info():
    """
    Check database location and whether read/write operations work.
    """

    try:

        with get_connection() as conn:

            # Test write operation using a temporary table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS __write_test (
                    id INTEGER PRIMARY KEY
                )
            """)

            conn.execute("""
                INSERT INTO __write_test DEFAULT VALUES
            """)

            conn.execute("""
                DELETE FROM __write_test
            """)

            conn.commit()

        return {
            "status": "ok",
            "database": DB_PATH,
            "read": True,
            "write": True
        }

    except Exception as e:

        return {
            "status": "error",
            "database": DB_PATH,
            "read": True,
            "write": False,
            "error": str(e)
        }


# --------------------------------------------------
# START SERVER
# --------------------------------------------------

def main():
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000
    )


if __name__ == "__main__":
    main()