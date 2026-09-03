from fastmcp import FastMCP
import aiosqlite
import asyncio
import os
from pathlib import Path
from datetime import date


# ============================================================
# FASTMCP SERVER
# ============================================================

mcp = FastMCP("ExpenseTracker")


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

# You can override this using:
#
# EXPENSES_DB_PATH=/path/to/expenses.db
#
# Otherwise, use a writable local directory.

DEFAULT_DB_DIR = Path(__file__).resolve().parent / "data"

DB_PATH = Path(
    os.environ.get(
        "EXPENSES_DB_PATH",
        str(DEFAULT_DB_DIR / "expenses.db")
    )
).resolve()


# ============================================================
# DATABASE CONNECTION
# ============================================================

async def get_db():
    """
    Create and return an async SQLite connection.
    """

    # Make sure the database directory exists
    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    db = await aiosqlite.connect(str(DB_PATH))

    # Return rows as dictionaries
    db.row_factory = aiosqlite.Row

    # Enable foreign keys
    await db.execute("PRAGMA foreign_keys = ON")

    # WAL allows better concurrent read/write performance.
    await db.execute("PRAGMA journal_mode = WAL")

    # Busy timeout prevents immediate "database is locked" errors.
    await db.execute("PRAGMA busy_timeout = 5000")

    return db


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

async def init_db():
    """
    Create the database and expenses table.
    """

    DB_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    async with aiosqlite.connect(str(DB_PATH)) as db:

        await db.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                date TEXT NOT NULL,

                amount REAL NOT NULL
                    CHECK(amount >= 0),

                category TEXT NOT NULL,

                subcategory TEXT DEFAULT '',

                note TEXT DEFAULT '',

                created_at TEXT
                    DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_date
            ON expenses(date)
        """)

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_expenses_category
            ON expenses(category)
        """)

        await db.commit()


# ============================================================
# SERVER STARTUP
# ============================================================

async def startup():
    """
    Initialize everything required before the MCP server starts.
    """

    await init_db()

    print(
        f"Expense database initialized at:\n{DB_PATH}"
    )


# ============================================================
# ADD EXPENSE
# ============================================================

@mcp.tool()
async def add_expense(
    date: str,
    amount: float,
    category: str,
    subcategory: str = "",
    note: str = ""
):
    """
    Add a new expense to the database.

    Args:
        date: Expense date in YYYY-MM-DD format.
        amount: Expense amount.
        category: Main expense category.
        subcategory: Optional subcategory.
        note: Optional note.

    Returns:
        Details of the newly created expense.
    """

    # --------------------------------------------------------
    # Validate date
    # --------------------------------------------------------

    try:
        date.fromisoformat(date)
    except ValueError:
        return {
            "status": "error",
            "message": "Invalid date. Use YYYY-MM-DD format."
        }

    # --------------------------------------------------------
    # Validate amount
    # --------------------------------------------------------

    if amount < 0:
        return {
            "status": "error",
            "message": "Amount cannot be negative."
        }

    # --------------------------------------------------------
    # Validate category
    # --------------------------------------------------------

    if not category.strip():
        return {
            "status": "error",
            "message": "Category cannot be empty."
        }

    # --------------------------------------------------------
    # Database operation
    # --------------------------------------------------------

    try:

        async with await get_db() as db:

            cursor = await db.execute(
                """
                INSERT INTO expenses (
                    date,
                    amount,
                    category,
                    subcategory,
                    note
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    date,
                    amount,
                    category.strip(),
                    subcategory.strip(),
                    note.strip()
                )
            )

            await db.commit()

            expense_id = cursor.lastrowid

        return {
            "status": "ok",
            "message": "Expense added successfully.",
            "expense": {
                "id": expense_id,
                "date": date,
                "amount": amount,
                "category": category.strip(),
                "subcategory": subcategory.strip(),
                "note": note.strip()
            }
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to add expense: {str(e)}"
        }


# ============================================================
# GET EXPENSE BY ID
# ============================================================

@mcp.tool()
async def get_expense(expense_id: int):
    """
    Get a single expense by its ID.
    """

    try:

        async with await get_db() as db:

            cursor = await db.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                    created_at
                FROM expenses
                WHERE id = ?
                """,
                (expense_id,)
            )

            row = await cursor.fetchone()

        if row is None:
            return {
                "status": "error",
                "message": f"No expense found with ID {expense_id}."
            }

        return {
            "status": "ok",
            "expense": dict(row)
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to get expense: {str(e)}"
        }


# ============================================================
# LIST EXPENSES BY DATE RANGE
# ============================================================

@mcp.tool()
async def list_expenses(
    start_date: str,
    end_date: str
):
    """
    List all expenses between two dates.

    Dates must be in YYYY-MM-DD format.
    """

    # --------------------------------------------------------
    # Validate dates
    # --------------------------------------------------------

    try:
        date.fromisoformat(start_date)
        date.fromisoformat(end_date)
    except ValueError:

        return {
            "status": "error",
            "message": "Dates must use YYYY-MM-DD format."
        }

    if start_date > end_date:

        return {
            "status": "error",
            "message": "start_date cannot be after end_date."
        }

    # --------------------------------------------------------
    # Query database
    # --------------------------------------------------------

    try:

        async with await get_db() as db:

            cursor = await db.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                    created_at
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date ASC, id ASC
                """,
                (
                    start_date,
                    end_date
                )
            )

            rows = await cursor.fetchall()

        expenses = [
            dict(row)
            for row in rows
        ]

        return {
            "status": "ok",
            "start_date": start_date,
            "end_date": end_date,
            "count": len(expenses),
            "expenses": expenses
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to list expenses: {str(e)}"
        }


# ============================================================
# GET ALL EXPENSES
# ============================================================

@mcp.tool()
async def get_all_expenses():
    """
    Get every expense stored in the database.
    """

    try:

        async with await get_db() as db:

            cursor = await db.execute(
                """
                SELECT
                    id,
                    date,
                    amount,
                    category,
                    subcategory,
                    note,
                    created_at
                FROM expenses
                ORDER BY date DESC, id DESC
                """
            )

            rows = await cursor.fetchall()

        expenses = [
            dict(row)
            for row in rows
        ]

        return {
            "status": "ok",
            "count": len(expenses),
            "expenses": expenses
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to get expenses: {str(e)}"
        }


# ============================================================
# UPDATE EXPENSE
# ============================================================

@mcp.tool()
async def update_expense(
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

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    try:
        date.fromisoformat(date)
    except ValueError:

        return {
            "status": "error",
            "message": "Invalid date. Use YYYY-MM-DD format."
        }

    if amount < 0:

        return {
            "status": "error",
            "message": "Amount cannot be negative."
        }

    if not category.strip():

        return {
            "status": "error",
            "message": "Category cannot be empty."
        }

    # --------------------------------------------------------
    # Update database
    # --------------------------------------------------------

    try:

        async with await get_db() as db:

            cursor = await db.execute(
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
                    category.strip(),
                    subcategory.strip(),
                    note.strip(),
                    expense_id
                )
            )

            await db.commit()

            rows_updated = cursor.rowcount

        if rows_updated == 0:

            return {
                "status": "error",
                "message": f"No expense found with ID {expense_id}."
            }

        return {
            "status": "ok",
            "message": "Expense updated successfully.",
            "id": expense_id
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to update expense: {str(e)}"
        }


# ============================================================
# DELETE EXPENSE
# ============================================================

@mcp.tool()
async def delete_expense(expense_id: int):
    """
    Delete an expense by ID.
    """

    try:

        async with await get_db() as db:

            cursor = await db.execute(
                """
                DELETE FROM expenses
                WHERE id = ?
                """,
                (expense_id,)
            )

            await db.commit()

            rows_deleted = cursor.rowcount

        if rows_deleted == 0:

            return {
                "status": "error",
                "message": f"No expense found with ID {expense_id}."
            }

        return {
            "status": "ok",
            "message": "Expense deleted successfully.",
            "id": expense_id
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to delete expense: {str(e)}"
        }


# ============================================================
# EXPENSE SUMMARY
# ============================================================

@mcp.tool()
async def expense_summary(
    start_date: str,
    end_date: str
):
    """
    Get expense totals and category-wise spending
    between two dates.
    """

    try:

        date.fromisoformat(start_date)
        date.fromisoformat(end_date)

    except ValueError:

        return {
            "status": "error",
            "message": "Dates must use YYYY-MM-DD format."
        }

    try:

        async with await get_db() as db:

            # ------------------------------------------------
            # Total
            # ------------------------------------------------

            cursor = await db.execute(
                """
                SELECT
                    COUNT(*) AS count,
                    COALESCE(SUM(amount), 0) AS total
                FROM expenses
                WHERE date BETWEEN ? AND ?
                """,
                (
                    start_date,
                    end_date
                )
            )

            total_row = await cursor.fetchone()

            # ------------------------------------------------
            # Category breakdown
            # ------------------------------------------------

            cursor = await db.execute(
                """
                SELECT
                    category,
                    COUNT(*) AS count,
                    SUM(amount) AS total
                FROM expenses
                WHERE date BETWEEN ? AND ?
                GROUP BY category
                ORDER BY total DESC
                """,
                (
                    start_date,
                    end_date
                )
            )

            category_rows = await cursor.fetchall()

        return {
            "status": "ok",
            "period": {
                "start_date": start_date,
                "end_date": end_date
            },
            "total_expenses": total_row["count"],
            "total_amount": total_row["total"],
            "categories": [
                dict(row)
                for row in category_rows
            ]
        }

    except Exception as e:

        return {
            "status": "error",
            "message": f"Failed to generate summary: {str(e)}"
        }


# ============================================================
# DATABASE HEALTH CHECK
# ============================================================

@mcp.tool()
async def database_info():
    """
    Check whether the database supports both read and write
    operations.
    """

    try:

        # ----------------------------------------------------
        # Check file permissions
        # ----------------------------------------------------

        DB_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        # ----------------------------------------------------
        # Open database
        # ----------------------------------------------------

        async with await get_db() as db:

            # READ TEST
            cursor = await db.execute(
                "SELECT COUNT(*) AS count FROM expenses"
            )

            row = await cursor.fetchone()

            current_count = row["count"]

            # WRITE TEST
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS __write_test (
                    id INTEGER PRIMARY KEY
                )
                """
            )

            await db.execute(
                """
                INSERT INTO __write_test DEFAULT VALUES
                """
            )

            await db.execute(
                """
                DELETE FROM __write_test
                """
            )

            await db.commit()

        return {
            "status": "ok",
            "database_path": str(DB_PATH),
            "database_exists": DB_PATH.exists(),
            "read": True,
            "write": True,
            "expense_count": current_count
        }

    except Exception as e:

        return {
            "status": "error",
            "database_path": str(DB_PATH),
            "database_exists": DB_PATH.exists(),
            "read": False,
            "write": False,
            "error": str(e)
        }


# ============================================================
# SERVER ENTRY POINT
# ============================================================

async def main():
    """
    Start the FastMCP server.
    """

    await startup()

    # FastMCP's HTTP server itself is started by mcp.run().
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())